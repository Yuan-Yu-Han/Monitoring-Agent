# Monitoring-Agent

## 快速开始

### 监控模式

```bash
python src/start_monitoring.py --rtsp rtsp://127.0.0.1:8554/mystream
```

### 监控 + 交互

```bash
python src/start_monitoring.py --rtsp rtsp://127.0.0.1:8554/mystream --interactive
```

## 入口说明

- `src/start_monitoring.py`：统一入口，支持监控与交互。

## Unified Entry

Run with no flags:

```bash
module load Miniconda3
source activate vllm
cd /home/yuan0165/yyh/Monitoring-Agent
python3 main.py
```

This starts:
- stream server (`5002`)
- dashboard API (`8010`)
- monitoring (`src/start_monitoring.py`)

If you also want to auto-start frontend dev:

```bash
export MAIN_RUN_FRONTEND_DEV=1
python3 main.py
```
