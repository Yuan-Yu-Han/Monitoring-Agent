#!/bin/bash

OUTPUT_DIR="./outputs"
PID_FILE="$OUTPUT_DIR/vllm_server.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat $PID_FILE)
    echo "正在停止vLLM服务 (PID: $PID)..."
    
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        echo "vLLM服务已停止"
        rm $PID_FILE
    else
        echo "进程 $PID 不存在，可能已经停止"
        rm $PID_FILE
    fi
else
    echo "未找到PID文件，尝试通过进程名停止..."
    pkill -f "vllm.entrypoints.openai.api_server"
    echo "已尝试停止所有vLLM服务"
fi