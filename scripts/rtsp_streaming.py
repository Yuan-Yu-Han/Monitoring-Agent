#!/usr/bin/env python3
"""
RTSP流处理和Web UI实时显示
支持网络摄像头实时检测和WebSocket推送
"""

import asyncio
import json
import time
import threading
import queue
from typing import Dict, List, Optional, Any, Callable
import logging

# 条件导入
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

logger = logging.getLogger(__name__)


class VideoStreamReader:
    """视频流读取器"""
    
    def __init__(self, source: str, queue_size: int = 10):
        self.source = source
        self.queue = queue.Queue(maxsize=queue_size)
        self.cap = None
        self.running = False
        self.thread = None
        self.last_frame_time = 0
        self.fps = 30
        self.frame_interval = 1.0 / self.fps
    
    def start(self):
        """启动视频流读取"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._read_frames, daemon=True)
        self.thread.start()
        logger.info(f"视频流读取器已启动: {self.source}")
    
    def stop(self):
        """停止视频流读取"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
        logger.info("视频流读取器已停止")
    
    def _read_frames(self):
        """读取帧的线程函数"""
        self.cap = cv2.VideoCapture(self.source)
        
        if not self.cap.isOpened():
            logger.error(f"无法打开视频源: {self.source}")
            return
        
        # 设置缓冲区大小
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                logger.warning("读取帧失败，尝试重新连接...")
                time.sleep(1)
                # 尝试重新连接
                self.cap.release()
                self.cap = cv2.VideoCapture(self.source)
                continue
            
            # 控制帧率
            current_time = time.time()
            if current_time - self.last_frame_time < self.frame_interval:
                continue
            
            self.last_frame_time = current_time
            
            # 将帧放入队列
            try:
                self.queue.put(frame, block=False)
            except queue.Full:
                # 队列满时丢弃旧帧
                try:
                    self.queue.get_nowait()
                    self.queue.put(frame, block=False)
                except queue.Empty:
                    pass
    
    def get_frame(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """获取一帧"""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None


class WebSocketManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_callbacks: List[Callable] = []
    
    async def connect(self, websocket: WebSocket):
        """接受WebSocket连接"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket连接已建立，当前连接数: {len(self.active_connections)}")
        
        # 调用连接回调
        for callback in self.connection_callbacks:
            try:
                await callback(websocket, "connect")
            except Exception as e:
                logger.error(f"连接回调执行失败: {e}")
    
    def disconnect(self, websocket: WebSocket):
        """断开WebSocket连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket连接已断开，当前连接数: {len(self.active_connections)}")
        
        # 调用断开回调
        for callback in self.connection_callbacks:
            try:
                asyncio.create_task(callback(websocket, "disconnect"))
            except Exception as e:
                logger.error(f"断开回调执行失败: {e}")
    
    async def broadcast(self, message: Dict):
        """广播消息到所有连接"""
        if not self.active_connections:
            return
        
        # 创建消息副本
        message_copy = json.dumps(message, ensure_ascii=False)
        
        # 并发发送消息
        tasks = []
        dead_connections = []
        
        for websocket in self.active_connections:
            task = asyncio.create_task(self._send_message(websocket, message_copy))
            tasks.append((websocket, task))
        
        # 等待所有发送完成
        for websocket, task in tasks:
            try:
                await task
            except Exception as e:
                logger.warning(f"发送消息失败: {e}")
                dead_connections.append(websocket)
        
        # 清理死连接
        for websocket in dead_connections:
            self.disconnect(websocket)
    
    async def _send_message(self, websocket: WebSocket, message: str):
        """发送单条消息"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            raise e
    
    def add_connection_callback(self, callback: Callable):
        """添加连接状态回调"""
        self.connection_callbacks.append(callback)


class RTSPStreamingService:
    """RTSP流处理服务"""
    
    def __init__(self, detector, tracker):
        self.detector = detector
        self.tracker = tracker
        self.stream_reader = None
        self.websocket_manager = WebSocketManager()
        self.running = False
        self.inference_task = None
        self.current_source = None
        
        # 统计信息
        self.stats = {
            "total_frames": 0,
            "total_detections": 0,
            "total_tracks": 0,
            "start_time": None,
            "fps": 0
        }
    
    async def start_streaming(self, source: str):
        """启动流处理"""
        if self.running:
            await self.stop_streaming()
        
        self.current_source = source
        self.stream_reader = VideoStreamReader(source)
        self.stream_reader.start()
        
        self.running = True
        self.stats["start_time"] = time.time()
        self.stats["total_frames"] = 0
        
        # 启动推理任务
        self.inference_task = asyncio.create_task(self._inference_loop())
        
        logger.info(f"RTSP流处理已启动: {source}")
    
    async def stop_streaming(self):
        """停止流处理"""
        self.running = False
        
        if self.inference_task:
            self.inference_task.cancel()
            try:
                await self.inference_task
            except asyncio.CancelledError:
                pass
        
        if self.stream_reader:
            self.stream_reader.stop()
        
        logger.info("RTSP流处理已停止")
    
    async def _inference_loop(self):
        """推理循环"""
        while self.running:
            try:
                # 获取帧
                frame = self.stream_reader.get_frame(timeout=0.1)
                if frame is None:
                    await asyncio.sleep(0.01)
                    continue
                
                # 检测
                detections = self.detector.detect(frame)
                
                # 跟踪
                tracks = self.tracker.update(detections, frame.shape[:2])
                
                # 更新统计
                self.stats["total_frames"] += 1
                self.stats["total_detections"] += len(detections)
                self.stats["total_tracks"] += len(tracks)
                
                # 计算FPS
                if self.stats["start_time"]:
                    elapsed = time.time() - self.stats["start_time"]
                    if elapsed > 0:
                        self.stats["fps"] = self.stats["total_frames"] / elapsed
                
                # 绘制结果
                annotated_frame = self._draw_detections(frame, tracks)
                
                # 编码帧为JPEG
                _, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frame_data = buffer.tobytes()
                
                # 构建消息
                message = {
                    "type": "frame",
                    "timestamp": time.time(),
                    "frame_data": frame_data.hex(),  # 转换为十六进制字符串
                    "detections": detections,
                    "tracks": tracks,
                    "stats": self.stats.copy()
                }
                
                # 广播消息
                await self.websocket_manager.broadcast(message)
                
                # 控制帧率
                await asyncio.sleep(0.03)  # ~30 FPS
                
            except Exception as e:
                logger.error(f"推理循环错误: {e}")
                await asyncio.sleep(0.1)
    
    def _draw_detections(self, frame: np.ndarray, tracks: List[Dict]) -> np.ndarray:
        """在帧上绘制检测结果"""
        annotated_frame = frame.copy()
        
        for track in tracks:
            bbox = track["bbox"]
            track_id = track["track_id"]
            label = track["label"]
            conf = track["conf"]
            
            x1, y1, x2, y2 = map(int, bbox)
            
            # 绘制边界框
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # 绘制标签
            label_text = f"ID:{track_id} {label} {conf:.2f}"
            label_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(annotated_frame, (x1, y1 - label_size[1] - 10), 
                         (x1 + label_size[0], y1), (0, 255, 0), -1)
            cv2.putText(annotated_frame, label_text, (x1, y1 - 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
        
        return annotated_frame
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self.stats.copy()


class RTSPWebApp:
    """RTSP Web应用"""
    
    def __init__(self, streaming_service: RTSPStreamingService):
        self.streaming_service = streaming_service
        self.app = None
        self._create_app()
    
    def _create_app(self):
        """创建FastAPI应用"""
        if not FASTAPI_AVAILABLE:
            logger.error("FastAPI不可用，无法创建Web应用")
            return
        
        self.app = FastAPI(title="YOLO RTSP Streaming Service")
        
        # 静态文件服务
        try:
            self.app.mount("/static", StaticFiles(directory="static"), name="static")
        except:
            pass  # 静态文件目录不存在时忽略
        
        # 路由
        self._setup_routes()
    
    def _setup_routes(self):
        """设置路由"""
        
        @self.app.get("/")
        async def root():
            return HTMLResponse(self._get_index_html())
        
        @self.app.get("/health")
        async def health():
            return {"status": "ok", "streaming": self.streaming_service.running}
        
        @self.app.post("/start")
        async def start_streaming(source: str):
            try:
                await self.streaming_service.start_streaming(source)
                return {"status": "started", "source": source}
            except Exception as e:
                return JSONResponse(
                    {"status": "error", "error": str(e)}, 
                    status_code=500
                )
        
        @self.app.post("/stop")
        async def stop_streaming():
            try:
                await self.streaming_service.stop_streaming()
                return {"status": "stopped"}
            except Exception as e:
                return JSONResponse(
                    {"status": "error", "error": str(e)}, 
                    status_code=500
                )
        
        @self.app.get("/stats")
        async def get_stats():
            return self.streaming_service.get_stats()
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.streaming_service.websocket_manager.connect(websocket)
            try:
                while True:
                    # 保持连接活跃
                    data = await websocket.receive_text()
                    await websocket.send_text(f"ack: {data}")
            except WebSocketDisconnect:
                self.streaming_service.websocket_manager.disconnect(websocket)
            except Exception as e:
                logger.error(f"WebSocket错误: {e}")
                self.streaming_service.websocket_manager.disconnect(websocket)
    
    def _get_index_html(self) -> str:
        """获取主页HTML"""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>YOLO RTSP Streaming</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .video-container { text-align: center; margin: 20px 0; }
        .controls { margin: 20px 0; }
        .stats { background: #f5f5f5; padding: 10px; border-radius: 5px; margin: 10px 0; }
        input[type="text"] { width: 300px; padding: 5px; }
        button { padding: 8px 16px; margin: 5px; cursor: pointer; }
        #videoFrame { max-width: 100%; border: 1px solid #ccc; }
    </style>
</head>
<body>
    <div class="container">
        <h1>YOLO RTSP Streaming Service</h1>
        
        <div class="controls">
            <input type="text" id="sourceInput" placeholder="输入RTSP地址或视频文件路径" 
                   value="rtsp://admin:password@192.168.1.10:554/stream">
            <button onclick="startStreaming()">开始流</button>
            <button onclick="stopStreaming()">停止流</button>
        </div>
        
        <div class="stats" id="stats">
            <h3>统计信息</h3>
            <div id="statsContent">等待连接...</div>
        </div>
        
        <div class="video-container">
            <img id="videoFrame" src="" alt="视频流">
        </div>
    </div>

    <script>
        let ws = null;
        let statsInterval = null;

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            ws = new WebSocket(wsUrl);
            
            ws.onopen = function() {
                console.log('WebSocket连接已建立');
                updateStats();
                statsInterval = setInterval(updateStats, 1000);
            };
            
            ws.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'frame') {
                        // 显示视频帧
                        const frameData = data.frame_data;
                        const binaryData = new Uint8Array(frameData.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
                        const blob = new Blob([binaryData], {type: 'image/jpeg'});
                        const url = URL.createObjectURL(blob);
                        document.getElementById('videoFrame').src = url;
                        
                        // 更新统计信息
                        updateStatsDisplay(data.stats);
                    }
                } catch (e) {
                    console.log('收到文本消息:', event.data);
                }
            };
            
            ws.onclose = function() {
                console.log('WebSocket连接已关闭');
                if (statsInterval) {
                    clearInterval(statsInterval);
                }
            };
            
            ws.onerror = function(error) {
                console.error('WebSocket错误:', error);
            };
        }

        function startStreaming() {
            const source = document.getElementById('sourceInput').value;
            if (!source) {
                alert('请输入视频源');
                return;
            }
            
            fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({source: source})
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'started') {
                    console.log('流处理已启动');
                } else {
                    alert('启动失败: ' + data.error);
                }
            })
            .catch(error => {
                console.error('启动错误:', error);
                alert('启动失败: ' + error);
            });
        }

        function stopStreaming() {
            fetch('/stop', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                console.log('流处理已停止');
            })
            .catch(error => {
                console.error('停止错误:', error);
            });
        }

        function updateStats() {
            fetch('/stats')
            .then(response => response.json())
            .then(data => {
                updateStatsDisplay(data);
            })
            .catch(error => {
                console.error('获取统计信息失败:', error);
            });
        }

        function updateStatsDisplay(stats) {
            const statsContent = document.getElementById('statsContent');
            statsContent.innerHTML = `
                <p>总帧数: ${stats.total_frames || 0}</p>
                <p>总检测数: ${stats.total_detections || 0}</p>
                <p>总跟踪数: ${stats.total_tracks || 0}</p>
                <p>FPS: ${stats.fps ? stats.fps.toFixed(2) : 0}</p>
                <p>运行时间: ${stats.start_time ? Math.floor((Date.now()/1000 - stats.start_time)) : 0}秒</p>
            `;
        }

        // 页面加载时连接WebSocket
        window.onload = function() {
            connectWebSocket();
        };
    </script>
</body>
</html>
        """
    
    def run(self, host: str = "0.0.0.0", port: int = 8080):
        """运行Web应用"""
        if not self.app:
            logger.error("Web应用未初始化")
            return
        
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)
