from typing import Any, Dict, List

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

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
    )


def main() -> None:
    agent = build_hybrid_agent()

    messages = []
    messages.append({"role": "user", "content": "请检测这张图片中的安全隐患 校验输出的json 并且画bbox图。图片路径是'./inputs/fire1.jpg'"})

    for chunk in agent.stream(  
        {"messages": messages},
        stream_mode="updates",
    ):
        for step, data in chunk.items():
            print(f"step: {step}")
            print(f"content: {data['messages'][-1].content_blocks}")

    # response = agent.invoke(
    #     {"messages": messages},
    # )
    # print(response)

if __name__ == "__main__":
    main()