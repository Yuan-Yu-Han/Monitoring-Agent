"""Agent 调用接口，提供事件驱动和用户驱动两种模式。"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import logging
import numpy as np
from enum import Enum
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from src.system.event_trigger import DetectionEvent, MonitorState
from src.utils.image_utils import encode_numpy_to_base64
from src.hybrid_monitoring_agent import build_hybrid_agent

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
    
    def __init__(self, agent: Optional[Any] = None, conversation_memory: Optional[ConversationMemory] = None, enable_memory: bool = True):
        """初始化 Agent 接口，允许传入自定义 agent。"""
        self.agent = agent or build_hybrid_agent()
        self.conversation_memory = conversation_memory or ConversationMemory()
        self.enable_memory = enable_memory
        self.last_interrupt = None
        self.last_config = None
        
        # 事件上下文缓存（用于丰富提示词）
        self.last_events: List[DetectionEvent] = []
        self.max_event_history = 5
    
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
            # 合并 tool_args 到 config['configurable']
            config = {"configurable": {"thread_id": "event_1"}}
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
            
            # 添加用户消息到对话记忆
            if self.enable_memory:
                self.conversation_memory.add_message(
                    MessageRole.USER,
                    query,
                    metadata={"image": image is not None}
                )
            
            # 构建提示词（融合对话历史 + 事件上下文 + 用户查询）
            prompt = self._build_user_prompt(query, context)
            
            # 调用 Agent
            response = self._invoke_agent(
                prompt,
                config={"configurable": {"thread_id": "user_query"}},
                stream=True
            )
            
            # 添加 Assistant 消息到对话记忆
            if self.enable_memory:
                self.conversation_memory.add_message(
                    MessageRole.ASSISTANT,
                    response
                )
            
            # 解析严重程度
            severity = self._parse_severity_from_response(response)
            
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
    
    def _build_event_prompt(self, event: DetectionEvent) -> str:
        """构建事件分析提示词，融合事件与历史上下文。"""
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
        
        # 如果启用了记忆，添加对话历史（只取最近 3 条）
        if self.enable_memory:
            history = self.conversation_memory.get_conversation_context()
            if history:
                prompt_parts.append("===== 对话历史 =====")
                prompt_parts.append(history)
                prompt_parts.append("")
        
        # 添加当前事件信息
        prompt_parts.append("===== 当前监控事件 =====")
        prompt_parts.append(f"状态: {state_desc.get(event.state, event.state.value)}")
        prompt_parts.append(f"时间: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        prompt_parts.append(f"检测到的目标:")
        prompt_parts.append(detection_info if detection_info else "无")
        
        # 如果有事件历史，只添加最近 1 个
        if self.last_events:
            prompt_parts.append("")
            prompt_parts.append("===== 最近事件历史 =====")
            for i, evt in enumerate(self.last_events[-1:], 1):
                prompt_parts.append(
                    f"{i}. [{evt.timestamp.strftime('%H:%M:%S')}] "
                    f"{evt.state.value} - {len(evt.detections)} 个检测"
                )
        
        prompt_parts.append("")
        prompt_parts.append("===== 分析要求 =====")
        prompt_parts.append("请简洁地分析:")
        prompt_parts.append("1. 这是什么情况？")
        prompt_parts.append("2. 严重程度如何？")
        prompt_parts.append("3. 是否需要立即处理？")
        
        return "\n".join(prompt_parts)
    
    def _build_user_prompt(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """构建用户查询提示词，融合对话与事件上下文。"""
        prompt_parts = []
        
        # 添加对话历史（只取最近 3 条）
        if self.enable_memory:
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
        
        return "\n".join(prompt_parts)
    
    def _invoke_agent(self, prompt: str, config: Optional[Dict[str, Any]] = None, stream: bool = False) -> str:
        """调用 Agent，使用 invoke 接口返回文本响应。"""
        # 根据 Agent 类型调用不同的接口。
        if hasattr(self.agent, 'invoke'):
            # LangChain Agent 或实现了 invoke 方法的 Agent。
            try:
                messages = [HumanMessage(content=prompt)]
                self.last_config = config

                if stream and hasattr(self.agent, "stream"):
                    result_text = None
                    for chunk in self.agent.stream(
                        {"messages": messages},
                        stream_mode="updates",
                        config=config
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
                            content_blocks = getattr(last_message, "content_blocks", None)
                            if isinstance(content_blocks, list):
                                text_parts = []
                                for block in content_blocks:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        text_parts.append(block.get("text", ""))
                                text = "".join(text_parts).strip()
                                if text:
                                    print(text, flush=True)

                            tool_calls = getattr(last_message, "tool_calls", None)
                            if tool_calls:
                                print(f"step: {step}", flush=True)
                                tool_names = []
                                for call in tool_calls:
                                    if isinstance(call, dict):
                                        tool_names.append(call.get("name", "unknown"))
                                    else:
                                        tool_names.append(getattr(call, "name", "unknown"))
                                print(f"[tools] {', '.join(tool_names)}", flush=True)

                            if hasattr(last_message, "content") and last_message.content:
                                result_text = last_message.content
                            elif isinstance(last_message, dict):
                                result_text = last_message.get("content", result_text)

                    if result_text:
                        return result_text

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
                if hasattr(last_message, "content") and last_message.content:
                    result_text = last_message.content
                elif isinstance(last_message, dict):
                    result_text = last_message.get("content", result_text)

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
