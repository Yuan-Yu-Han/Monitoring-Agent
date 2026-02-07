# 监控系统架构说明

## 三层架构关系

```
┌─────────────────────────────────────────────────────────────────┐
│                     应用层 (Application Layer)                   │
│                    interactive_chat.py                           │
│  - 真实用户交互界面（REPL 循环）                                  │
│  - 对话历史管理                                                   │
│  - 特殊命令处理 (/history, /clear, /exit)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │ 使用
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     接口层 (Interface Layer)                      │
│                    agent_interface.py                            │
│  - 统一的 Agent 调用接口                                          │
│  - 对话记忆管理 (ConversationMemory)                             │
│  - Prompt 构建（融合事件 + 历史）                                │
│  - 响应解析和严重程度评估                                        │
│  - 事件驱动和用户驱动两种模式                                    │
└────────────────────────────┬────────────────────────────────────┘
                             │ 使用
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   模型层 (Model Layer)                           │
│               hybrid_monitoring_agent.py                         │
│  - 初始化 LangChain Agent (create_agent)                         │
│  - 管理工具集 (detect_image, safe_parse_json, draw_bboxes)      │
│  - 提供 invoke() 方法给接口层调用                                │
│  - 内部维护状态和消息循环                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 详细说明

### 1. **HybridMonitoringAgent** (模型层)
**文件**: `src/hybrid_monitoring_agent.py`

**职责**:
- 创建并维护 LangChain Agent 实例（基于 `create_agent` API）
- 管理可用的工具集：
  - `detect_image` - 图像检测
  - `safe_parse_json` - JSON 解析
  - `draw_bboxes` - 绘制检测框
- 提供 `invoke(input_text, chat_history=None, config=None)` 方法

**关键代码**:
```python
class HybridMonitoringAgent:
    def __init__(self, config: GlobalConfig):
        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            checkpointer=InMemorySaver(),
            system_prompt=load_prompt("system_prompt")
        )
    
    def invoke(self, input_text, chat_history=None, config=None):
        # 转发到底层 agent.invoke()
        result = self.agent.invoke({"messages": messages}, config=config)
        # 提取响应文本返回
```

**特点**:
- ✅ 直接与 LangChain Agent 交互
- ✅ 支持工具调用循环
- ✅ 使用 InMemorySaver 作为检查点存储

---

### 2. **AgentInterface** (接口层)
**文件**: `src/agent_interface.py`

**职责**:
- 为上层应用提供**统一的 Agent 调用接口**
- 维护**对话记忆** (ConversationMemory)
- 构建**上下文感知的 Prompt**
  - 融合对话历史
  - 融合事件上下文
  - 融合用户查询
- **两种调用模式**:
  1. **事件驱动** `handle_event(event)` - 响应检测事件
  2. **用户驱动** `handle_user_query(query, context)` - 响应用户问题
- 解析 Agent 响应、评估严重程度、判断是否升级报警

**关键方法**:
```python
class AgentInterface:
    def process(self, input_data, context=None) -> AgentResponse:
        # 统一入口，根据 input_data["type"] 分发
        
    def handle_event(self, event: DetectionEvent) -> AgentResponse:
        # 事件驱动：当监控事件触发时调用
        
    def handle_user_query(self, query: str, context=None) -> AgentResponse:
        # 用户驱动：当用户提问时调用
        
    def _invoke_agent(self, prompt, image_data=None, config=None) -> str:
        # 调用底层 HybridMonitoringAgent.invoke()
```

**关键特性**:
- ✅ 保持对话历史（最多 20 条消息）
- ✅ 保持事件历史（最多 5 个事件）
- ✅ 自动评估严重程度（info/warning/critical）
- ✅ 决定是否升级报警

---

### 3. **InteractiveChat** (应用层)
**文件**: `interactive_chat.py` (或 `monitoring_guardian.py`)

**职责**:
- 提供**交互式 REPL 界面**给最终用户
- 获取用户输入并调用 AgentInterface
- 管理和显示对话历史
- 处理特殊命令

**关键方法**:
```python
class InteractiveChat:
    def run(self):
        # 交互式循环：输入 → 处理 → 输出
        
    def _handle_user_query(self, query: str):
        # 调用 self.interface.handle_user_query()
        
    def _show_history(self):
        # 显示完整的对话和事件历史
        
    def _clear_history(self):
        # 清空所有历史记录
```

**特点**:
- ✅ REPL 交互循环
- ✅ 支持特殊命令 (`/history`, `/clear`, `/exit`)
- ✅ 完整的对话历史展示
- ✅ 用户友好的输出格式

---

## 数据流向

### 用户查询流程

```
用户输入 "最近有什么异常情况吗?"
    ▼
InteractiveChat._handle_user_query()
    ▼
AgentInterface.handle_user_query()
    ├─ 构建 Prompt（融合对话历史 + 事件上下文）
    ├─ 调用 _invoke_agent(prompt, config)
    │    ▼
    │ HybridMonitoringAgent.invoke()
    │    ▼
    │ LangChain create_agent 返回的 Agent
    │    ▼
    │ 返回 Agent 响应文本
    ├─ 解析响应，评估严重程度
    └─ 返回 AgentResponse 对象
    ▼
InteractiveChat 显示响应给用户
    ▼
更新对话历史
```

---

## 消息和状态流

### 对话记忆流向

```
用户问题 "检测到什么？"
    ▼
AgentInterface.conversation_memory.add_message(
    role=USER,
    content="检测到什么？"
)
    ▼
Agent 处理并返回响应
    ▼
AgentInterface.conversation_memory.add_message(
    role=ASSISTANT,
    content="检测到火焰..."
)
    ▼
下一次用户提问时，Prompt 会包含前面的对话历史
```

### 事件历史流向

```
监控系统检测到事件
    ▼
AgentInterface.handle_event(event)
    ▼
self.last_events.append(event)
    ▼
构建 Prompt 时包含事件历史
    ▼
后续用户查询时可以参考这些事件
```

---

## 关键交互点

### 1. HybridMonitoringAgent ↔ AgentInterface

```python
# AgentInterface 调用 HybridMonitoringAgent
def _invoke_agent(self, prompt, image_data=None, config=None) -> str:
    if hasattr(self.agent, 'invoke'):
        result = self.agent.invoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config=config
        )
```

**参数说明**:
- `prompt`: 构建好的提示词（包含上下文）
- `config`: LangGraph 配置，包含 `thread_id` 用于检查点管理
- 返回值: Agent 生成的文本响应

### 2. AgentInterface ↔ InteractiveChat

```python
# InteractiveChat 调用 AgentInterface
response = self.interface.handle_user_query(
    query,
    context={
        "recent_events": self.interface.last_events,
        "current_state": "MONITORING"
    }
)
```

**返回值**: `AgentResponse` 对象，包含:
- `success`: 是否成功
- `message`: 响应文本
- `severity`: 严重程度 (info/warning/critical)
- `should_escalate`: 是否需要升级

---

## 完整工作流示例

```
1. 用户启动 interactive_chat.py
   → InteractiveChat 创建实例
   → 初始化 HybridMonitoringAgent
   → 初始化 AgentInterface
   → 进入交互循环

2. 用户输入: "火灾情况如何？"
   → InteractiveChat 获取输入
   → 调用 AgentInterface.handle_user_query()
   
3. AgentInterface 处理:
   → 读取对话历史
   → 读取事件历史
   → 融合成完整的 Prompt
   → 调用 HybridMonitoringAgent.invoke(prompt)
   
4. HybridMonitoringAgent 处理:
   → 转发到 create_agent 返回的 Agent
   → Agent 调用相关工具（detect_image 等）
   → 返回分析结果
   
5. AgentInterface 后处理:
   → 解析 Agent 响应
   → 检测关键词评估严重程度
   → 存储到对话记忆
   → 返回 AgentResponse
   
6. InteractiveChat 显示:
   → 打印 Agent 的回答
   → 显示严重程度
   → 更新本地历史
   → 提示用户继续输入

7. 用户输入 "/history":
   → InteractiveChat._show_history()
   → 显示完整的对话和事件历史
   → 继续循环
```

---

## 层级特点总结

| 层级 | 文件 | 职责 | 特点 |
|-----|------|------|------|
| **应用层** | interactive_chat.py | 用户交互 | REPL、命令、历史展示 |
| **接口层** | agent_interface.py | Agent 统一接口 | 记忆、Prompt构建、响应解析 |
| **模型层** | hybrid_monitoring_agent.py | LLM Agent 管理 | 工具调用、状态管理 |

---

## 为什么这样设计？

### ✅ 关注点分离 (Separation of Concerns)
- 应用层只关心用户交互
- 接口层只关心 Agent 调用的统一性
- 模型层只关心 LLM 和工具的协作

### ✅ 易于扩展
- 可以轻松替换 HybridMonitoringAgent（如果有更好的 Agent）
- 可以轻松替换交互界面（CLI → Web API → 语音等）
- AgentInterface 保持不变

### ✅ 易于测试
- 可以用 MockAgent 测试 AgentInterface
- 可以用 MockInterface 测试 InteractiveChat
- 可以单独测试 HybridMonitoringAgent

### ✅ 可维护性强
- 每层职责清晰
- 接口定义明确
- 代码改动影响范围小
