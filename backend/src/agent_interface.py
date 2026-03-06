"""Agent 调用接口，提供事件驱动和用户驱动两种模式。"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import logging
import numpy as np
from enum import Enum
from pathlib import Path
import re
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from src.utils.runtime_env import configure_runtime_env

configure_runtime_env()

from config import load_config
from src.system.event_trigger import DetectionEvent, MonitorState
from src.utils.image_utils import encode_numpy_to_base64
from src.hybrid_monitoring_agent import build_hybrid_agent
from src.context_engine.memory.case_memory import CaseMemoryStore, CaseRecord, extract_labels
from src.context_engine.memory.vector_memory import VectorMemoryStore
from src.context_engine.orchestrator import build_context_bundle
from src.context_engine.retrievers import build_event_query

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """消息角色定义，统一对话角色标签。"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class ConversationMessage:
    """对话消息，包含角色、内容与元信息。"""
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，便于序列化与日志记录。"""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class ConversationMemory:
    """对话记忆管理，用于存取历史消息。"""
    messages: List[ConversationMessage] = field(default_factory=list)
    max_history: int = 10  # 最多保留 10 条消息（从 20 改为 10）
    
    def add_message(self, role: MessageRole, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """添加消息到记忆，并维护最大历史长度。"""
        message = ConversationMessage(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self.messages.append(message)
        
        # 如果超过最大历史，移除最旧的消息
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
    
    def get_recent_messages(self, n: int = 5) -> List[ConversationMessage]:
        """获取最近的 N 条消息，默认取最后 5 条。"""
        return self.messages[-n:] if n > 0 else self.messages
    
    def get_conversation_context(self) -> str:
        """获取对话上下文字符串，用于提示词拼接。"""
        if not self.messages:
            return ""
        
        context_parts = []
        for msg in self.get_recent_messages(5):  # 从 10 改为 5
            role_label = "用户" if msg.role == MessageRole.USER else "Assistant"
            context_parts.append(f"{role_label}: {msg.content}")
        
        return "\n".join(context_parts)
    
    def clear(self) -> None:
        """清空对话记忆。"""
        self.messages.clear()
    
    def get_messages_for_context(self) -> List[Dict[str, str]]:
        """获取消息列表用于 LLM 上下文，返回 role/content 格式。"""
        return [
            {"role": msg.role.value, "content": msg.content}
            for msg in self.messages[-5:]  # 从 10 改为 5
        ]


@dataclass
class AgentResponse:
    """Agent 响应对象，包含文本与严重性信息。"""
    success: bool
    message: str                    # Agent 生成的文本回复
    severity: str = "info"          # 严重程度: info, warning, critical
    should_escalate: bool = False   # 是否应该升级报警
    metadata: Dict[str, Any] = field(default_factory=dict) # 额外元数据


class AgentInterface:
    """Agent 调用接口，包含事件驱动与用户驱动两种模式。"""
    
    def __init__(
        self,
        agent: Optional[Any] = None,
        conversation_memory: Optional[ConversationMemory] = None,
        enable_memory: Optional[bool] = None,
        enable_retrieval: Optional[bool] = None,
        retrieval_targets: Optional[List[str]] = None,
    ):
        """初始化 Agent 接口，允许传入自定义 agent。"""
        self.config = load_config()
        self.agent = agent or build_hybrid_agent()
        self.conversation_memory = conversation_memory or ConversationMemory()
        cfg_agent = getattr(self.config, "agent", None)
        # Default behaviors (can be overridden per request via context flags)
        self.default_enable_memory = (
            bool(getattr(cfg_agent, "enable_memory", False))
            if enable_memory is None
            else bool(enable_memory)
        )

        cfg_targets = getattr(cfg_agent, "retrieval_targets", None)
        if isinstance(cfg_targets, list):
            cfg_targets_list = [
                str(t).strip().lower()
                for t in cfg_targets
                if str(t).strip().lower() in ("event", "chat", "knowledge")
            ]
        else:
            cfg_targets_list = []
        self.default_retrieval_targets = (
            cfg_targets_list
            if retrieval_targets is None
            else [
                str(t).strip().lower()
                for t in retrieval_targets
                if str(t).strip().lower() in ("event", "chat", "knowledge")
            ]
        )

        # Backward-compatible constructor switch: enable_retrieval True => all targets
        if enable_retrieval is True and not self.default_retrieval_targets:
            self.default_retrieval_targets = ["event", "chat", "knowledge"]
        if enable_retrieval is False:
            self.default_retrieval_targets = []

        self.expose_retrieval_debug = bool(getattr(cfg_agent, "expose_retrieval_debug", False))
        self.last_interrupt = None
        self.last_config = None
        self._stream_queue = None  # set during handle_user_query_stream

        # 事件上下文缓存（用于丰富提示词）
        self.last_events: List[DetectionEvent] = []
        self.max_event_history = 5

        # 事件计数器，用于生成唯一的thread_id
        self.event_counter = 0

        # 案例记忆库（持久化到 cache 目录）
        case_store_path = Path(self.config.cache_dir) / "event_cases.jsonl"
        self.case_memory = CaseMemoryStore(case_store_path)
        # 向量记忆（由 config.json rag.enable_vector_memory 控制）
        self.vector_memory: Optional[VectorMemoryStore] = None
        if getattr(self.config.rag, "enable_vector_memory", False):
            vector_store_path = Path(self.config.cache_dir) / "vector_memory"
            try:
                self.vector_memory = VectorMemoryStore(vector_store_path)
                logger.info("向量记忆已启用")
            except Exception as exc:
                logger.warning(f"向量记忆初始化失败，将仅使用JSONL记忆: {exc}")
    
    def process(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> AgentResponse:
        """统一入口：处理输入数据并分发到对应路径。"""
        input_type = input_data.get("type", "query")
        
        if input_type == "event":
            event = input_data.get("event")
            if event is None:
                return AgentResponse(
                    success=False,
                    message="错误：event 类型输入缺少 'event' 字段",
                    severity="error"
                )
            return self.handle_event(event)
        
        elif input_type == "query":
            query = input_data.get("query", "")
            image = input_data.get("image")
            return self.handle_user_query(query, context, image)
        
        else:
            return AgentResponse(
                success=False,
                message=f"未知的输入类型: {input_type}",
                severity="error"
            )
    
    def handle_event(self, event: DetectionEvent, tool_args: Optional[Dict[str, Any]] = None) -> AgentResponse:
        """事件驱动入口，用于监控事件触发处理。支持 tool_args 传递给 Agent 工具。"""
        try:
            logger.info(f"Agent 处理事件: {event.state.value}")
            # 保存事件到历史
            self.last_events.append(event)
            if len(self.last_events) > self.max_event_history:
                self.last_events = self.last_events[-self.max_event_history:]
            # 构建提示词（融合事件上下文 + 对话历史）
            prompt = self._build_event_prompt(event)

            # 使用唯一的thread_id，避免历史累积导致上下文超限
            self.event_counter += 1
            thread_id = f"event_{self.event_counter}"

            # 合并 tool_args 到 config['configurable']
            config = {"configurable": {"thread_id": thread_id}}
            if tool_args:
                config["configurable"].update(tool_args)
            # 调用 Agent
            response = self._invoke_agent(
                prompt,
                config=config,
                stream=True
            )
            # 添加到对话记忆
            if self.enable_memory:
                self.conversation_memory.add_message(
                    MessageRole.USER,
                    f"[事件触发] {event.state.value}",
                    metadata=event.to_dict()
                )
                self.conversation_memory.add_message(
                    MessageRole.ASSISTANT,
                    response
                )
            # 解析 Agent 响应并评估严重性
            agent_response = self._parse_agent_response(response, event)
            self._remember_event_case(event, agent_response)
            logger.info(
                f"Agent 响应: severity={agent_response.severity}, "
                f"escalate={agent_response.should_escalate}"
            )
            return agent_response
        except Exception as e:
            logger.error(f"Agent 处理事件失败: {e}", exc_info=True)
            return AgentResponse(
                success=False,
                message=f"Agent 处理失败: {str(e)}",
                severity="error"
            )
    
    def handle_user_query(self, query: str, context: Optional[Dict[str, Any]] = None, image: Optional[np.ndarray] = None) -> AgentResponse:
        """用户驱动入口，用于处理用户查询。"""
        try:
            logger.info(f"Agent 处理用户查询: {query}")
            ctx = context or {}
            enable_conversation_memory = bool(ctx.get("enable_memory", self.default_enable_memory))

            # 对寒暄/自我介绍请求走快速路径，避免每次都触发检索路由导致首句响应慢。
            if self._is_greeting_or_intro(query):
                fast_reply = (
                    "您好，我是火灾与安防监控专业助手（SafeGuard Fire Assistant）。"
                    "我可以进行火情风险研判、监控事件分析、历史案例对比，并给出处置建议。"
                )
                if enable_conversation_memory:
                    self.conversation_memory.add_message(MessageRole.USER, query, metadata={"image": image is not None})
                    self.conversation_memory.add_message(MessageRole.ASSISTANT, fast_reply)
                return AgentResponse(success=True, message=fast_reply, severity="info")
            
            # 添加用户消息到对话记忆
            if enable_conversation_memory:
                self.conversation_memory.add_message(
                    MessageRole.USER,
                    query,
                    metadata={"image": image is not None}
                )
            
            # 构建提示词（融合对话历史 + 事件上下文 + 用户查询）
            prompt = self._build_user_prompt(query, ctx)
            
            # 调用 Agent
            response = self._invoke_agent(
                prompt,
                config={"configurable": {"thread_id": "user_query"}},
                stream=True
            )
            
            # 添加 Assistant 消息到对话记忆
            if enable_conversation_memory:
                self.conversation_memory.add_message(
                    MessageRole.ASSISTANT,
                    response
                )
            
            # 解析严重程度
            severity = self._parse_severity_from_response(response)

            # 将用户对话写入案例记忆库，支持后续检索复用
            self._remember_user_case(query, response, severity, context)
            
            return AgentResponse(
                success=True,
                message=response,
                severity=severity
            )
            
        except Exception as e:
            logger.error(f"Agent 处理用户查询失败: {e}", exc_info=True)
            return AgentResponse(
                success=False,
                message=f"处理失败: {str(e)}",
                severity="error"
            )

    def handle_user_query_stream(self, query: str, context, event_queue) -> None:
        """Streaming version: puts typed events into event_queue, then a final 'done'/'error' event."""
        import io
        import sys

        self._stream_queue = event_queue

        # Redirect stdout so tool print() output is captured as 'tool_output' events
        original_stdout = sys.stdout

        class ToolCapture(io.TextIOBase):
            def write(self_, s):  # noqa: N805
                if isinstance(s, str) and s.strip():
                    event_queue.put({"type": "tool_output", "content": s})
                return len(s) if s else 0
            def flush(self_):
                pass

        sys.stdout = ToolCapture()
        try:
            resp = self.handle_user_query(query, context)
            event_queue.put({"type": "done", "message": resp.message, "severity": resp.severity})
        except Exception as exc:
            event_queue.put({"type": "error", "message": str(exc)})
        finally:
            sys.stdout = original_stdout
            self._stream_queue = None

    def _is_greeting_or_intro(self, query: str) -> bool:
        q = query.strip().lower()
        if not q:
            return False
        # 纯寒暄/身份询问才走快速路径，含任务关键词的不触发
        task_keywords = ["检测", "分析", "查询", "告警", "图片", "视频", "fire", "smoke", "detect", "报告", "风险", "帮我", "帮忙"]
        if any(kw in q for kw in task_keywords):
            return False
        pure_greetings = {"你好", "您好", "hi", "hello", "你是谁", "介绍下你自己", "自我介绍", "hey"}
        if q in pure_greetings:
            return True
        return False
    
    def _build_event_prompt(self, event: DetectionEvent) -> str:
        """构建事件分析提示词（精简版，避免上下文超限）。"""
        state_desc = {
            MonitorState.SUSPECT: "检测到可疑情况",
            MonitorState.ALARM: "检测到异常事件",
            MonitorState.IDLE: "恢复正常"
        }

        detection_info = "\n".join([
            f"- {det.get('class', '未知')} (置信度: {det.get('confidence', 0):.2f})"
            for det in event.detections
        ])

        prompt_parts = []

        # 添加当前事件信息（精简版）
        prompt_parts.append("===== 监控事件 =====")
        prompt_parts.append(f"状态: {state_desc.get(event.state, event.state.value)}")
        prompt_parts.append(f"时间: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

        # 添加 event_id（关键！让Agent知道如何找到图片）
        event_id = getattr(event, 'event_id', None)
        if event_id:
            prompt_parts.append(f"事件ID: {event_id}")

        prompt_parts.append(f"检测目标: {detection_info if detection_info else '无'}")

        # Layer 1+2: 先做意图识别，再按计划检索 event/chat/knowledge
        retrieval_query = build_event_query(event)
        targets = list(self.default_retrieval_targets or [])
        enable_retrieval = bool(targets)
        enable_event_mem = "event" in targets
        enable_chat_mem = "chat" in targets
        enable_knowledge = "knowledge" in targets

        if enable_retrieval:
            bundle = build_context_bundle(
                query=retrieval_query,
                context_kind="event",
                case_memory=self.case_memory,
                vector_memory=self.vector_memory,
                labels=extract_labels(event.detections),
                top_k=3,
                use_llm_router=True,
                enable_event_memory=enable_event_mem,
                enable_chat_memory=enable_chat_mem,
                enable_knowledge_memory=enable_knowledge,
            )

            if (self.config.debug or self.expose_retrieval_debug):
                prompt_parts.append(f"\n===== 检索路由（调试） =====")
                prompt_parts.append(
                    f"use_event_memory={bundle.plan.use_event_memory}, "
                    f"use_chat_memory={bundle.plan.use_chat_memory}, "
                    f"use_knowledge_memory={bundle.plan.use_knowledge_memory}, "
                    f"days={bundle.plan.days if bundle.plan.days else '-'}, "
                    f"reason={bundle.plan.reason}"
                )

            if enable_event_mem and bundle.event_memory:
                prompt_parts.append("\n===== 相关事件记录（参考） =====")
                prompt_parts.append(bundle.event_memory)
            if enable_chat_mem and bundle.chat_memory:
                prompt_parts.append("\n===== 相关对话记录（参考） =====")
                prompt_parts.append(bundle.chat_memory)
            if enable_knowledge and bundle.knowledge_memory:
                prompt_parts.append("\n===== 相关知识片段（参考） =====")
                prompt_parts.append(bundle.knowledge_memory)

        prompt_parts.append("\n===== 任务 =====")
        if event_id:
            prompt_parts.append(f"1. 使用 find_image 工具并传入 event_id='{event_id}' 来查找事件图片")
            prompt_parts.append("2. 使用 detect_image 工具分析图片内容")
            prompt_parts.append("3. 结合相似案例与RAG知识，给出简洁的风险评估和处置建议")
        else:
            prompt_parts.append("请分析当前情况并给出简洁评估。")

        return "\n".join(prompt_parts)
    
    def _build_user_prompt(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """构建用户查询提示词，融合对话与事件上下文。"""
        prompt_parts = []
        ctx = context or {}
        
        # 添加对话历史（只取最近 3 条）
        enable_conversation_memory = bool(ctx.get("enable_memory", self.default_enable_memory))
        if enable_conversation_memory:
            history = self.conversation_memory.get_conversation_context()
            if history:
                prompt_parts.append("===== 对话上下文 =====")
                prompt_parts.append(history)
                prompt_parts.append("")
        
        # 添加最近的监控事件（只取最近 1 条）
        if self.last_events:
            prompt_parts.append("===== 最近监控事件 =====")
            for i, evt in enumerate(self.last_events[-1:], 1):
                prompt_parts.append(
                    f"{i}. [{evt.timestamp.strftime('%H:%M:%S')}] "
                    f"状态: {evt.state.value}, 检测: {len(evt.detections)} 个目标"
                )
            prompt_parts.append("")
        
        # 添加用户查询
        prompt_parts.append("===== 用户问题 =====")
        prompt_parts.append(query)

        # Unified request flag: retrieval_targets
        req_targets = ctx.get("retrieval_targets", None)
        if req_targets is None:
            # Backward-compatible request flags:
            if ctx.get("enable_retrieval") is True:
                req_targets = ["event", "chat", "knowledge"]
            elif ctx.get("enable_retrieval") is False:
                req_targets = []
            else:
                # Legacy per-source flags
                legacy = []
                if ctx.get("enable_event_memory_retrieval") is True:
                    legacy.append("event")
                if ctx.get("enable_chat_memory_retrieval") is True:
                    legacy.append("chat")
                if ctx.get("enable_knowledge_memory") is True:
                    legacy.append("knowledge")
                req_targets = legacy if legacy else self.default_retrieval_targets

        if not isinstance(req_targets, list):
            req_targets = []
        targets = [
            str(t).strip().lower()
            for t in req_targets
            if str(t).strip().lower() in ("event", "chat", "knowledge")
        ]
        enable_retrieval = bool(targets)
        enable_event_mem = "event" in targets
        enable_chat_mem = "chat" in targets
        enable_knowledge = "knowledge" in targets

        if enable_retrieval:
            # Layer 1+2: 先做意图识别，再按计划检索 event/chat/knowledge
            bundle = build_context_bundle(
                query=query,
                context_kind="user",
                case_memory=self.case_memory,
                vector_memory=self.vector_memory,
                labels=None,
                top_k=3,
                use_llm_router=True,
                enable_event_memory=enable_event_mem,
                enable_chat_memory=enable_chat_mem,
                enable_knowledge_memory=enable_knowledge,
            )

            if (self.config.debug or self.expose_retrieval_debug):
                prompt_parts.append("")
                prompt_parts.append("===== 检索路由（调试） =====")
                prompt_parts.append(
                    f"use_event_memory={bundle.plan.use_event_memory}, "
                    f"use_chat_memory={bundle.plan.use_chat_memory}, "
                    f"use_knowledge_memory={bundle.plan.use_knowledge_memory}, "
                    f"days={bundle.plan.days if bundle.plan.days else '-'}, "
                    f"reason={bundle.plan.reason}"
                )

            if enable_event_mem and bundle.event_memory:
                prompt_parts.append("")
                prompt_parts.append("===== 相关事件记录（参考） =====")
                prompt_parts.append(bundle.event_memory)
            if enable_chat_mem and bundle.chat_memory:
                prompt_parts.append("")
                prompt_parts.append("===== 相关对话记录（参考） =====")
                prompt_parts.append(bundle.chat_memory)
            if enable_knowledge and bundle.knowledge_memory:
                prompt_parts.append("")
                prompt_parts.append("===== 相关知识片段（参考） =====")
                prompt_parts.append(bundle.knowledge_memory)
        
        return "\n".join(prompt_parts)

    def _remember_event_case(self, event: DetectionEvent, response: AgentResponse) -> None:
        """将事件及结论保存到案例记忆库。"""
        try:
            event_id = getattr(event, "event_id", "") or f"event_{event.timestamp.strftime('%Y%m%d_%H%M%S')}"
            summary = " ".join(response.message.strip().split())[:240]
            record = CaseRecord(
                event_id=event_id,
                timestamp=event.timestamp.isoformat(),
                state=event.state.value,
                severity=response.severity,
                confidence=float(event.confidence or 0.0),
                detection_count=len(event.detections or []),
                labels=extract_labels(event.detections),
                summary=summary,
            )
            self.case_memory.add(record)
            if self.vector_memory is not None:
                self.vector_memory.add(record, memory_type="event")
        except Exception as exc:
            logger.warning(f"写入案例记忆失败，已忽略: {exc}")

    def _remember_user_case(
        self,
        query: str,
        response_text: str,
        severity: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """将用户问答写入案例记忆库，便于后续相似问题检索。"""
        try:
            now = datetime.now()
            session_id = (context or {}).get("session_id", "chat")
            message_count = (context or {}).get("message_count", 0)
            event_id = f"{session_id}_{message_count or now.strftime('%Y%m%d_%H%M%S')}"
            latest_labels: List[str] = []
            if self.last_events:
                latest_labels = extract_labels(self.last_events[-1].detections)

            summary = " ".join(
                f"Q: {query.strip()} A: {response_text.strip()}".split()
            )[:240]

            record = CaseRecord(
                event_id=event_id,
                timestamp=now.isoformat(),
                state="chat",
                severity=severity,
                confidence=0.0,
                detection_count=0,
                labels=latest_labels,
                summary=summary,
            )
            self.case_memory.add(record)
            if self.vector_memory is not None:
                self.vector_memory.add(record, memory_type="chat")
        except Exception as exc:
            logger.warning(f"写入对话案例记忆失败，已忽略: {exc}")
    
    def _invoke_agent(self, prompt: str, config: Optional[Dict[str, Any]] = None, stream: bool = False) -> str:
        """调用 Agent，使用 invoke 接口返回文本响应。"""
        # 根据 Agent 类型调用不同的接口。
        if hasattr(self.agent, 'invoke'):
            # LangChain Agent 或实现了 invoke 方法的 Agent。
            try:
                messages = [HumanMessage(content=prompt)]
                self.last_config = config

                if stream and hasattr(self.agent, "stream"):
                    from langchain_core.messages import AIMessageChunk
                    from langchain_core.messages import ToolMessage as LCToolMessage
                    result_text = ""
                    seen_tools: set = set()

                    for item in self.agent.stream(
                        {"messages": messages},
                        stream_mode="messages",
                        config=config,
                    ):
                        # stream_mode="messages" yields (chunk, metadata) tuples
                        if not (isinstance(item, tuple) and len(item) == 2):
                            if isinstance(item, dict) and "__interrupt__" in item:
                                self.last_interrupt = item["__interrupt__"]
                                return ""
                            continue
                        chunk, metadata = item

                        if isinstance(chunk, AIMessageChunk):
                            # ── Text tokens ──────────────────────────────
                            content = chunk.content
                            if isinstance(content, str) and content:
                                result_text += content
                                if self._stream_queue is not None:
                                    self._stream_queue.put({"type": "token", "content": content})
                                else:
                                    print(content, end="", flush=True)
                            elif isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        text = block.get("text", "")
                                        if text:
                                            result_text += text
                                            if self._stream_queue is not None:
                                                self._stream_queue.put({"type": "token", "content": text})
                                            else:
                                                print(text, end="", flush=True)

                            # ── Tool calls (name arrives in tool_call_chunks first) ──
                            for tc in (getattr(chunk, "tool_call_chunks", None) or []):
                                name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                                if name and name not in seen_tools:
                                    seen_tools.add(name)
                                    if self._stream_queue is not None:
                                        self._stream_queue.put({"type": "tool_call", "names": [name]})
                                    else:
                                        print(f"\n[tools] {name}", flush=True)

                        elif isinstance(chunk, LCToolMessage):
                            # ── Tool output ───────────────────────────────
                            tool_out = str(chunk.content or "")
                            if tool_out:
                                if self._stream_queue is not None:
                                    self._stream_queue.put({"type": "tool_output", "content": tool_out})
                                else:
                                    print(tool_out, flush=True)
                        else:
                            # ── Final complete AIMessage (LangGraph emits one at end) ──
                            # Use it as fallback if no tokens were streamed (e.g. streaming not supported by LLM)
                            if not result_text:
                                from langchain_core.messages import AIMessage as LCAIMessage
                                if isinstance(chunk, LCAIMessage):
                                    raw = chunk.content
                                    if isinstance(raw, str):
                                        result_text = raw
                                    elif isinstance(raw, list):
                                        result_text = "".join(
                                            b.get("text", "") for b in raw
                                            if isinstance(b, dict) and b.get("type") == "text"
                                        )

                    if result_text:
                        return result_text.strip()
                    return ""

                if config:
                    result = self.agent.invoke({"messages": messages}, config=config)
                else:
                    result = self.agent.invoke({"messages": messages})

            except TypeError:
                if config:
                    result = self.agent.invoke(prompt, config=config)
                else:
                    result = self.agent.invoke(prompt)
            
            # 提取响应文本
            if isinstance(result, dict) and "messages" in result:
                messages = result["messages"]
                if messages:
                    last_message = messages[-1]
                    if hasattr(last_message, 'content'):
                        return last_message.content
                    elif isinstance(last_message, dict):
                        return last_message.get('content', str(last_message))
            
            return str(result)
        
        else:
            raise NotImplementedError(
                f"不支持的 Agent 类型: {type(self.agent).__name__}\n"
                f"Agent 必须实现以下方法之一: invoke, chat, run"
            )

    def resume_with_decision(self, decision_type: str = "approve") -> str:
        if not self.last_config:
            return ""

        decision = {"type": decision_type}
        result_text = None
        for chunk in self.agent.stream(
            Command(resume={"decisions": [decision]}),
            config=self.last_config,
            stream_mode="updates",
        ):
            if "__interrupt__" in chunk:
                self.last_interrupt = chunk["__interrupt__"]
                return ""

            for step, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                messages_list = update.get("messages") or []
                if not messages_list:
                    continue
                last_message = messages_list[-1]
                raw = (
                    last_message.get("content", None)
                    if isinstance(last_message, dict)
                    else getattr(last_message, "content", None)
                )
                if raw:
                    if isinstance(raw, str) and raw.strip():
                        result_text = raw
                    elif isinstance(raw, list):
                        parts = [
                            b.get("text", "") for b in raw
                            if isinstance(b, dict) and b.get("type") == "text"
                        ]
                        extracted = "".join(parts).strip()
                        if extracted:
                            result_text = extracted

        self.last_interrupt = None
        return result_text or ""
    
    def _encode_image(self, frame: np.ndarray) -> str:
        """将图像编码为 Base64，供视觉模型使用。"""
        try:
            return encode_numpy_to_base64(frame)
        except Exception as e:
            logger.error(f"图像编码失败: {e}")
            return ""
    
    def _parse_agent_response(self, response: str, event: DetectionEvent) -> AgentResponse:
        """解析 Agent 响应并评估严重性，返回结构化结果。"""
        severity = self._parse_severity_from_response(response)
        should_escalate = severity == "critical" or (severity == "warning" and event.state == MonitorState.ALARM)
        
        return AgentResponse(
            success=True,
            message=response,
            severity=severity,
            should_escalate=should_escalate,
            metadata={
                "event_state": event.state.value,
                "detection_count": len(event.detections),
                "confidence": event.confidence
            }
        )
    
    def _parse_severity_from_response(self, response: str) -> str:
        """从 Agent 回复中解析严重程度等级。"""
        response_lower = response.lower()
        
        # 判断严重程度 - 优先检查显式标注
        if "critical" in response_lower or "严重" in response_lower:
            return "critical"
        elif "warning" in response_lower or "警告" in response_lower:
            return "warning"
        
        # 高危词汇
        critical_keywords = ["危险", "紧急", "火灾", "爆炸", "danger"]
        if any(word in response_lower for word in critical_keywords):
            return "critical"
        
        # 警告词汇
        warning_keywords = ["注意", "异常", "可疑"]
        if any(word in response_lower for word in warning_keywords):
            return "warning"
        
        return "info"
    
    def clear_memory(self) -> None:
        """清空对话记忆并重置上下文。"""
        self.conversation_memory.clear()
    
    def clear_events(self) -> None:
        """清空事件历史缓存。"""
        self.last_events.clear()
