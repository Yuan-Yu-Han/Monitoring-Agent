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
