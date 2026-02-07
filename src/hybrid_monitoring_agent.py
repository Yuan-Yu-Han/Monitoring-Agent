from langchain.agents import create_agent
from langchain_openai import ChatOpenAI, OpenAI
from prompts.prompt_loader import load_prompt
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langgraph.checkpoint.memory import InMemorySaver  # [!code highlight]

from config import GlobalConfig
from src.tools.detections import detect_image, safe_parse_json, draw_bboxes
from src.tools.report_generator import generate_report
from src.tools.image_finder import find_image, list_images, validate_image


from typing import List, Dict





class HybridMonitoringAgent:
    """
    Hybrid Monitoring Agent 类
    封装了 LangChain 的 create_agent 功能，提供统一的智能体接口。
    """
    def __init__(self, config: GlobalConfig):
        """
        初始化 Hybrid Monitoring Agent
        
        Args:
            config: 配置对象，包含模型和工具的相关配置。
        """
        self.config = config
        # self.graph = build_graph(self.config)

        # 初始化 LangChain Agent
        self.model=ChatOpenAI(
            model="Qwen3-VL-8B-Instruct",
            api_key="EMPTY",
            base_url="http://localhost:8000/v1"
            )

        self.tools = [
            detect_image,
            safe_parse_json,
            draw_bboxes,
            generate_report,
            find_image,
            list_images,
            validate_image
        ]

        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            checkpointer=InMemorySaver(),
            system_prompt=load_prompt("system_prompt")
        )

    def invoke(self, input_text, chat_history=None, config=None, **kwargs):
        """
        统一调用接口（与 BaseAgent.invoke 保持一致的输入语义）

        Args:
            input_text: 用户输入文本
            chat_history: 可选的历史消息列表（BaseMessage 或 dict）
            config: 传给底层 agent.invoke 的 LangGraph 配置（如 thread_id）
            **kwargs: 传给底层 agent.invoke 的附加参数

        Returns:
            模型生成的文本响应
        """
        # 允许直接传入 LangGraph 格式的输入
        if isinstance(input_text, dict) and "messages" in input_text:
            result = self.agent.invoke(input_text, config=config, **kwargs)
        else:
            # 组装 messages
            messages = []
            if chat_history:
                messages.extend(chat_history)
            messages.append({"role": "user", "content": input_text})

            # 调用底层 LangChain Agent
            result = self.agent.invoke({"messages": messages}, config=config, **kwargs)

        # 兼容多种返回格式
        if isinstance(result, dict) and "messages" in result:
            msgs = result["messages"]
            if msgs:
                last_msg = msgs[-1]
                if hasattr(last_msg, "content"):
                    return last_msg.content
                if isinstance(last_msg, dict):
                    return last_msg.get("content", str(last_msg))

        return str(result)




if __name__ == "__main__":
    # 加载配置
    config = GlobalConfig()

    # 初始化 HybridMonitoringAgent
    hybrid_agent = HybridMonitoringAgent(config)

    # 预定义输入问题
    predefined_questions = [
        "请检测这张图片中的安全隐患 校验输出的json 并且画bbox图。图片路径是'./inputs/fire1.jpg'",
    ]

    # 示例多轮对话
    messages = []
    for question in predefined_questions:
        print(f"🟢 当前问题: {question}")  # 输出当前问题

        # 添加用户输入到消息列表
        messages.append({"role": "user", "content": question})

        # 调用 Agent（使用 HybridMonitoringAgent.invoke）
        response = hybrid_agent.invoke(
            question,
            chat_history=messages,
            config={"configurable": {"thread_id": "1"}}
        )
        print("🤖 Agent 响应:", response)

        # 添加 AI 响应到消息列表
        messages.append({"role": "assistant", "content": response})