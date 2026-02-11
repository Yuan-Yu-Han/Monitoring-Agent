#!/bin/bash

# =========================
# 配置区
# =========================

# RTSP Server 地址（本地 RTSPServer）
SERVER_IP="127.0.0.1"

# RTSP 端口
RTSP_PORT=8554

# 流名称
STREAM_NAME="mystream"

# 本地视频文件路径
VIDEO_FILE="/home/yuan0165/yyh/Monitoring-Agent/src/streaming/fire.mp4"

# 静态编译 ffmpeg 路径
FFMPEG_BIN="/home/yuan0165/ffmpeg-7.0.2-amd64-static/ffmpeg"

# mediamtx 可执行文件路径（根据实际下载位置修改）
MEDIAMTX_BIN="/home/yuan0165/mediamtx_v1.15.6_linux_amd64/mediamtx"

# mediamtx 配置文件路径
MEDIAMTX_CONFIG="/home/yuan0165/mediamtx_v1.15.6_linux_amd64/mediamtx.yml"

# 创建日志目录
LOG_DIR="./logs/services/rtsp"
mkdir -p $LOG_DIR

# 生成带时间戳的日志文件名
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
MEDIAMTX_LOG="$LOG_DIR/mediamtx_$TIMESTAMP.log"
FFMPEG_LOG="$LOG_DIR/ffmpeg_$TIMESTAMP.log"

# =========================
# 检查依赖
# =========================

# 检查 ffmpeg
if [ ! -x "${FFMPEG_BIN}" ]; then
    echo "❌ 错误: 未找到可执行的 ffmpeg，请确认路径正确: ${FFMPEG_BIN}"
    exit 1
fi

# 检查 mediamtx
if [ ! -x "${MEDIAMTX_BIN}" ]; then
    echo "❌ 错误: 未找到可执行的 mediamtx，请确认路径正确: ${MEDIAMTX_BIN}"
    echo "请先从这里下载: https://github.com/bluenviron/mediamtx/releases"
    echo "下载后解压，并将 mediamtx 可执行文件放到脚本同目录"
    exit 1
fi

# =========================
# 启动 RTSP 服务器
# =========================

echo "🔧 启动 mediamtx RTSP 服务器..."
echo "📝 日志保存到: $MEDIAMTX_LOG"
"${MEDIAMTX_BIN}" "${MEDIAMTX_CONFIG}" > "$MEDIAMTX_LOG" 2>&1 &
MEDIAMTX_PID=$!
echo "✅ mediamtx 已启动 (PID: ${MEDIAMTX_PID})"
echo ""

# 等待服务器启动
echo "⏳ 等待 RTSP 服务器就绪..."
sleep 3

# 设置退出时清理函数
trap "echo ''; echo '🛑 停止 mediamtx...'; kill ${MEDIAMTX_PID} 2>/dev/null; exit" INT TERM EXIT

# =========================
# 推流
# =========================

echo "🚀 正在推送 RTSP 流到:"
echo "rtsp://${SERVER_IP}:${RTSP_PORT}/${STREAM_NAME}"
echo "📝 日志保存到: $FFMPEG_LOG"
echo ""

# 推流（循环播放）
"${FFMPEG_BIN}" -stream_loop -1 -re -i "${VIDEO_FILE}" \
  -c:v libx264 \
  -preset ultrafast \
  -tune zerolatency \
  -pix_fmt yuv420p \
  -f rtsp \
  rtsp://${SERVER_IP}:${RTSP_PORT}/${STREAM_NAME} \
  > "$FFMPEG_LOG" 2>&1
