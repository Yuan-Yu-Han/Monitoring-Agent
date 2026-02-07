#!/bin/bash

#SBATCH --output=/dev/null
#SBATCH --error=/dev/null

# ============================================================
# 统一启动脚本：调用已有的服务脚本
# ============================================================

# 创建日志目录和文件，重定向所有输出
LOG_DIR="./logs/startup"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/run_all_services_$TIMESTAMP.log"

# 重定向 stdout 和 stderr 到日志文件，同时输出到控制台
exec > >(tee -a "$LOG_FILE")
exec 2>&1

echo "======================================"
echo "  监控系统统一启动脚本"
echo "======================================"
echo "📝 日志保存到: $LOG_FILE"
echo ""

# 获取脚本所在目录
# 在 SLURM 环境中使用 $SLURM_SUBMIT_DIR，否则使用 ${BASH_SOURCE[0]}
if [ -n "$SLURM_SUBMIT_DIR" ]; then
    PROJECT_ROOT="$SLURM_SUBMIT_DIR"
    SCRIPT_DIR="$PROJECT_ROOT/scripts"
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
fi

# 脚本路径
QWEN_VL_SCRIPT="$SCRIPT_DIR/run_qwen_vl.sh"
RTSP_SCRIPT="$SCRIPT_DIR/run_rtsp.sh"

echo "调试信息："
echo "  SCRIPT_DIR: $SCRIPT_DIR"
echo "  PROJECT_ROOT: $PROJECT_ROOT"
echo "  QWEN_VL_SCRIPT: $QWEN_VL_SCRIPT"
echo "  RTSP_SCRIPT: $RTSP_SCRIPT"
echo ""

# 检查脚本是否存在
if [ ! -f "$QWEN_VL_SCRIPT" ]; then
    echo "❌ 未找到 vLLM 启动脚本: $QWEN_VL_SCRIPT"
    exit 1
fi

if [ ! -f "$RTSP_SCRIPT" ]; then
    echo "❌ 未找到 RTSP 启动脚本: $RTSP_SCRIPT"
    exit 1
fi

# 确保脚本可执行
chmod +x "$QWEN_VL_SCRIPT"
chmod +x "$RTSP_SCRIPT"

# ============================================================
# 启动 vLLM API 服务（后台运行）
# ============================================================

echo "[1/2] 启动 vLLM API 服务..."
cd "$PROJECT_ROOT"
bash "$QWEN_VL_SCRIPT" &
VLLM_PID=$!

echo "✅ vLLM 服务已启动 (PID: $VLLM_PID)"
echo "⏳ 等待 vLLM 服务就绪（约 30 秒）..."
sleep 30
echo ""

# ============================================================
# 启动 RTSP 流服务（前台运行）
# ============================================================

echo "[2/2] 启动 RTSP 流服务..."
cd "$PROJECT_ROOT"

# 设置清理函数
cleanup() {
    echo ""
    echo "🛑 正在停止所有服务..."
    
    # 停止 vLLM（会自动停止其子进程）
    if [ ! -z "$VLLM_PID" ] && ps -p $VLLM_PID > /dev/null 2>&1; then
        echo "   停止 vLLM 服务 (PID: $VLLM_PID)..."
        kill $VLLM_PID 2>/dev/null
    fi
    
    # RTSP 脚本自己会处理清理
    
    echo "✅ 所有服务已停止"
    exit 0
}

trap cleanup INT TERM EXIT

# 运行 RTSP 脚本（前台）
bash "$RTSP_SCRIPT"

