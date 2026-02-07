# 事件驱动监控系统

## 🎯 核心设计理念

**Agent 不监听 RTSP，也不跑循环**  
**Agent 只在「事件发生」或「用户询问」时被调用**

## 📐 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      监控系统                            │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  路径 1: 事件驱动 (自动监控)                             │
│  ════════════════════════════════════                   │
│                                                          │
│  RTSP 流 → 抽帧 → YOLO → Event Trigger → Agent          │
│    │         │      │         │             │           │
│    │         │      │         │             └─→ 分析    │
│    │         │      │         └─→ 状态机判断             │
│    │         │      └─→ 目标检测                        │
│    │         └─→ 按 FPS 抽取                            │
│    └─→ 数据源                                           │
│                                                          │
│  路径 2: 用户驱动 (对话查询)                             │
│  ════════════════════════════════════                   │
│                                                          │
│  用户问题 → Agent (+ 上下文 + 图像)                      │
│      │         │                                        │
│      │         └─→ 回答问题                             │
│      └─→ "现在现场怎么样？"                              │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 🔧 核心组件

### 1. RTSP 帧抽取器 (`rtsp_extractor.py`)
- 连接 RTSP 流
- 按指定 FPS 抽取帧
- 断线自动重连

### 2. YOLO 检测器 (`yolo_detector.py`)
- 封装 Ultralytics YOLO
- 提供简化的检测接口
- 支持批量检测

### 3. 事件触发器 (`event_trigger.py`)
- **核心状态机**: Idle → Suspect → Alarm
- 只在状态转换时触发 Agent
- 避免重复调用

### 4. Agent 接口 (`agent_interface.py`)
- 事件驱动模式：分析检测事件
- 用户驱动模式：回答用户问题
- 统一的响应格式

### 5. 监控系统 (`monitoring_system.py`)
- 整合所有组件
- 主事件循环
- 事件回调机制

## 🚀 使用方法

### 方式 1: 纯监控模式

```bash
cd /home/yuan0165/yyh/Monitoring-Agent

# 启动监控（后台持续运行）
python src/run_monitoring.py \
    --rtsp rtsp://127.0.0.1:8554/mystream \
    --fps 5 \
    --model yolov8n.pt \
    --device cuda:0 \
    --target-classes fire smoke person
```

### 方式 2: 交互式模式（推荐）

```bash
# 启动交互式监控（监控 + 对话）
python src/run_interactive.py \
    --rtsp rtsp://127.0.0.1:8554/mystream \
    --fps 5 \
    --device cuda:0
```

启动后可以：
- 后台自动监控（状态变化时自动调用 Agent）
- 前台随时提问

示例对话：
```
👤 你: 现在现场怎么样？
🤖 Agent: 当前监控状态正常，未检测到异常...

👤 你: 刚才那是误报吗？
🤖 Agent: 根据最近的检测记录，刚才在 15:23:45...

👤 你: status
系统状态:
  当前状态: idle
  处理帧数: 1234
  事件次数: 3
```

## 📁 完整代码结构

```
yyh/Monitoring-Agent/src/
├── event_trigger.py      # 事件触发器（状态机）
├── rtsp_extractor.py     # RTSP 帧抽取器
├── yolo_detector.py      # YOLO 检测封装
├── agent_interface.py    # Agent 调用接口
├── monitoring_system.py  # 主监控系统
├── run_monitoring.py     # 启动脚本（纯监控）
└── run_interactive.py    # 启动脚本（交互式）
```

## ⚙️ 配置参数

### 事件触发阈值
- `suspect_threshold`: 连续检测多少次进入怀疑状态（默认 2）
- `alarm_threshold`: 连续检测多少次进入报警状态（默认 5）
- `idle_threshold`: 连续多少次无检测回到空闲（默认 10）

### 检测参数
- `target_classes`: 目标类别列表（如 ["fire", "smoke"]）
- `min_confidence`: 最小置信度阈值（默认 0.5）

### RTSP 参数
- `fps`: 抽帧频率（每秒多少帧，默认 5）
- `resize_width/height`: 是否缩放图像

## 🔥 典型使用场景

### 场景 1: 火灾监控

```python
config = MonitoringSystemConfig(
    rtsp_url="rtsp://127.0.0.1:8554/mystream",
    target_classes=["fire", "smoke"],
    suspect_threshold=2,    # 连续 2 次检测到 → 怀疑
    alarm_threshold=5,      # 连续 5 次检测到 → 报警
)
```

状态转换：
1. 检测到火焰 2 次 → **Suspect** → Agent 分析 ✅
2. 持续检测，达到 5 次 → **Alarm** → Agent 再次分析 ✅
3. 火焰消失，10 次无检测 → **Idle**

### 场景 2: 人员入侵监控

```python
config = MonitoringSystemConfig(
    rtsp_url="rtsp://192.168.1.100:554/stream",
    target_classes=["person"],
    suspect_threshold=3,
    alarm_threshold=10,
)
```

## 🎨 扩展示例

### 自定义事件回调

```python
def my_event_handler(event, agent_response):
    """自定义事件处理"""
    if agent_response.severity == "critical":
        # 发送短信报警
        send_sms(f"紧急: {agent_response.message}")
    
    # 记录到数据库
    db.save_event(event.to_dict())

system.set_event_callback(my_event_handler)
```

### 添加自定义 Agent

```python
from src.monitoring_system import MonitoringSystem

# 使用你自己的 Agent
my_agent = YourCustomAgent()
system = MonitoringSystem(config, my_agent)
```

## 📊 日志输出

系统会输出结构化日志：

```
2026-01-30 15:10:00 - INFO - 正在连接 RTSP 流: rtsp://127.0.0.1:8554/mystream
2026-01-30 15:10:01 - INFO - ✅ RTSP 流连接成功
2026-01-30 15:10:01 - INFO - 正在加载 YOLO 模型: yolov8n.pt
2026-01-30 15:10:03 - INFO - ✅ YOLO 模型加载成功
2026-01-30 15:10:03 - INFO - ✅ 监控系统初始化完成
2026-01-30 15:10:03 - INFO - 🚀 启动监控循环
2026-01-30 15:10:33 - INFO - 帧 30: 检测到 2 个目标, 状态: suspect
2026-01-30 15:10:35 - INFO - ⚡ 事件 1: 触发 Agent 分析
2026-01-30 15:10:37 - INFO - 📊 Agent 分析结果:
  - 严重程度: warning
  - 是否升级: False
  - 消息: 检测到可疑火焰...
```

## 🛠️ 依赖安装

```bash
pip install ultralytics opencv-python langchain langchain-openai
```

## 💡 关键优势

1. **Agent 不浪费资源**: 只在需要时调用
2. **状态机避免重复**: 同一状态不重复触发
3. **双路径设计**: 自动监控 + 手动查询
4. **易于扩展**: 所有组件独立，可替换
5. **生产就绪**: 异常处理、日志、资源清理

## 🚨 注意事项

1. **GPU 内存**: YOLO 持续运行会占用 GPU，建议使用小模型（yolov8n）
2. **网络稳定**: RTSP 流断开会自动重连
3. **Agent 超时**: 如果 Agent 响应慢，考虑异步调用
4. **存储空间**: 保存事件帧会占用磁盘空间

## 📝 TODO

- [ ] 支持多 RTSP 流同时监控
- [ ] Agent 异步调用（避免阻塞主循环）
- [ ] 事件历史数据库存储
- [ ] Web 界面查看监控状态
- [ ] 多种报警方式（邮件、短信、webhook）
