from typing import Any, Dict, List

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents.middleware import HumanInTheLoopMiddleware

from config import GlobalConfig
from prompts.prompt_loader import load_prompt
from src.tools.detections import detect_image, safe_parse_json, draw_bboxes
from src.tools.report_generator import generate_report
from src.tools.image_finder import find_image, list_images, validate_image


def build_hybrid_agent() -> Any:
    config = GlobalConfig()
    model = ChatOpenAI(
        model=config.vllm_chat.model_name,
        api_key=config.vllm_chat.api_key,
        base_url=config.vllm_chat.base_url,
    )

    tools = [
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
                    "generate_report": True,
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