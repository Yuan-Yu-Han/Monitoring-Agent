"""
基础 Agent 模块
使用 LangChain 1.0.3 的全新 create_agent API 实现通用的智能体封装

这是第 1 阶段的核心模块，实现：
1. 基于 LangChain V1.0.0 的 create_agent API
2. 流式输出支持（Streaming）
3. 工具调用集成
4. 统一的消息处理

技术要点：
- 使用 LangChain 1.0.3 的 langchain.agents.create_agent API
- create_agent 返回 CompiledStateGraph（基于 LangGraph）
- 支持流式输出，可以实时看到 token、tool calls、reasoning
- 集成自定义工具（时间、计算、搜索等）
- 提供同步和异步接口

参考文档：
- https://docs.langchain.com/oss/python/langchain/agents
- https://reference.langchain.com/python/langchain/agents/
"""

from typing import List, Optional, Dict, Any, Iterator, AsyncIterator, Union, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.agents import create_agent  # LangChain V1.0.0 的新 API

from core.models import get_chat_model, get_streaming_model
from core.prompts import get_system_prompt, get_prompt_with_tools
from core.tools import ALL_TOOLS, BASIC_TOOLS
from config import settings, get_logger

logger = get_logger(__name__)


class BaseAgent:
    """
    基础 Agent 类
    
    封装了 LangChain 1.0.3 的 create_agent 功能，提供统一的智能体接口。
    
    在 LangChain V1.0.0 中，create_agent 返回一个 CompiledStateGraph（基于 LangGraph），
    它内部已经实现了完整的工具调用循环、状态管理和流式输出。
    
    Attributes:
        model: LLM 模型实例或模型标识符
        tools: Agent 可用的工具列表
        graph: LangChain 的 CompiledStateGraph 实例（由 create_agent 返回）
        system_prompt: 系统提示词
        
    Example:
        >>> # 创建一个基础 Agent
        >>> agent = BaseAgent(tools=[get_current_time, calculator])
        >>> 
        >>> # 同步调用
        >>> response = agent.invoke("现在几点？")
        >>> print(response)
        >>> 
        >>> # 流式调用
        >>> for chunk in agent.stream("计算 123 + 456"):
        ...     print(chunk, end="", flush=True)
    
    参考：
        - https://docs.langchain.com/oss/python/langchain/agents
        - https://reference.langchain.com/python/langchain/agents/
    """
    
    def __init__(
        self,
        model: Optional[Union[str, BaseChatModel]] = None,
        tools: Optional[Sequence[BaseTool]] = None,
        system_prompt: Optional[str] = None,
        prompt_mode: str = "default",
        debug: bool = False,
        **kwargs: Any,
    ):
        """
        初始化 Base Agent
        
        根据 LangChain V1.0.0 的 create_agent API 规范初始化 Agent。
        
        Args:
            model: LLM 模型，可以是：
                   - 字符串标识符（如 "openai:gpt-4o"）
                   - BaseChatModel 实例
                   如果为 None，使用默认配置创建
            tools: Agent 可用的工具列表（Sequence[BaseTool]）
                   如果为 None 或空列表，Agent 将只包含模型节点，不进行工具调用循环
            system_prompt: 自定义系统提示词
                          如果为 None，则根据 prompt_mode 生成
            prompt_mode: 提示词模式（default/coding/research/concise/detailed）
            debug: 是否启用详细日志（对应 create_agent 的 debug 参数）
            **kwargs: 其他传递给 create_agent 的参数，如：
                     - checkpointer: 状态持久化
                     - store: 跨线程数据存储
                     - interrupt_before/interrupt_after: 中断点
                     - name: Agent 名称
        
        参考：
            https://reference.langchain.com/python/langchain/agents/#langchain.agents.create_agent
        """
        # ==================== 模型初始化 ====================
        # 在 LangChain V1.0.0 中，model 可以是字符串或 BaseChatModel 实例
        if model is None:
            # 使用默认模型（从配置读取）
            # create_agent 接受字符串格式，如 "openai:gpt-4o"
            self.model = f"openai:{settings.openai_model}"
            logger.info(f"🤖 使用默认模型: {self.model}")
        elif isinstance(model, str):
            # 字符串标识符
            self.model = model
            logger.info(f"🤖 使用模型标识符: {model}")
        else:
            # BaseChatModel 实例
            self.model = model
            logger.info(f"🤖 使用自定义模型实例: {model.__class__.__name__}")
        
        # ==================== 工具初始化 ====================
        if tools is None:
            # 默认使用基础工具集（不需要 API Key）
            self.tools = BASIC_TOOLS
            logger.info(f"🔧 使用基础工具集 ({len(self.tools)} 个工具)")
        else:
            self.tools = list(tools) if tools else []
            logger.info(f"🔧 使用自定义工具集 ({len(self.tools)} 个工具)")
        
        # 打印工具列表
        if self.tools:
            tool_names = [tool.name for tool in self.tools]
            logger.debug(f"   工具列表: {', '.join(tool_names)}")
        
        # ==================== 提示词初始化 ====================
        if system_prompt is None:
            # 根据模式生成系统提示词
            if self.tools:
                # 如果有工具，使用包含工具说明的提示词
                self.system_prompt = get_prompt_with_tools(mode=prompt_mode)
                logger.info(f"📝 使用带工具说明的系统提示词 (模式: {prompt_mode})")
            else:
                # 没有工具，使用普通提示词
                self.system_prompt = get_system_prompt(mode=prompt_mode)
                logger.info(f"📝 使用普通系统提示词 (模式: {prompt_mode})")
        else:
            self.system_prompt = system_prompt
            logger.info("📝 使用自定义系统提示词")
        
        # ==================== Agent 配置 ====================
        self.debug = debug
        
        # ==================== 创建 Agent ====================
        # 在 LangChain V1.0.0 中，使用 create_agent 直接创建
        # 它返回一个 CompiledStateGraph，内部已经实现了完整的工具调用循环
        try:
            logger.info("🔨 创建 Agent（使用 LangChain V1.0.0 create_agent API）...")
            
            # 调用 create_agent
            # 参考：https://reference.langchain.com/python/langchain/agents/#langchain.agents.create_agent
            self.graph = create_agent(
                model=self.model,
                tools=self.tools if self.tools else None,  # None 或空列表表示无工具
                system_prompt=self.system_prompt,
                debug=self.debug,
                **kwargs,  # 支持 checkpointer, store, interrupt_before/after, name 等
            )
            
            logger.info("✅ Agent 创建成功（CompiledStateGraph）")
            logger.debug(f"   配置: debug={self.debug}, tools={len(self.tools)}")
            
        except Exception as e:
            logger.error(f"❌ Agent 创建失败: {e}")
            raise
    
    def invoke(
        self,
        input_text: str,
        chat_history: Optional[List[BaseMessage]] = None,
        **kwargs: Any,
    ) -> str:
        """
        同步调用 Agent（非流式）
        
        在 LangChain V1.0.0 中，create_agent 返回的 CompiledStateGraph
        使用 {"messages": [...]} 作为输入格式。
        
        Args:
            input_text: 用户输入的文本
            chat_history: 对话历史（可选）
            **kwargs: 其他传递给 graph 的参数
            
        Returns:
            Agent 的响应文本
            
        Example:
            >>> agent = BaseAgent()
            >>> response = agent.invoke("你好，请介绍一下自己")
            >>> print(response)
        
        参考：
            https://docs.langchain.com/oss/python/langchain/agents
        """
        logger.info(f"🚀 执行 Agent 调用: {input_text[:50]}...")
        
        try:
            # 准备消息列表
            # LangChain V1.0.0 的 create_agent 使用 {"messages": [...]} 格式
            messages = []
            
            # 添加历史消息
            if chat_history:
                messages.extend(chat_history)
            
            # 添加当前用户消息
            messages.append(HumanMessage(content=input_text))
            
            # 准备输入
            graph_input = {"messages": messages}
            graph_input.update(kwargs)
            
            # 执行 Graph
            # CompiledStateGraph 的 invoke 方法返回最终状态
            result = self.graph.invoke(graph_input)
            
            # 提取最后一条 AI 消息
            # result 是一个包含 "messages" 键的字典
            output_messages = result.get("messages", [])
            
            # 找到最后一条 AI 消息
            ai_response = ""
            for msg in reversed(output_messages):
                if isinstance(msg, AIMessage):
                    ai_response = msg.content
                    break
            
            logger.info(f"✅ Agent 调用完成，输出长度: {len(ai_response)} 字符")
            logger.debug(f"   输出: {ai_response[:100]}...")
            
            return ai_response
            
        except Exception as e:
            error_msg = f"Agent 执行失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return f"抱歉，处理您的请求时出现错误: {str(e)}"
    
    def stream(
        self,
        input_text: str,
        chat_history: Optional[List[BaseMessage]] = None,
        stream_mode: str = "messages",
        **kwargs: Any,
    ) -> Iterator[str]:
        """
        流式调用 Agent
        
        在 LangChain V1.0.0 中，CompiledStateGraph 支持多种流式模式。
        默认使用 "messages" 模式，逐步返回消息内容。
        
        Args:
            input_text: 用户输入的文本
            chat_history: 对话历史（可选）
            stream_mode: 流式模式，可选值：
                        - "messages": 流式返回消息内容（推荐）
                        - "updates": 返回状态更新
                        - "values": 返回完整状态值
            **kwargs: 其他参数
            
        Yields:
            Agent 输出的文本片段
            
        Example:
            >>> agent = BaseAgent()
            >>> for chunk in agent.stream("讲个笑话"):
            ...     print(chunk, end="", flush=True)
        
        参考：
            https://docs.langchain.com/oss/python/langchain/agents
        """
        logger.info(f"🌊 执行 Agent 流式调用: {input_text[:50]}...")
        
        try:
            # 准备消息列表
            messages = []
            if chat_history:
                messages.extend(chat_history)
            messages.append(HumanMessage(content=input_text))
            
            # 准备输入
            graph_input = {"messages": messages}
            graph_input.update(kwargs)
            
            # 流式执行 Graph
            # CompiledStateGraph 的 stream 方法支持多种模式
            for chunk in self.graph.stream(graph_input, stream_mode=stream_mode):
                # 根据 stream_mode 处理不同的输出格式
                if stream_mode == "messages":
                    # messages 模式：chunk 是 (message, metadata) 元组
                    if isinstance(chunk, tuple) and len(chunk) == 2:
                        message, metadata = chunk
                        if isinstance(message, AIMessage) and message.content:
                            logger.debug(f"   流式输出: {message.content[:50]}...")
                            yield message.content
                    elif isinstance(chunk, AIMessage) and chunk.content:
                        logger.debug(f"   流式输出: {chunk.content[:50]}...")
                        yield chunk.content
                
                elif stream_mode == "updates":
                    # updates 模式：chunk 是状态更新字典
                    if isinstance(chunk, dict) and "messages" in chunk:
                        messages_update = chunk["messages"]
                        if messages_update:
                            last_msg = messages_update[-1]
                            if isinstance(last_msg, AIMessage) and last_msg.content:
                                yield last_msg.content
            
            logger.info("✅ Agent 流式调用完成")
            
        except Exception as e:
            error_msg = f"Agent 流式执行失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            yield f"\n\n抱歉，处理您的请求时出现错误: {str(e)}"
    
    async def ainvoke(
        self,
        input_text: str,
        chat_history: Optional[List[BaseMessage]] = None,
        config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """
        异步调用 Agent（非流式）
        
        Args:
            input_text: 用户输入的文本
            chat_history: 对话历史（可选）
            config: LangGraph 配置（如 recursion_limit）
            **kwargs: 其他参数
            
        Returns:
            Agent 的响应文本
            
        Example:
            >>> agent = BaseAgent()
            >>> response = await agent.ainvoke("你好")
            >>> print(response)
        """
        logger.info(f"🚀 执行 Agent 异步调用: {input_text[:50]}...")
        
        try:
            # 准备消息列表
            messages = []
            if chat_history:
                messages.extend(chat_history)
            messages.append(HumanMessage(content=input_text))
            
            # 准备输入
            graph_input = {"messages": messages}
            graph_input.update(kwargs)
            
            # 异步执行 Graph
            result = await self.graph.ainvoke(graph_input, config=config)
            
            # 提取最后一条 AI 消息
            output_messages = result.get("messages", [])
            ai_response = ""
            for msg in reversed(output_messages):
                if isinstance(msg, AIMessage):
                    ai_response = msg.content
                    break
            
            logger.info(f"✅ Agent 异步调用完成")
            return ai_response
            
        except Exception as e:
            error_msg = f"Agent 异步执行失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return f"抱歉，处理您的请求时出现错误: {str(e)}"
    
    async def astream(
        self,
        input_text: str,
        chat_history: Optional[List[BaseMessage]] = None,
        stream_mode: str = "messages",
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        异步流式调用 Agent
        
        Args:
            input_text: 用户输入的文本
            chat_history: 对话历史（可选）
            stream_mode: 流式模式（"messages" 或 "updates"）
            **kwargs: 其他参数
            
        Yields:
            Agent 输出的文本片段
            
        Example:
            >>> agent = BaseAgent()
            >>> async for chunk in agent.astream("讲个笑话"):
            ...     print(chunk, end="", flush=True)
        """
        logger.info(f"🌊 执行 Agent 异步流式调用: {input_text[:50]}...")
        
        try:
            # 准备消息列表
            messages = []
            if chat_history:
                messages.extend(chat_history)
            messages.append(HumanMessage(content=input_text))
            
            # 准备输入
            graph_input = {"messages": messages}
            graph_input.update(kwargs)
            
            # 异步流式执行 Graph
            async for chunk in self.graph.astream(graph_input, stream_mode=stream_mode):
                # 根据 stream_mode 处理不同的输出格式
                if stream_mode == "messages":
                    if isinstance(chunk, tuple) and len(chunk) == 2:
                        message, metadata = chunk
                        if isinstance(message, AIMessage) and message.content:
                            yield message.content
                    elif isinstance(chunk, AIMessage) and chunk.content:
                        yield chunk.content
                
                elif stream_mode == "updates":
                    if isinstance(chunk, dict) and "messages" in chunk:
                        messages_update = chunk["messages"]
                        if messages_update:
                            last_msg = messages_update[-1]
                            if isinstance(last_msg, AIMessage) and last_msg.content:
                                yield last_msg.content
            
            logger.info("✅ Agent 异步流式调用完成")
            
        except Exception as e:
            error_msg = f"Agent 异步流式执行失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            yield f"\n\n抱歉，处理您的请求时出现错误: {str(e)}"


def create_base_agent(
    model: Optional[Union[str, BaseChatModel]] = None,
    tools: Optional[Sequence[BaseTool]] = None,
    prompt_mode: str = "default",
    debug: bool = False,
    **kwargs: Any,
) -> BaseAgent:
    """
    创建基础 Agent 的便捷工厂函数
    
    根据 LangChain V1.0.0 的规范创建 Agent。
    
    Args:
        model: LLM 模型（字符串标识符或实例）
        tools: 工具列表
        prompt_mode: 提示词模式
        debug: 是否启用调试日志
        **kwargs: 其他参数（传递给 create_agent）
        
    Returns:
        配置好的 BaseAgent 实例
        
    Example:
        >>> # 创建默认 Agent
        >>> agent = create_base_agent()
        >>> 
        >>> # 创建编程助手 Agent
        >>> agent = create_base_agent(prompt_mode="coding")
        >>> 
        >>> # 创建带所有工具的 Agent
        >>> from core.tools import ALL_TOOLS
        >>> agent = create_base_agent(tools=ALL_TOOLS)
        >>> 
        >>> # 使用特定模型
        >>> agent = create_base_agent(model="openai:gpt-4o-mini")
    
    参考：
        https://docs.langchain.com/oss/python/langchain/agents
    """
    logger.info(f"🏭 创建 Base Agent (mode={prompt_mode}, debug={debug})")
    
    return BaseAgent(
        model=model,
        tools=tools,
        prompt_mode=prompt_mode,
        debug=debug,
        **kwargs,
    )

