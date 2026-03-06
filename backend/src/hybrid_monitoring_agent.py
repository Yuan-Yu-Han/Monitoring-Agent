from typing import Any, Dict, List

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents.middleware import HumanInTheLoopMiddleware

from src.utils.runtime_env import configure_runtime_env

configure_runtime_env()

from config import GlobalConfig
from prompts.prompt_loader import load_prompt
from src.tools.detections import detect_image, safe_parse_json, draw_bboxes
from src.tools.report_generator import generate_report
from src.tools.image_finder import find_image, list_images, validate_image
from src.tools.skills import (
    analyze_monitoring_event,
    quick_detect,
    batch_analyze,
    compare_events
)


def build_hybrid_agent() -> Any:
    config = GlobalConfig()
    model = ChatOpenAI(
        model=config.vllm_chat.model_name,
        api_key=config.vllm_chat.api_key,
        base_url=config.vllm_chat.base_url,
        streaming=True,          # 必须显式开启，否则 stream_mode="messages" 无法逐 token 输出
        max_tokens=None,         # 不传限制，让 vLLM 按剩余 context 自动决定
        temperature=config.vllm_chat.temperature,
        timeout=config.vllm_chat.timeout,
    )

    tools = [
        # 🔥 Skills（推荐优先使用）- 封装的高频工作流
        analyze_monitoring_event,  # 【最常用】一键分析：find → detect → draw → report
        quick_detect,              # 快速检测：只检测不报告
        batch_analyze,             # 批量分析：分析多张图片
        compare_events,            # 对比分析：对比两个事件

        # 🔧 基础工具（需要时使用）
        detect_image,
        safe_parse_json,
        draw_bboxes,
        generate_report,
        find_image,
        list_images,
        validate_image,
    ]

    return create_agent(
        model=model,
        tools=tools,
        debug=False,
        system_prompt=load_prompt("system_prompt"),
        checkpointer=InMemorySaver(),
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "generate_report": False,
                    "draw_bboxes": False,
                    "detect_image": False,
                    "safe_parse_json": False,
                    "find_image": False,
                    "list_images": False,
                    "validate_image": False,
                }
                ,
                description_prefix="Tool execution pending approval"
            ),
        ],
    )


if __name__ == "__main__":
    pass
