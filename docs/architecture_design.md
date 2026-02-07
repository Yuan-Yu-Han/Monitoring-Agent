# 监控系统架构设计对话记录

> 日期: 2026-02-02
> 主题: HybridMonitoringAgent、系统分层架构、Memory/RAG设计、文件夹结构规划

---

## 1. HybridMonitoringAgent 的完整设计

### 用户提问
谢谢你 实际上我只有一个hybrid monitoring agent，baseagent和mock agent都是测试用的，不过我hybrid monitoring agent都还没写完，我觉得这个类里应该还有别的函数要写，你觉得我的系统和agent的层次架构到底是什么样的

### 架构分析

#### 🏗️ 系统 vs Agent 分层架构

```
┌──────────────────────────────────────────────────────────┐
│ 应用层 (Application Layer)                               │
│ - run_interactive.py: 用户交互入口                         │
│ - InteractiveMonitoring: 前后台协调                       │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│ 系统层 (System Layer) - MonitoringSystem                  │
│ 职责：                                                     │
│ ✓ 管理 RTSP 流读取、YOLO 检测、事件触发                    │
│ ✓ 状态机（idle → suspect → alarm）                       │
│ ✓ 决定何时调用 Agent（事件驱动）                           │
│ ✓ 维护系统级的统计（帧数、事件数）                         │
│ ✗ 不关心 Agent 的内部逻辑                                 │
│ ✗ 不维护对话记忆                                          │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│ 接口层 (Interface Layer) - AgentInterface                │
│ 职责：                                                     │
│ ✓ 统一入口：process(input_type, data)                     │
│ ✓ 维护对话记忆 (ConversationMemory)                       │
│ ✓ 构建 prompt（融合事件上下文 + 对话历史）                │
│ ✓ 解析 Agent 响应                                         │
│ ✓ 评估严重程度和是否升级                                  │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│ Agent 层 (Agent Layer) - HybridMonitoringAgent            │
│ 职责：                                                     │
│ ✓ 提供 invoke() 方法（接收 prompt + context）             │
│ ✓ 管理 LangChain 工具链和工作流                           │
│ ✓ 调用 LLM 模型                                           │
│ ✓ 使用内置工具（detect_image, draw_bboxes等）            │
│ ✗ 不维护对话记忆                                          │
│ ✗ 不关心监控系统的业务逻辑                                │
└──────────────────────────────────────────────────────────┘
```

#### 📝 各层的具体实现

**MonitoringSystem（系统层）**

```python
class MonitoringSystem:
    """只关心监控逻辑"""
    
    def run(self):
        """主循环"""
        while self.is_running:
            frame = self.frame_extractor.read_frame()
            detections = self.detector.detect(frame)
            
            # 状态机判断
            should_call_agent, event = self.event_trigger.process_detection(detections, frame)
            
            if should_call_agent:
                # ✅ 直接调用接口，不关心内部细节
                response = self.agent_interface.process(
                    input_type="event",
                    data=event
                )
                self._handle_agent_response(response)
    
    def handle_user_query(self, query: str):
        """处理用户查询"""
        # ✅ 调用接口，融合当前系统状态
        response = self.agent_interface.process(
            input_type="query",
            data={
                "query": query,
                "current_state": self.event_trigger.get_state(),
                "recent_events": self.event_trigger.get_event_history(limit=3)
            }
        )
        return response
```

**AgentInterface（接口层）**

```python
class AgentInterface:
    """唯一入口 - 管理交互、记忆、prompt构建"""
    
    def __init__(self, agent: HybridMonitoringAgent):
        self.agent = agent
        self.memory = ConversationMemory()
    
    def process(self, input_type: str, data: Any) -> AgentResponse:
        """唯一入口"""
        
        if input_type == "event":
            prompt = self._build_event_prompt(data)
        else:  # "query"
            prompt = self._build_query_prompt(data)
            
        # 加入历史
        full_prompt = self._inject_memory(prompt)
        
        # 调用 Agent
        response = self.agent.invoke({
            "messages": [{"role": "user", "content": full_prompt}]
        })
        
        # 保存记忆
        self.memory.add_turn(input_type, data, response)
        
        # 解析响应
        return self._parse_response(response)
    
    def _inject_memory(self, prompt: str) -> str:
        """融合对话历史"""
        context = self.memory.get_context()
        if context:
            return f"背景信息：\n{context}\n\n{prompt}"
        return prompt
    
    def _parse_response(self, response: str) -> AgentResponse:
        """解析并评估"""
        # 关键词判断严重程度
        # 决定是否升级
        # 返回 AgentResponse
        pass
```

**HybridMonitoringAgent（Agent层）**

```python
class HybridMonitoringAgent:
    """LangChain Agent - 纯粹的 AI 推理层"""
    
    def __init__(self, config: GlobalConfig):
        self.config = config
        self.model = ChatOpenAI(...)
        self.tools = [detect_image, safe_parse_json, draw_bboxes]
        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            state_schema=DetectionState,
            checkpointer=InMemorySaver(),
            system_prompt=load_prompt("system_prompt")
        )
    
    def invoke(self, input_data: Dict, config: Dict = None) -> str:
        """
        纯粹的调用接口
        
        Args:
            input_data: {"messages": [{"role": "user", "content": prompt}]}
            config: {"configurable": {"thread_id": "..."}}
        """
        response = self.agent.invoke(input_data, config or {})
        return self._extract_text(response)
    
    def _extract_text(self, response) -> str:
        """从 LangChain 响应中提取文本"""
        # 处理 AIMessage 或 dict 响应
        pass
```

#### 🎯 HybridMonitoringAgent 还需要写的函数

基于架构，应该添加以下方法：

```python
class HybridMonitoringAgent:
    
    def __init__(self, config: GlobalConfig):
        """已有✓"""
        pass
    
    def invoke(self, input_data, config=None) -> str:
        """已有✓ - 核心方法"""
        pass
    
    # ========== 新增方法 ==========
    
    def set_system_prompt(self, prompt: str):
        """动态设置系统提示词"""
        # 重新初始化 agent
        pass
    
    def add_tool(self, tool):
        """动态添加工具"""
        pass
    
    def clear_memory(self):
        """清空 LangGraph 的内存状态"""
        # 用于重新开始新的对话线程
        pass
    
    def get_supported_tools(self) -> List[str]:
        """返回支持的工具列表"""
        return [t.name for t in self.tools]
    
    def _extract_text(self, response) -> str:
        """提取响应文本的辅助方法"""
        # 处理各种响应格式
        pass
```

#### 📊 信息流示意

```
用户输入
  ↓
run_interactive.py (chat_loop)
  ↓
MonitoringSystem.handle_user_query()
  ↓
AgentInterface.process(input_type="query", data={...})
  ↓
[1] 加载对话记忆
[2] 构建完整 prompt（+ 历史 + 上下文）
[3] 调用 HybridMonitoringAgent.invoke()
[4] 解析响应、评估严重程度
[5] 保存到记忆
[6] 返回 AgentResponse
  ↓
run_interactive.py 显示结果
```

---

## 2. Memory 和 RAG 的位置设计

### 用户提问
你觉得我的memory和rag到底应该实现在哪

### 设计方案

#### 📍 Memory vs RAG 的位置

```
┌─────────────────────────────────────┐
│ AgentInterface (接口层)              │
│                                      │
│ ✅ Memory (对话记忆)                 │
│    - 维护用户 ↔ Agent 的对话历史    │
│    - 构建 prompt 时注入上下文        │
│                                      │
│ ✅ 系统级 RAG (监控事件库)           │
│    - 检索过去的异常事件              │
│    - 检索系统规则、告警阈值          │
│    - 作为 prompt 的一部分注入        │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ HybridMonitoringAgent (Agent层)     │
│                                      │
│ ✅ Agent 级 RAG (作为 Tool)          │
│    - 作为 LangChain Tool 集成        │
│    - Agent 在推理中主动调用          │
│    - 检索特定领域知识库              │
│    - 例如：火灾特征库、安全规范等    │
└─────────────────────────────────────┘
```

#### 🎯 具体方案

**方案 A：Memory 在 AgentInterface**

```python
# src/frame/conversation_memory.py
class ConversationMemory:
    """对话记忆 - 维护对话历史"""
    
    def __init__(self, max_turns=10):
        self.turns: List[Dict] = []  # [{"user": "...", "agent": "...", "type": "event|query"}, ...]
    
    def add_turn(self, user_input: str, agent_output: str, input_type: str):
        """添加一个对话轮次"""
        self.turns.append({
            "user": user_input[:200],  # 截断长输入
            "agent": agent_output[:200],
            "type": input_type,
            "timestamp": datetime.now()
        })
        if len(self.turns) > self.max_turns:
            self.turns.pop(0)
    
    def get_context(self) -> str:
        """获取格式化的对话上下文"""
        if not self.turns:
            return ""
        
        lines = []
        for turn in self.turns[-3:]:  # 最近3轮
            lines.append(f"[{turn['type']}] 用户: {turn['user']}")
            lines.append(f"[{turn['type']}] 助手: {turn['agent']}\n")
        return "\n".join(lines)
    
    def clear(self):
        self.turns.clear()
```

**方案 B：系统级 RAG 在 AgentInterface**

```python
# src/frame/event_retriever.py
class EventRetriever:
    """检索系统事件历史和规则库"""
    
    def __init__(self, monitoring_system):
        self.monitoring_system = monitoring_system
    
    def retrieve_recent_events(self, limit=5) -> str:
        """检索最近的事件"""
        events = self.monitoring_system.event_trigger.get_event_history(limit=limit)
        
        lines = []
        for evt in events:
            lines.append(
                f"- [{evt.timestamp.strftime('%H:%M:%S')}] "
                f"{evt.state.value}: {len(evt.detections)} 个检测"
            )
        return "\n".join(lines) if lines else "无最近事件"
    
    def retrieve_rules(self, state: str) -> str:
        """检索告警规则"""
        rules = {
            "suspect": "连续检测2次以上触发suspect状态",
            "alarm": "连续检测5次以上触发alarm状态",
            "critical": "检测置信度>0.9且类型为fire/smoke"
        }
        return rules.get(state, "未知规则")
```

**方案 C：Agent 级 RAG 作为 Tool**

```python
# src/tools/knowledge_retriever.py
from langchain_core.tools import tool

@tool
def retrieve_fire_knowledge(query: str) -> str:
    """
    检索火灾识别知识库
    
    在分析图像时，Agent 可以调用这个 tool 来获取火灾特征信息
    """
    knowledge_base = {
        "火焰特征": "橙红色/黄色光源，形状不规则，有烟气伴随",
        "烟雾特征": "灰白色气体，快速流动，温度升高",
        "安全距离": "火源周围5米内为危险区域",
    }
    
    for key, value in knowledge_base.items():
        if query in key or key in query:
            return f"{key}: {value}"
    
    return "知识库中未找到相关信息"
```

**改进后的 AgentInterface**

```python
class AgentInterface:
    """统一入口 - 管理 Memory、系统级 RAG、和 Agent 调用"""
    
    def __init__(
        self, 
        agent: HybridMonitoringAgent,
        monitoring_system: MonitoringSystem = None
    ):
        self.agent = agent
        self.memory = ConversationMemory()
        
        # 系统级 RAG（可选）
        self.event_retriever = EventRetriever(monitoring_system) if monitoring_system else None
    
    def process(self, input_type: str, data: Any) -> AgentResponse:
        """唯一入口"""
        
        # 1. 构建基础 prompt
        if input_type == "event":
            prompt = self._build_event_prompt(data)
        else:
            prompt = self._build_query_prompt(data)
        
        # 2. 注入对话记忆
        prompt = self._inject_memory(prompt)
        
        # 3. 注入系统级 RAG（事件历史、规则等）
        if self.event_retriever:
            prompt = self._inject_system_rag(prompt, data)
        
        # 4. 调用 Agent（Agent 可以通过 tool 自动检索 Agent 级 RAG）
        response = self.agent.invoke({
            "messages": [{"role": "user", "content": prompt}]
        })
        
        # 5. 保存到 memory
        self.memory.add_turn(prompt[:100], response[:100], input_type)
        
        # 6. 解析响应
        return self._parse_response(response)
    
    def _inject_memory(self, prompt: str) -> str:
        """融合对话历史"""
        context = self.memory.get_context()
        if context:
            return f"【对话历史】\n{context}\n\n【当前请求】\n{prompt}"
        return prompt
    
    def _inject_system_rag(self, prompt: str, data: Any) -> str:
        """融合系统级 RAG"""
        rag_context = []
        
        # 检索相关事件
        recent = self.event_retriever.retrieve_recent_events(limit=5)
        rag_context.append(f"【最近事件】\n{recent}")
        
        # 检索相关规则
        if isinstance(data, dict) and "state" in data:
            rules = self.event_retriever.retrieve_rules(data["state"])
            rag_context.append(f"\n【相关规则】\n{rules}")
        
        rag_text = "\n".join(rag_context)
        return f"{rag_text}\n\n{prompt}"
```

**HybridMonitoringAgent 集成 Agent 级 RAG**

```python
class HybridMonitoringAgent:
    
    def __init__(self, config: GlobalConfig):
        self.config = config
        self.model = ChatOpenAI(...)
        
        # 基础工具
        self.tools = [
            detect_image,
            safe_parse_json,
            draw_bboxes,
            retrieve_fire_knowledge,  # ✅ Agent 级 RAG
        ]
        
        self.agent = create_agent(
            model=self.model,
            tools=self.tools,  # ✅ Agent 可以自动调用 RAG tool
            ...
        )
    
    def invoke(self, input_data, config=None) -> str:
        """Agent 会在推理过程中自动决定是否调用 RAG tool"""
        pass
```

#### 📊 总结对比

| 功能 | 位置 | 用途 |
|------|------|------|
| **对话Memory** | AgentInterface | 维护对话历史，提供上下文 |
| **事件检索** | AgentInterface (EventRetriever) | 检索系统中的异常事件 |
| **规则库** | AgentInterface (EventRetriever) | 检索告警规则、阈值 |
| **知识库** | HybridMonitoringAgent (as Tool) | Agent 主动检索专业知识 |

#### 💡 三层 RAG 架构

```
AgentInterface
├─ Memory (对话记忆)
└─ EventRetriever (系统 RAG)
    ├─ 事件历史检索
    └─ 规则库检索

HybridMonitoringAgent
└─ Tools (包含 RAG Tool)
    ├─ detect_image
    ├─ draw_bboxes
    └─ retrieve_fire_knowledge (Agent 级 RAG) ✨
```

---

## 3. 项目文件夹架构重构

### 用户提问
你觉得我的项目代码文件夹的架构应该怎么样

### 建议的文件夹架构

```
Monitoring-Agent/
│
├── 📦 配置和入口
│   ├── config.py                    # 全局配置
│   ├── config.json                  # 配置文件
│   ├── main.py                      # CLI 入口
│   └── requirements.txt             # 依赖
│
├── 🎯 应用层 (Application Layer)
│   └── app/
│       ├── __init__.py
│       ├── interactive_ui.py        # 用户交互界面（从 run_interactive 重命名）
│       └── cli/                     # 命令行工具
│           ├── commands.py
│           └── __init__.py
│
├── 🔧 系统层 (System Layer)
│   └── monitoring/
│       ├── __init__.py
│       ├── core.py                  # MonitoringSystem（核心引擎）
│       ├── video/                   # 视频处理
│       │   ├── __init__.py
│       │   ├── rtsp_extractor.py    # RTSP 流读取
│       │   └── frame_processor.py   # 帧处理（如果有）
│       ├── detection/               # 检测相关
│       │   ├── __init__.py
│       │   ├── yolo_detector.py     # YOLO 模型
│       │   └── event_trigger.py     # 状态机/事件触发
│       └── output/                  # 输出处理
│           ├── __init__.py
│           ├── event_logger.py      # 事件保存
│           └── frame_saver.py       # 帧保存
│
├── 🤖 接口层 (Interface Layer)
│   └── agent_interface/
│       ├── __init__.py
│       ├── interface.py             # AgentInterface（唯一入口）
│       ├── memory/                  # 对话记忆
│       │   ├── __init__.py
│       │   └── conversation.py      # ConversationMemory
│       └── rag/                     # 检索增强生成
│           ├── __init__.py
│           ├── event_retriever.py   # 事件检索
│           ├── rule_retriever.py    # 规则检索
│           └── knowledge_base.py    # 知识库管理
│
├── 🧠 Agent 层 (Agent Layer)
│   └── agents/
│       ├── __init__.py
│       ├── hybrid_monitoring.py     # HybridMonitoringAgent
│       └── tools/                   # Agent Tools
│           ├── __init__.py
│           ├── vision_tools.py      # 视觉相关（detect_image, draw_bboxes）
│           ├── knowledge_tools.py   # 知识检索工具
│           ├── utility_tools.py     # 其他工具（JSON解析等）
│           └── custom_tools.py      # 自定义工具
│
├── 🛠️ 支持工具和工作流
│   └── workflow/
│       ├── __init__.py
│       ├── state.py                 # 工作流状态定义
│       ├── graph.py                 # 工作流图定义
│       └── nodes.py                 # 工作流节点
│
├── 🌐 流媒体服务（可选）
│   └── streaming/
│       ├── __init__.py
│       ├── server.py                # WebSocket 服务器
│       └── templates/
│           └── index.html
│
├── 📊 数据和输出
│   ├── inputs/                      # 输入数据
│   ├── outputs/
│   │   ├── logs/                    # 日志
│   │   ├── monitoring_output/       # 监控输出（帧、图片）
│   │   └── results/                 # 分析结果
│   ├── prompts/                     # 提示词模板
│   │   ├── system_prompt.txt
│   │   ├── event_prompt.txt
│   │   └── query_prompt.txt
│   └── models/                      # 模型文件
│       └── yolov8n.pt
│
├── 📝 脚本和工具
│   └── scripts/
│       ├── setup_config.py
│       ├── video_to_images.sh
│       ├── images_to_video.py
│       └── ...
│
├── 🧪 测试
│   └── tests/
│       ├── __init__.py
│       ├── test_monitoring.py
│       ├── test_agent_interface.py
│       ├── test_hybrid_agent.py
│       └── fixtures/
│           └── sample_frames/
│
├── 📚 文档
│   ├── README.md
│   ├── ARCHITECTURE.md              # 架构文档
│   ├── API.md                       # API 文档
│   └── docs/
│       ├── system_design.md
│       ├── agent_design.md
│       └── rag_design.md
│
└── 🔌 配置文件
    ├── .env
    ├── .env.example
    ├── .gitignore
    └── pyproject.toml
```

#### 📋 新增文件清单

需要创建/整理的文件：

```
app/
├── __init__.py                      # ✨ 新建
├── interactive_ui.py                # 🔄 从 run_interactive.py 改名
└── cli/
    ├── __init__.py                  # ✨ 新建
    └── commands.py                  # ✨ 新建

monitoring/
├── __init__.py                      # ✨ 新建
├── core.py                          # 🔄 MonitoringSystem 从 monitoring_system.py 移动
├── video/
│   ├── __init__.py                  # ✨ 新建
│   └── rtsp_extractor.py            # 🔄 从 monitoring_system 目录移动
├── detection/
│   ├── __init__.py                  # ✨ 新建
│   ├── yolo_detector.py             # 🔄 从 monitoring_system 目录移动
│   └── event_trigger.py             # 🔄 从 monitoring_system 目录移动
└── output/
    ├── __init__.py                  # ✨ 新建
    ├── event_logger.py              # ✨ 新建
    └── frame_saver.py               # ✨ 新建

agent_interface/
├── __init__.py                      # ✨ 新建
├── interface.py                     # 🔄 AgentInterface 重构
├── memory/
│   ├── __init__.py                  # ✨ 新建
│   └── conversation.py              # ✨ 新建
└── rag/
    ├── __init__.py                  # ✨ 新建
    ├── event_retriever.py           # ✨ 新建
    ├── rule_retriever.py            # ✨ 新建
    └── knowledge_base.py            # ✨ 新建

agents/
├── __init__.py                      # ✨ 新建
├── hybrid_monitoring.py             # 🔄 从 hybrid_monitoring_agent.py 改名
└── tools/
    ├── __init__.py                  # ✨ 新建
    ├── vision_tools.py              # 🔄 detect_image, draw_bboxes 从 detections.py 重组
    ├── knowledge_tools.py           # ✨ 新建
    ├── utility_tools.py             # 🔄 safe_parse_json 从 detections.py 重组
    └── custom_tools.py              # ✨ 新建（用户自定义工具）

tests/
├── __init__.py                      # ✨ 新建
├── test_monitoring.py               # ✨ 新建
├── test_agent_interface.py          # ✨ 新建
├── test_hybrid_agent.py             # ✨ 新建
└── fixtures/
    └── __init__.py                  # ✨ 新建

prompts/
├── system_prompt.txt                # 已有
├── event_prompt.txt                 # ✨ 新建
└── query_prompt.txt                 # ✨ 新建
```

#### 🔄 模块导入关系

```python
# app/interactive_ui.py
from monitoring.core import MonitoringSystem
from monitoring.detection.event_trigger import EventTrigger
from agent_interface.interface import AgentInterface

# monitoring/core.py
from monitoring.video.rtsp_extractor import RTSPFrameExtractor
from monitoring.detection.yolo_detector import YOLODetector
from monitoring.detection.event_trigger import EventTrigger
from monitoring.output.event_logger import EventLogger

# agent_interface/interface.py
from agents.hybrid_monitoring import HybridMonitoringAgent
from agent_interface.memory.conversation import ConversationMemory
from agent_interface.rag.event_retriever import EventRetriever

# agents/hybrid_monitoring.py
from agents.tools.vision_tools import detect_image, draw_bboxes
from agents.tools.knowledge_tools import retrieve_fire_knowledge
from agents.tools.utility_tools import safe_parse_json
```

#### 🎯 关键优势

| 方面 | 优势 |
|------|------|
| **清晰分层** | 按三层架构组织，职责明确 |
| **易于扩展** | 新工具、新提示词、新RAG易于添加 |
| **易于测试** | 每层都可单独测试 |
| **代码复用** | 工具、提示词、存储器都可复用 |
| **文档友好** | 文件夹结构本身就是文档 |
| **依赖清晰** | 每层只依赖下层，不交叉依赖 |

---

## 总结

这个对话记录涵盖了：

1. **系统分层架构** - 应用层 → 系统层 → 接口层 → Agent层
2. **HybridMonitoringAgent 的完整设计** - 包括所需的新增方法
3. **Memory 和 RAG 的分布设计** - 三层 RAG 架构
4. **文件夹结构重构方案** - 清晰的模块组织

这些设计目的是为了实现：
- ✅ 职责清晰（SRP - 单一职责原则）
- ✅ 易于扩展（OCP - 开放闭合原则）
- ✅ 易于测试（DIP - 依赖反转原则）
- ✅ 代码复用（DRY - 不重复原则）
