#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RTSP 流转 WebSocket 服务器 - 集成版本
服务器主动连接 RTSP 源，读取帧，通过 WebSocket 转发到浏览器
支持 HTTP 控制接口和命令行控制工具
"""

import cv2
import base64
import threading
import time
import os
import sys
import signal
import argparse
import requests
from flask import Flask, jsonify
from flask_socketio import SocketIO, emit
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'streaming-server-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# RTSP 流配置
RTSP_URL = os.getenv('RTSP_URL', 'rtsp://127.0.0.1:8554/mystream')
JPEG_QUALITY = 80
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

# 全局变量
cap = None
frame_thread = None
is_streaming = False
clients_connected = 0
stream_info = {
    'is_running': False,
    'frames_sent': 0,
    'clients': 0,
    'start_time': None,
    'last_error': None
}




@app.route('/')
def index():
    """服务根路径（不再提供独立 RTSP 预览页）"""
    return jsonify({
        'service': 'rtsp-websocket-stream',
        'message': 'RTSP preview page has been removed. Use dashboard left monitor panel.',
        'status_endpoint': '/status',
        'health_endpoint': '/health'
    }), 200


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
    }), 200


@app.route('/status', methods=['GET'])
def get_status():
    """获取流状态"""
    uptime = None
    if stream_info['start_time']:
        uptime = time.time() - stream_info['start_time']
    
    return jsonify({
        'is_running': stream_info['is_running'],
        'frames_sent': stream_info['frames_sent'],
        'clients_connected': stream_info['clients'],
        'uptime_seconds': uptime,
        'rtsp_url': RTSP_URL,
        'last_error': stream_info['last_error']
    }), 200


@app.route('/start', methods=['POST'])
def start_stream():
    """启动流"""
    global is_streaming, cap
    
    if is_streaming:
        return jsonify({'status': 'already_running'}), 200
    
    if init_rtsp_capture():
        start_streaming()
        return jsonify({'status': 'started'}), 200
    else:
        return jsonify({'status': 'failed', 'error': 'Cannot connect to RTSP'}), 500


@app.route('/stop', methods=['POST'])
def stop_stream():
    """停止流"""
    stop_streaming()
    return jsonify({'status': 'stopped'}), 200


def init_rtsp_capture():
    """初始化 RTSP 捕获"""
    global cap
    try:
        logger.info(f"正在连接 RTSP 流: {RTSP_URL}")
        cap = cv2.VideoCapture(RTSP_URL)
        
        # 设置缓冲区大小为 1，减少延迟
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not cap.isOpened():
            logger.error("无法打开 RTSP 流")
            stream_info['last_error'] = 'Cannot open RTSP stream'
            return False
        
        logger.info("RTSP 流连接成功")
        return True
    except Exception as e:
        logger.error(f"RTSP 连接失败: {e}")
        stream_info['last_error'] = str(e)
        return False


def stream_frames():
    """持续读取 RTSP 帧并通过 WebSocket 发送"""
    global cap, is_streaming
    
    frame_count = 0
    error_consecutive = 0
    max_consecutive_errors = 10
    
    while is_streaming and cap and cap.isOpened():
        try:
            ret, frame = cap.read()
            
            if not ret:
                error_consecutive += 1
                logger.warning(f"无法读取帧 ({error_consecutive}/{max_consecutive_errors})")
                
                if error_consecutive >= max_consecutive_errors:
                    logger.warning("连续错误过多，尝试重新连接...")
                    cap.release()
                    if not init_rtsp_capture():
                        is_streaming = False
                        break
                    error_consecutive = 0
                continue
            
            error_consecutive = 0  # 重置错误计数
            
            # 压缩帧大小以减少网络带宽
            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
            
            # 将帧编码为 JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not ret:
                continue
            
            # 转换为 Base64
            frame_data = base64.b64encode(buffer).decode('utf-8')
            frame_count += 1
            stream_info['frames_sent'] = frame_count
            
            # 广播给所有客户端
            socketio.emit('frame', {
                'image': f"data:image/jpeg;base64,{frame_data}",
                'frame_number': frame_count
            }, to=None)
            
        except Exception as e:
            logger.error(f"处理帧时出错: {e}")
            stream_info['last_error'] = str(e)
            continue


def start_streaming():
    """启动流传输线程"""
    global is_streaming, frame_thread
    
    if is_streaming:
        return
    
    is_streaming = True
    stream_info['is_running'] = True
    stream_info['frames_sent'] = 0
    stream_info['start_time'] = time.time()
    
    frame_thread = threading.Thread(target=stream_frames, daemon=True)
    frame_thread.start()
    logger.info("流传输已启动")


def stop_streaming():
    """停止流传输"""
    global is_streaming, cap
    
    is_streaming = False
    stream_info['is_running'] = False
    
    if cap:
        cap.release()
        cap = None
    
    logger.info("流传输已停止")


@socketio.on('connect')
def handle_connect():
    """处理客户端连接"""
    global clients_connected
    clients_connected += 1
    stream_info['clients'] = clients_connected
    
    logger.info(f"客户端已连接，当前连接数: {clients_connected}")
    emit('connection_response', {'data': '已连接到服务器'})
    
    # 如果是第一个客户端，启动流传输
    if clients_connected == 1:
        logger.info("第一个客户端连接，启动流传输...")
        if init_rtsp_capture():
            start_streaming()


@socketio.on('disconnect')
def handle_disconnect():
    """处理客户端断开连接"""
    global clients_connected
    clients_connected -= 1
    stream_info['clients'] = clients_connected
    
    logger.info(f"客户端已断开连接，当前连接数: {clients_connected}")
    
    # 如果没有客户端连接，停止流传输
    if clients_connected == 0:
        logger.info("所有客户端已断开，停止流传输...")
        stop_streaming()


# ===================== 命令行控制功能 =====================

def signal_handler(sig, frame):
    """处理 Ctrl+C"""
    logger.info("\n关闭服务器...")
    stop_streaming()
    sys.exit(0)


def get_status(server_url):
    """获取服务器状态"""
    try:
        response = requests.get(f"{server_url}/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            logger.info("=" * 50)
            logger.info(f"运行中: {data['is_running']}")
            logger.info(f"连接客户端: {data['clients_connected']}")
            logger.info(f"已发送帧数: {data['frames_sent']}")
            if data['uptime_seconds']:
                logger.info(f"运行时长: {data['uptime_seconds']:.1f}s")
            logger.info(f"RTSP 源: {data['rtsp_url']}")
            if data['last_error']:
                logger.info(f"错误: {data['last_error']}")
            logger.info("=" * 50)
        else:
            logger.error("获取状态失败")
    except Exception as e:
        logger.error(f"无法连接到服务器: {e}")


def start_stream_cmd(server_url):
    """启动流"""
    try:
        response = requests.post(f"{server_url}/start", timeout=5)
        if response.status_code == 200:
            logger.info("✓ 流已启动")
        else:
            logger.error("✗ 启动失败")
    except Exception as e:
        logger.error(f"✗ 启动失败: {e}")


def stop_stream_cmd(server_url):
    """停止流"""
    try:
        response = requests.post(f"{server_url}/stop", timeout=5)
        if response.status_code == 200:
            logger.info("✓ 流已停止")
        else:
            logger.error("✗ 停止失败")
    except Exception as e:
        logger.error(f"✗ 停止失败: {e}")


def run_server_mode(server_port=5002, server_host='0.0.0.0', rtsp_url=None):
    """启动服务器模式"""
    global RTSP_URL
    
    if rtsp_url:
        RTSP_URL = rtsp_url
    
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 60)
    logger.info("RTSP WebSocket 服务器启动")
    logger.info("=" * 60)
    logger.info(f"访问地址: http://{server_host}:{server_port}")
    logger.info(f"RTSP 源 URL: {RTSP_URL}")
    logger.info(f"帧分辨率: {FRAME_WIDTH}x{FRAME_HEIGHT}")
    logger.info(f"JPEG 质量: {JPEG_QUALITY}")
    logger.info("=" * 60)
    logger.info("HTTP 接口:")
    logger.info("  GET  /health - 健康检查")
    logger.info("  GET  /status - 获取流状态")
    logger.info("  POST /start  - 启动流")
    logger.info("  POST /stop   - 停止流")
    logger.info("=" * 60)
    logger.info("命令行控制:")
    logger.info("  python server.py status")
    logger.info("  python server.py stream-start")
    logger.info("  python server.py stream-stop")
    logger.info("=" * 60)
    logger.info("按 Ctrl+C 停止\n")
    
    socketio.run(app, host=server_host, port=server_port, debug=False, allow_unsafe_werkzeug=True)


def main():
    """命令行主函数"""
    parser = argparse.ArgumentParser(description='RTSP WebSocket 服务器')
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # 启动服务器
    start_parser = subparsers.add_parser('start', help='启动服务器')
    start_parser.add_argument('--host', default='0.0.0.0', help='监听地址 (默认: 0.0.0.0)')
    start_parser.add_argument('--port', type=int, default=5002, help='端口 (默认: 5002)')
    start_parser.add_argument('--rtsp', help='RTSP 源 URL')
    
    # 查看状态
    status_parser = subparsers.add_parser('status', help='查看服务器状态')
    status_parser.add_argument('--server', default='http://127.0.0.1:5002', help='服务器地址')
    
    # 启动流
    stream_start_parser = subparsers.add_parser('stream-start', help='启动流传输')
    stream_start_parser.add_argument('--server', default='http://127.0.0.1:5002', help='服务器地址')
    
    # 停止流
    stream_stop_parser = subparsers.add_parser('stream-stop', help='停止流传输')
    stream_stop_parser.add_argument('--server', default='http://127.0.0.1:5002', help='服务器地址')
    
    args = parser.parse_args()
    
    if not args.command:
        # 默认启动服务器（不带参数时）
        args.command = 'start'
        args.host = '0.0.0.0'
        args.port = 5002
        args.rtsp = None
    
    if args.command == 'start':
        run_server_mode(args.port, args.host, args.rtsp)
    
    elif args.command == 'status':
        get_status(args.server.rstrip('/'))
    
    elif args.command == 'stream-start':
        start_stream_cmd(args.server.rstrip('/'))
    
    elif args.command == 'stream-stop':
        stop_stream_cmd(args.server.rstrip('/'))


if __name__ == '__main__':
    main()
