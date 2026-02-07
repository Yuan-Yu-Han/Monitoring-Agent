# Agent Interface 快速开始

## 5 分钟快速上手

### 安装和基础设置

```python
from src.monitoring_system.agent_interface import AgentInterface
from src.monitoring_system.event_trigger import DetectionEvent, MonitorState
from src.hybrid_monitoring_agent import HybridMonitoringAgent
from config import GlobalConfig
from datetime import datetime

# 1. 初始化 Agent
config = GlobalConfig()
agent = HybridMonitoringAgent(config)

# 2. 创建接口（只需一行！）
interface = AgentInterface(agent, enable_memory=True)
```

## 三种最常用的模式

### 模式 1: 处理检测事件 ⚡

当监控系统检测到事件时：

```python
# 创建检测事件
event = DetectionEvent(
    timestamp=datetime.now(),
    state=MonitorState.ALARM,
    detections=[
        {"class": "fire", "confidence": 0.95},
        {"class": "smoke", "confidence": 0.87}
    ],
    frame=None,  # 可选图像
    confidence=0.95
)

# 调用 Agent 进行分析
response = interface.handle_event(event)

# 使用响应
print(f"分析: {response.message}")
print(f"严重程度: {response.severity}")  # critical, warning, info

if response.should_escalate:
    # 触发升级（电话、短信等）
    send_alert(response.message)
```

### 模式 2: 回答用户问题 💬

用户提出问题时：

```python
# 用户提问
response = interface.handle_user_query(
    query="现在是什么情况？需要采取什么措施？",
    context={
        "current_state": "ALARM",
        "alarm_count": 3
    }
)

# 返回 Agent 的建议
print(f"Agent 的建议: {response.message}")
```

### 模式 3: 使用统一入口 🎯

同时支持事件和查询：

```python
# 可以处理任意类型的输入
result = interface.process(
    input_data={
        "type": "event",  # 或 "query"
        "event": event,   # 如果 type="event"
        # "query": "...",  # 如果 type="query"
    },
    context={...}  # 可选
)
```

## 常见场景

### 场景 1: 智能火灾监控系统

```python
def process_frame_with_fire_detection():
    # 检测到火焰
    event = DetectionEvent(
        timestamp=datetime.now(),
        state=MonitorState.ALARM,
        detections=[
            {"class": "fire", "confidence": 0.96},
            {"class": "smoke", "confidence": 0.92}
        ],
        frame=frame_data,  # 图像帧
        confidence=0.96
    )
    
    # Agent 分析（会自动加载历史事件和对话）
    response = interface.handle_event(event)
    
    # 高可信度的火焰检测 → 立即升级
    if response.severity == "critical" and response.should_escalate:
        trigger_emergency_protocol()  # 拉响警报、联系消防队等
    else:
        log_event(response.message)
```

### 场景 2: 多轮对话系统

```python
def interactive_monitoring():
    # 第 1 轮：用户问现在的状况
    response1 = interface.handle_user_query("现在怎么样？")
    print(f"Agent: {response1.message}")
    
    # 第 2 轮：用户询问具体事件
    response2 = interface.handle_user_query("刚才的报警是什么？")
    print(f"Agent: {response2.message}")  
    # 注意：Agent 会记得第 1 轮的内容，对话更连贯
    
    # 第 3 轮：用户请求建议
    response3 = interface.handle_user_query("需要采取什么措施？")
    print(f"Agent: {response3.message}")
```

### 场景 3: 事件驱动 + 用户查询混合

```python
def hybrid_workflow():
    # Step 1: 系统检测到异常事件
    event = DetectionEvent(...)
    event_response = interface.handle_event(event)
    
    # Step 2: 用户想了解更多细节
    user_response = interface.handle_user_query(
        query="这个事件是怎样的？",
        context={
            "current_state": event.state.value,
            "recent_events": [event]
        }
    )
    
    # Step 3: 获取建议
    advice_response = interface.handle_user_query(
        query="根据这个事件，需要做什么？"
        # 注意：对话记忆自动包含 Step 1 和 Step 2
    )
```

## 数据结构参考

### 检测事件

```python
from src.monitoring_system.event_trigger import DetectionEvent

event = DetectionEvent(
    timestamp=datetime.now(),           # 必需
    state=MonitorState.ALARM,           # 必需：IDLE, SUSPECT, ALARM
    detections=[                        # 必需
        {
            "class": "fire",            # 检测类别
            "confidence": 0.95,         # 置信度 (0-1)
            "bbox": [x1, y1, x2, y2]   # 边界框（可选）
        }
    ],
    frame=numpy_array,                  # 图像（可选）
    confidence=0.95,                    # 整体置信度
    description="检测到火焰"           # 描述（可选）
)
```

### 上下文信息

```python
context = {
    "recent_events": [event1, event2],  # 最近的事件
    "current_state": "ALARM",           # 系统状态
    "alarm_count": 5,                   # 报警次数
    "duration": "30分钟",               # 持续时间
}
```

### Agent 响应

```python
response = interface.handle_event(event)

# 响应包含：
response.success          # bool: 是否成功
response.message          # str: Agent 的分析
response.severity         # str: "critical" | "warning" | "info"
response.should_escalate  # bool: 是否升级
response.metadata         # dict: 额外信息
```

## 对话记忆管理

### 启用/禁用

```python
# 启用记忆（默认）
interface = AgentInterface(agent, enable_memory=True)

# 禁用记忆（如果不需要对话连贯性）
interface = AgentInterface(agent, enable_memory=False)
```

### 查看记忆

```python
# 获取最近 5 条消息
recent = interface.conversation_memory.get_recent_messages(n=5)
for msg in recent:
    print(f"{msg.role.value}: {msg.content[:50]}...")

# 获取格式化的对话上下文
context = interface.conversation_memory.get_conversation_context()
print(context)
```

### 清理记忆

```python
# 清空所有对话记忆（开始新的会话）
interface.clear_memory()

# 清空事件历史
interface.clear_events()
```

## 常见问题解答

### Q: 对话记忆会占用多少空间？
A: 默认最多 20 条消息，通常小于 1MB。每条消息包括：角色、内容、时间戳和元数据。

### Q: Agent 响应需要多长时间？
A: 取决于 Agent 模型。LLM 通常需要 1-10 秒，具体时间根据模型和硬件而定。

### Q: 如何处理 Agent 失败的情况？
A: 检查 `response.success`。失败时会返回包含错误信息的响应，不会抛出异常。

### Q: 可以同时使用多个接口实例吗？
A: 可以，但每个实例有独立的内存。如果需要共享记忆，可以传入相同的 `ConversationMemory` 对象。

### Q: 如何处理图像？
A: 直接传递 OpenCV 的 numpy array。接口会自动编码为 Base64。

### Q: 严重程度评估准确吗？
A: 基于关键词匹配，对于明确的危险情况（如"火灾"）很准确。对于复杂情况，可能需要自定义评估逻辑。

## 下一步

- 📖 [详细使用指南](./AGENT_INTERFACE_USAGE.md)
- 🏗️ [架构设计文档](./ARCHITECTURE.md)
- 🧪 [测试脚本](./test_agent_interface.py)
- 💻 运行演示：`python3 test_agent_interface.py`

## 更新日志

### v1.0 (2026-02-03)

✨ **新特性**
- ✅ 统一入口 `process()` 方法
- ✅ 完整的对话记忆系统
- ✅ 智能 Prompt 构建（融合历史和上下文）
- ✅ 自动严重程度评估
- ✅ 多种 Agent 类型支持

🐛 **修复**
- 修复了语法错误（elif 位置）
- 改进了错误处理

📚 **文档**
- 添加完整的使用指南
- 添加架构设计文档
- 添加测试脚本和示例
