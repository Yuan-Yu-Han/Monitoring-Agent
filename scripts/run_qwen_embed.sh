#!/bin/bash

#SBATCH --output=/dev/null
#SBATCH --error=/dev/null

MODEL="/projects/yuan0165/Qwen3-VL-Embedding-2B"
PORT=8001

LOG_DIR="./logs/services/qwen_embed"
mkdir -p "$LOG_DIR"

OUTPUT_DIR="./outputs"
mkdir -p "$OUTPUT_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/vllm_embed_server_$TIMESTAMP.log"

echo "启动 vLLM Embedding 服务，日志保存到: $LOG_FILE"

python3 -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --served-model-name text-embedding-3-small \
    --runner pooling \
    --convert embed \
    --host 0.0.0.0 \
    --port "$PORT" \
    --tensor-parallel-size 1 \
    --max-model-len 4096 \
    --dtype float16 \
    --gpu-memory-utilization 0.3 \
    > "$LOG_FILE" 2>&1


echo $! > "$OUTPUT_DIR/vllm_embed_server.pid"
echo "vLLM Embedding 服务已启动，PID: $!"
echo "日志文件: $LOG_FILE"
echo "PID文件: $OUTPUT_DIR/vllm_embed_server.pid"
