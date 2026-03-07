#!/bin/bash

#SBATCH --output=/dev/null
#SBATCH --error=/dev/null

# ============================================================
# 统一启动脚本：调用已有的服务脚本
# ============================================================

# 创建日志目录和文件，重定向所有输出
LOG_DIR="./backend/logs/services/startup"
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
    SCRIPT_DIR="$PROJECT_ROOT/backend/scripts"
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
fi

# 脚本路径
QWEN_VL_SCRIPT="$SCRIPT_DIR/run_qwen_vl.sh"
QWEN_EMBED_SCRIPT="$SCRIPT_DIR/run_qwen_embed.sh"
RTSP_SCRIPT="$SCRIPT_DIR/run_rtsp.sh"

echo "调试信息："
echo "  SCRIPT_DIR: $SCRIPT_DIR"
echo "  PROJECT_ROOT: $PROJECT_ROOT"
echo "  QWEN_VL_SCRIPT: $QWEN_VL_SCRIPT"
echo "  QWEN_EMBED_SCRIPT: $QWEN_EMBED_SCRIPT"
echo "  RTSP_SCRIPT: $RTSP_SCRIPT"
echo ""

# ============================================================
# 解析参数：支持任意组合启动
#   默认：不传参数 -> 启动全部
#   可选：--vl --embed --rtsp
# ============================================================
START_VL=false
START_EMBED=false
START_RTSP=false

if [ "$#" -eq 0 ]; then
    START_VL=true
    START_EMBED=false
    START_RTSP=true
else
    for arg in "$@"; do
        case "$arg" in
            --vl)
                START_VL=true
                ;;
            --embed)
                START_EMBED=true
                ;;
            --rtsp)
                START_RTSP=true
                ;;
            -h|--help)
                echo "用法: $0 [--vl] [--embed] [--rtsp]"
                echo "  不传参数默认启动全部服务"
                exit 0
                ;;
            *)
                echo "❌ 未知参数: $arg"
                echo "用法: $0 [--vl] [--embed] [--rtsp]"
                exit 1
                ;;
        esac
    done
fi

if ! $START_VL && ! $START_EMBED && ! $START_RTSP; then
    echo "❌ 未选择任何服务，退出"
    exit 1
fi

# 检查脚本是否存在（仅检查要启动的服务）
if $START_VL && [ ! -f "$QWEN_VL_SCRIPT" ]; then
    echo "❌ 未找到 vLLM 启动脚本: $QWEN_VL_SCRIPT"
    exit 1
fi

if $START_EMBED && [ ! -f "$QWEN_EMBED_SCRIPT" ]; then
    echo "❌ 未找到 Embedding 启动脚本: $QWEN_EMBED_SCRIPT"
    exit 1
fi

if $START_RTSP && [ ! -f "$RTSP_SCRIPT" ]; then
    echo "❌ 未找到 RTSP 启动脚本: $RTSP_SCRIPT"
    exit 1
fi

# 确保脚本可执行
$START_VL && chmod +x "$QWEN_VL_SCRIPT"
$START_EMBED && chmod +x "$QWEN_EMBED_SCRIPT"
$START_RTSP && chmod +x "$RTSP_SCRIPT"

# ============================================================
# 启动服务（后台/前台）
# ============================================================

cd "$PROJECT_ROOT"

if $START_VL; then
    echo "[1/3] 启动 vLLM API 服务..."
    bash "$QWEN_VL_SCRIPT" &
    VLLM_PID=$!
    echo "✅ vLLM 服务已启动 (PID: $VLLM_PID)"
    echo "⏳ 等待 vLLM 服务就绪（约 60 秒）..."
    sleep 60
    echo ""
fi

if $START_EMBED; then
    echo "[2/3] 启动 Embedding 服务..."
    bash "$QWEN_EMBED_SCRIPT" &
    EMBED_PID=$!
    echo "✅ Embedding 服务已启动 (PID: $EMBED_PID)"
    echo "⏳ 等待 Embedding 服务就绪（约 15 秒）..."
    sleep 15
    echo ""
fi

if $START_RTSP; then
    echo "[3/3] 启动 RTSP 流服务..."
fi

# 设置清理函数
cleanup() {
    echo ""
    echo "🛑 正在停止所有服务..."
    
    # 停止 vLLM（会自动停止其子进程）
    if [ ! -z "$VLLM_PID" ] && ps -p $VLLM_PID > /dev/null 2>&1; then
        echo "   停止 vLLM 服务 (PID: $VLLM_PID)..."
        kill $VLLM_PID 2>/dev/null
    fi

    if [ ! -z "$EMBED_PID" ] && ps -p $EMBED_PID > /dev/null 2>&1; then
        echo "   停止 Embedding 服务 (PID: $EMBED_PID)..."
        kill $EMBED_PID 2>/dev/null
    fi
    
    # RTSP 脚本自己会处理清理
    
    echo "✅ 所有服务已停止"
    exit 0
}

trap cleanup INT TERM EXIT

# 运行 RTSP 脚本（前台）
if $START_RTSP; then
    bash "$RTSP_SCRIPT"
else
    echo "未选择 RTSP，保持运行以便后台服务不退出"
    wait
fi

