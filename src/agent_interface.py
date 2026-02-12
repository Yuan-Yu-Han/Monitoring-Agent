"""
Agent 调用接口 - 接口层
提供两种调用模式：事件驱动 和 用户驱动

职责：
✓ 统一入口：process(input, context)
✓ 维护对话记忆 (ConversationMemory)
✓ 构建 prompt（融合事件上下文 + 对话历史）
✓ 解析 Agent 响应
✓ 评估事件严重程度和是否升级
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import logging
import numpy as np
from enum import Enum
from langchain_core.messages import HumanMessage

from src.system.event_trigger import DetectionEvent, MonitorState
from src.utils.image_utils import encode_numpy_to_base64
from src.hybrid_monitoring_agent import build_hybrid_agent

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class ConversationMessage:
    """对话消息"""
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class ConversationMemory:
    """对话记忆管理
    
    职责：
    - 存储和管理对话历史
    - 维护消息队列，避免超出 token 限制
    - 提供上下文检索
    """
    messages: List[ConversationMessage] = field(default_factory=list)
    max_history: int = 10  # 最多保留 10 条消息（从 20 改为 10）
    
    def add_message(
        self, 
        role: MessageRole, 
        content: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """添加消息到记忆"""
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
        """获取最近的 N 条消息"""
        return self.messages[-n:] if n > 0 else self.messages
    
    def get_conversation_context(self) -> str:
        """获取对话上下文作为字符串"""
        if not self.messages:
            return ""
        
        context_parts = []
        for msg in self.get_recent_messages(5):  # 从 10 改为 5
            role_label = "用户" if msg.role == MessageRole.USER else "Assistant"
            context_parts.append(f"{role_label}: {msg.content}")
        
        return "\n".join(context_parts)
    
    def clear(self) -> None:
        """清空记忆"""
        self.messages.clear()
    
    def get_messages_for_context(self) -> List[Dict[str, str]]:
        """获取消息列表用于 LLM 上下文
        
        Returns:
            符合 LLM API 格式的消息列表
        """
        return [
            {"role": msg.role.value, "content": msg.content}
            for msg in self.messages[-5:]  # 从 10 改为 5
        ]


@dataclass
class AgentResponse:
    """Agent 响应
    
    包含 Agent 的分析结果、严重程度评估和是否需要升级报警
    """
    success: bool
    message: str                    # Agent 生成的文本回复
    severity: str = "info"          # 严重程度: info, warning, critical
    should_escalate: bool = False   # 是否应该升级报警
    metadata: Dict[str, Any] = field(default_factory=dict) # 额外元数据


class AgentInterface:
    """
    Agent 调用接口 - 接口层
    
    职责：
    1. 统一入口：process(input, context) - 处理所有输入
    2. 维护对话记忆 (ConversationMemory) - 保存对话历史
    3. 构建 prompt - 融合事件上下文 + 对话历史
    4. 解析 Agent 响应 - 提取关键信息
    5. 评估事件严重程度和是否升级 - 智能决策
    
    提供两种调用模式：
    1. 事件驱动（handle_event）：基于检测事件调用
    2. 用户驱动（handle_user_query）：基于用户问题调用
    """
    
    def __init__(
        self, 
        agent: Optional[Any] = None,
        conversation_memory: Optional[ConversationMemory] = None,
        enable_memory: bool = True
    ):
        """
        初始化 Agent 接口
        
        Args:
            agent: Agent 实例（可选，不传则使用 build_hybrid_agent）
            conversation_memory: 对话记忆实例（可选，如果不提供会创建新的）
            enable_memory: 是否启用对话记忆功能
        """
        self.agent = agent or build_hybrid_agent()
        self.conversation_memory = conversation_memory or ConversationMemory()
        self.enable_memory = enable_memory
        
        # 事件上下文缓存（用于丰富提示词）
        self.last_events: List[DetectionEvent] = []
        self.max_event_history = 5
    
    def process(
        self, 
        input_data: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """
        统一入口：处理输入数据
        
        支持两种输入类型：
        1. event：基于检测事件的驱动
        2. query：基于用户查询的驱动
        
        Args:
            input_data: 输入数据字典，格式如下：
                {
                    "type": "event" | "query",
                    "event": DetectionEvent (如果 type 是 event),
                    "query": str (如果 type 是 query),
                    "image": np.ndarray (可选，用于图像分析)
                }
            context: 额外上下文信息（可选）
            
        Returns:
            AgentResponse: Agent 响应
        """
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
    
    def handle_event(self, event: DetectionEvent) -> AgentResponse:
        """
        路径 1：事件驱动
        
        当状态机触发事件时调用。会使用最近的事件历史和对话记忆
        来构建更富有上下文的提示词。
        
        Args:
            event: 检测事件
            
        Returns:
            AgentResponse: Agent 分析结果
        """
        try:
            logger.info(f"Agent 处理事件: {event.state.value}")
            
            # 保存事件到历史
            self.last_events.append(event)
            if len(self.last_events) > self.max_event_history:
                self.last_events = self.last_events[-self.max_event_history:]
            
            # 构建提示词（融合事件上下文 + 对话历史）
            prompt = self._build_event_prompt(event)
            
            # 准备图像（如果需要视觉分析）
            image_data = self._encode_image(event.frame) if event.frame is not None else None
            
            # 调用 Agent
            response = self._invoke_agent(
                prompt,
                config={"configurable": {"thread_id": "event_1"}},
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
    
    def handle_user_query(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None,
        image: Optional[np.ndarray] = None
    ) -> AgentResponse:
        """
        路径 2：用户驱动
        
        用户提问时调用。会融合对话记忆、事件上下文和额外信息
        来构建更完整的提示词。
        
        Args:
            query: 用户问题
            context: 上下文信息（如最近的事件历史）
            image: 可选的图像（用户可能要求分析当前画面）
            
        Returns:
            AgentResponse: Agent 回答
        """
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
            
            # 准备图像
            image_data = self._encode_image(image) if image is not None else None
            
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
        """
        构建事件分析提示词
        
        融合以下内容：
        - 对话历史（如果启用了内存）
        - 当前事件信息（状态、时间、检测目标）
        - 最近事件历史（1 条）
        
        Args:
            event: 检测事件
            
        Returns:
            构建好的提示词
        """
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
    
    def _build_user_prompt(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建用户查询提示词
        
        融合以下内容：
        - 对话历史（最近 3 条）
        - 最近的监控事件（1 条）
        - 额外上下文信息
        - 用户查询
        
        Args:
            query: 用户问题
            context: 额外上下文信息
            
        Returns:
            构建好的提示词
        """
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
    
    def _invoke_agent(
        self, 
        prompt: str,
        config: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> str:
        """
        调用 Agent
        
        支持多种 Agent 类型：
        - LangChain Agent（带 invoke 方法）
        - 其他实现了 chat 或 run 方法的 Agent
        
        Args:
            prompt: 提示词
            image_data: Base64 编码的图像（可选）
            config: LangGraph 配置（包含 thread_id 等）
            
        Returns:
            Agent 的文本响应
            
        Raises:
            NotImplementedError: 不支持的 Agent 类型
        """
        # 根据 Agent 类型调用不同的接口
        if hasattr(self.agent, 'invoke'):
            # LangChain Agent 或实现了 invoke 方法的 Agent
            try:
                messages = [HumanMessage(content=prompt)]

                if stream and hasattr(self.agent, "stream"):
                    result_text = None
                    for chunk in self.agent.stream(
                        {"messages": messages},
                        stream_mode="updates",
                        config=config
                    ):
                        if stream_mode == "messages":
                            token, metadata = data
                            content = None
                            if hasattr(token, "content_blocks"):
                                content = token.content_blocks
                            elif hasattr(token, "content"):
                                content = token.content
                            if content:
                                print(content, end="", flush=True)
                        elif stream_mode == "updates":
                            for step, update in data.items():
                                last_message = update.get("messages", [])[-1]
                                tool_calls = getattr(last_message, "tool_calls", None)
                                if tool_calls:
                                    tool_names = []
                                    for call in tool_calls:
                                        if isinstance(call, dict):
                                            tool_names.append(call.get("name", "unknown"))
                                        else:
                                            tool_names.append(getattr(call, "name", "unknown"))
                                    print(f"\n[tools] {', '.join(tool_names)}")
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
        
        elif hasattr(self.agent, 'chat'):
            # chat 方法
            return self.agent.chat(prompt)
        
        elif hasattr(self.agent, 'run'):
            # run 方法
            return self.agent.run(prompt)
        
        else:
            raise NotImplementedError(
                f"不支持的 Agent 类型: {type(self.agent).__name__}\n"
                f"Agent 必须实现以下方法之一: invoke, chat, run"
            )
    
    def _encode_image(self, frame: np.ndarray) -> str:
        """将图像编码为 Base64（调用统一的工具函数）
        
        Args:
            frame: OpenCV 图像（numpy array）
            
        Returns:
            Base64 编码的图像字符串
        """
        try:
            return encode_numpy_to_base64(frame)
        except Exception as e:
            logger.error(f"图像编码失败: {e}")
            return ""
    
    def _parse_agent_response(
        self, 
        response: str, 
        event: DetectionEvent
    ) -> AgentResponse:
        """
        解析 Agent 响应，评估严重性和是否需要升级
        
        使用关键词匹配进行初步评估：
        - critical: 含有危险、紧急、火灾等词汇
        - warning: 含有警告、异常等词汇
        - info: 其他
        
        Args:
            response: Agent 的文本响应
            event: 原始检测事件
            
        Returns:
            解析后的 AgentResponse
        """
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
        """从 Agent 回复中解析严重程度
        
        Args:
            response: Agent 的文本响应
            
        Returns:
            严重程度: "critical", "warning", 或 "info"
        """
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
        """清空对话记忆"""
        self.conversation_memory.clear()
    
    def clear_events(self) -> None:
        """清空事件历史"""
        self.last_events.clear()
