# 日志目录结构

所有系统日志统一存放在此目录，按组件分类。

## 目录结构

```
logs/
├── vllm/           # vLLM 模型服务日志
│   └── vllm_server_YYYYMMDD_HHMMSS.log
├── rtsp/           # RTSP 流服务日志
│   ├── mediamtx_YYYYMMDD_HHMMSS.log
│   └── ffmpeg_YYYYMMDD_HHMMSS.log
└── agent/          # Agent 应用日志
    ├── cli_app_YYYYMMDD_HHMMSS.log
    ├── interactive_chat_YYYYMMDD_HHMMSS.log
    ├── monitoring_system_YYYYMMDD_HHMMSS.log
    ├── test_agent_YYYYMMDD_HHMMSS.log
    └── run_interactive_YYYYMMDD_HHMMSS.log
```

## 日志分类说明

### 1. vllm/ - 模型服务日志
- **vllm_server_*.log**: vLLM API 服务的启动和运行日志
- 包含模型加载、推理请求、响应等信息
- 脚本: `scripts/run_qwen_vl.sh`

### 2. rtsp/ - 视频流服务日志  
- **mediamtx_*.log**: RTSP 服务器日志
- **ffmpeg_*.log**: ffmpeg 推流日志
- 包含流的启动、连接、编码等信息
- 脚本: `scripts/run_rtsp.sh`

### 3. agent/ - Agent 应用日志
- **cli_app_*.log**: CLI 交互应用日志
- **interactive_chat_*.log**: 交互式对话日志
- **monitoring_system_*.log**: 监控系统主程序日志
- **test_agent_*.log**: Agent 接口测试日志
- **run_interactive_*.log**: 交互式监控运行日志
- 包含 Agent 对话、工具调用、事件处理等信息

## 日志文件命名规则

所有日志文件都使用时间戳命名：`{component}_{YYYYMMDD_HHMMSS}.log`

例如：
- `vllm_server_20260205_143022.log` - 2026年2月5日 14:30:22 启动的 vLLM 服务
- `cli_app_20260205_143025.log` - 2026年2月5日 14:30:25 启动的 CLI 应用

## 日志清理建议

日志文件会随时间累积，建议定期清理：

```bash
# 删除 7 天前的日志
find logs/ -name "*.log" -mtime +7 -delete

# 仅查看（不删除）7 天前的日志
find logs/ -name "*.log" -mtime +7 -ls
```

## 查看日志

```bash
# 实时查看最新的 vLLM 日志
tail -f logs/vllm/vllm_server_*.log

# 实时查看最新的 Agent 日志
tail -f logs/agent/cli_app_*.log

# 查看所有 RTSP 日志
ls -lh logs/rtsp/

# 搜索错误信息
grep -r "ERROR\|Exception" logs/
```
