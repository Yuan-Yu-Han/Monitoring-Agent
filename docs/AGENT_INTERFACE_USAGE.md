# Agent Interface 接口层使用指南

## 概述

`AgentInterface` 是监控系统的核心接口层，实现了以下职责：

✓ **统一入口**：`process(input, context)` - 处理所有类型的输入  
✓ **维护对话记忆**：`ConversationMemory` - 保存和管理对话历史  
✓ **构建 Prompt**：融合事件上下文 + 对话历史 + 额外信息  
✓ **解析响应**：从 Agent 输出中提取关键信息  
✓ **评估严重程度**：智能判断事件严重性和是否升级  

## 核心数据结构

### 1. MessageRole（消息角色）
```python
class MessageRole(Enum):
    USER = "user"           # 用户消息
    ASSISTANT = "assistant" # Agent 响应
    SYSTEM = "system"       # 系统消息
```

### 2. ConversationMessage（对话消息）
```python
@dataclass
class ConversationMessage:
    role: MessageRole                   # 消息角色
    content: str                        # 消息内容
    timestamp: datetime                 # 时间戳
    metadata: Dict[str, Any]            # 元数据（可选）
```

### 3. ConversationMemory（对话记忆）
```python
@dataclass
class ConversationMemory:
    messages: List[ConversationMessage] # 消息列表
    max_history: int = 20               # 最多保留 20 条消息
    
    # 关键方法：
    add_message(role, content, metadata)        # 添加消息
    get_recent_messages(n=5)                    # 获取最近 N 条消息
    get_conversation_context()                  # 获取上下文字符串
    get_messages_for_context()                  # 获取 LLM 格式的消息列表
    clear()                                     # 清空记忆
```

### 4. AgentResponse（Agent 响应）
```python
@dataclass
class AgentResponse:
    success: bool           # 是否成功
    message: str            # Agent 的文本回复
    severity: str           # 严重程度: info, warning, critical
    should_escalate: bool   # 是否应该升级报警
    metadata: Dict[str, Any] # 额外元数据
```

## 使用示例

### 初始化

```python
from src.monitoring_system.agent_interface import AgentInterface, ConversationMemory
from src.hybrid_monitoring_agent import HybridMonitoringAgent
from config import GlobalConfig

# 初始化 Agent
config = GlobalConfig()
agent = HybridMonitoringAgent(config)

# 创建接口（自动创建对话记忆）
interface = AgentInterface(
    agent=agent,
    enable_memory=True  # 启用对话记忆
)

# 或者使用现有的对话记忆
memory = ConversationMemory(max_history=30)
interface = AgentInterface(
    agent=agent,
    conversation_memory=memory,
    enable_memory=True
)
```

### 方式 1：事件驱动

```python
# 直接处理事件
response = interface.handle_event(detection_event)

# 或使用统一入口
response = interface.process({
    "type": "event",
    "event": detection_event
})

# 使用响应
if response.success:
    print(f"分析结果: {response.message}")
    print(f"严重程度: {response.severity}")  # info, warning, critical
    if response.should_escalate:
        # 触发升级报警
        trigger_alert(response)
```

### 方式 2：用户驱动

```python
# 处理用户查询
response = interface.handle_user_query(
    query="检测到什么了？",
    context={
        "current_state": "ALARM",
        "alarm_count": 3,
        "recent_events": [event1, event2, event3]
    },
    image=None  # 可选的图像数据
)

# 或使用统一入口
response = interface.process({
    "type": "query",
    "query": "检测到什么了？",
    "image": numpy_array  # 可选
}, context={...})

# 使用响应
if response.success:
    print(response.message)
```

### 对话记忆管理

```python
# 添加自定义消息
interface.conversation_memory.add_message(
    MessageRole.USER,
    "用户说的话",
    metadata={"source": "web_interface"}
)

# 获取对话上下文
context = interface.conversation_memory.get_conversation_context()
print(context)  # 输出格式化的对话历史

# 获取最近的 5 条消息
recent_msgs = interface.conversation_memory.get_recent_messages(n=5)

# 获取 LLM 格式的消息列表
messages_for_llm = interface.conversation_memory.get_messages_for_context()

# 清空记忆
interface.clear_memory()
```

### Prompt 构建详解

#### 事件驱动的 Prompt

```
===== 对话历史 =====
用户: 最近有异常吗?
Assistant: 暂时未检测到异常

===== 当前监控事件 =====
状态: 检测到异常事件
时间: 2026-02-03 15:30:45
检测到的目标:
- fire (置信度: 0.95)
- smoke (置信度: 0.87)

===== 最近事件历史 =====
1. [15:25:10] suspect - 1 个检测
2. [15:28:30] alarm - 2 个检测
3. [15:30:45] alarm - 2 个检测

===== 分析要求 =====
请分析以下内容:
1. 这是什么情况？
2. 严重程度如何？（低/中/高）
3. 是否需要立即处理？
4. 建议的后续行动

请提供简洁的分析结果。
```

#### 用户驱动的 Prompt

```
===== 对话上下文 =====
用户: 最近有异常吗?
Assistant: 暂时未检测到异常

===== 最近监控事件 =====
1. [15:28:30] 状态: alarm, 检测: 2 个目标
2. [15:30:45] 状态: alarm, 检测: 2 个目标

===== 额外上下文 =====
当前状态: ALARM
今日报警次数: 5

===== 用户问题 =====
现在是什么情况，需要采取什么措施？
```

## 响应严重程度评估

系统根据 Agent 的响应关键词自动评估严重程度：

| 严重程度 | 关键词 | 自动升级 |
|---------|-------|---------|
| critical | 危险、紧急、严重、火灾、爆炸、critical、danger | 是 |
| warning | 警告、注意、异常、可疑、warning | 仅在 ALARM 状态下 |
| info | 其他 | 否 |

## 工作流示例

```python
# 完整的监控流程示例

interface = AgentInterface(agent, enable_memory=True)

# 1. 检测到火焰事件
event = DetectionEvent(
    timestamp=datetime.now(),
    state=MonitorState.ALARM,
    detections=[{"class": "fire", "confidence": 0.95}],
    frame=current_frame,
    confidence=0.95
)

# 2. 事件驱动分析
response = interface.handle_event(event)

# 3. 根据响应采取行动
if response.severity == "critical":
    print(f"警报: {response.message}")
    if response.should_escalate:
        # 触发升级报警（电话、短信等）
        trigger_escalation(response)

# 4. 用户查询最近情况
user_response = interface.handle_user_query(
    query="刚才发生了什么？",
    context={
        "current_state": "ALARM",
        "recent_events": [event]
    }
)

print(f"Agent 说: {user_response.message}")

# 5. 继续对话
follow_up = interface.handle_user_query(
    query="需要采取什么措施？"
)

print(f"建议: {follow_up.message}")

# 6. 清理
interface.clear_memory()
```

## 高级特性

### 自定义 Agent 类型

`AgentInterface` 支持多种 Agent 类型：

```python
# LangChain Agent（带 invoke 方法）
agent1 = LangChainAgent(...)
interface1 = AgentInterface(agent1)

# 自定义 Agent（实现 chat 方法）
class CustomAgent:
    def chat(self, prompt):
        return "Agent 的响应"

agent2 = CustomAgent()
interface2 = AgentInterface(agent2)

# 或实现 run 方法
class AnotherAgent:
    def run(self, prompt):
        return "Agent 的响应"

agent3 = AnotherAgent()
interface3 = AgentInterface(agent3)
```

### 图像处理

Agent Interface 自动处理图像编码：

```python
import cv2
import numpy as np

# 读取图像
frame = cv2.imread("image.jpg")

# 传递给 Agent Interface
response = interface.handle_user_query(
    query="分析这张图片中的安全隐患",
    image=frame  # 自动转为 Base64
)
```

### 事件历史查询

```python
# 查看最近的事件
recent_events = interface.last_events  # List[DetectionEvent]

# 清空事件历史
interface.clear_events()

# 访问最新事件的元数据
if interface.last_events:
    latest = interface.last_events[-1]
    print(f"最后检测: {latest.timestamp}")
    print(f"目标数: {len(latest.detections)}")
    print(f"置信度: {latest.confidence}")
```

## 上下文信息格式

传递给 `handle_user_query()` 的 `context` 支持以下字段：

```python
context = {
    "recent_events": [event1, event2, event3],  # 最近的事件列表
    "current_state": "ALARM",                   # 当前系统状态
    "alarm_count": 5,                           # 今日报警次数
    "duration": "2 小时 30 分钟",               # 事件持续时间
}
```

## 最佳实践

1. **启用对话记忆**：在多轮交互中启用内存以保持上下文一致性
2. **定期清理记忆**：为了避免 token 溢出，定期清理长时间的对话记忆
3. **设置合理的历史长度**：根据 Agent 的 token 限制调整 `max_history`
4. **监控响应严重程度**：检查 `should_escalate` 标志决定是否升级
5. **保存对话日志**：将 `ConversationMemory.messages` 保存以便审计
6. **优雅降级**：当 Agent 失败时，返回有意义的错误信息而不是崩溃

## 常见问题

### Q: 对话记忆会无限增长吗？
A: 不会。`ConversationMemory` 的 `max_history` 参数限制了消息数量。默认为 20 条，超过时会自动删除最旧的消息。

### Q: 如何禁用对话记忆？
A: 在初始化时设置 `enable_memory=False`：
```python
interface = AgentInterface(agent, enable_memory=False)
```

### Q: Agent 调用失败会怎样？
A: `handle_event()` 和 `handle_user_query()` 会返回 `success=False` 的 `AgentResponse`，包含错误信息。

### Q: 如何自定义严重程度评估？
A: 重写 `_parse_agent_response()` 方法或继承 `AgentInterface` 类。
