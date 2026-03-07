import logging
from pathlib import Path
from typing import Any, Dict, List

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents.middleware import HumanInTheLoopMiddleware, SummarizationMiddleware, before_model, after_model
from langchain.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from src.utils.runtime_env import configure_runtime_env

configure_runtime_env()

from config import GlobalConfig
from prompts.prompt_loader import load_prompt
from src.tools.report_generator import generate_report
from src.tools.image_finder import find_image, list_images
from src.skills import (
    analyze_monitoring_event,
    quick_detect,
    batch_analyze,
    compare_events,
    capture_current_frame,
)

# ── Agent 行为日志 ──────────────────────────────────────────────────────────────
import datetime as _dt

_LOG_DIR = Path(__file__).parent.parent.parent / "logs" / "sessions"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_session_ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
_session_log = _LOG_DIR / f"agent_{_session_ts}.log"

_agent_logger = logging.getLogger("agent.trace")
if not _agent_logger.handlers:
    _fh = logging.FileHandler(_session_log, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    _agent_logger.addHandler(_fh)
    _agent_logger.setLevel(logging.INFO)
    _agent_logger.propagate = False  # 不上传到 root logger，避免重复输出


def _tid(runtime) -> str:
    """从 runtime 安全取 thread_id。"""
    try:
        return str(runtime.config["configurable"]["thread_id"])
    except Exception:
        return "?"


@before_model
def trim_messages(state, runtime):
    """硬限制：超过 20 条时保留第一条 + 最近 10 条，防止 context 无限增长。"""
    messages = state["messages"]
    n = len(messages)
    _agent_logger.info("[before_model] thread=%s  消息数=%d", _tid(runtime), n)
    if n <= 20:
        return None
    keep = [messages[0]] + messages[-10:]
    _agent_logger.warning("[trim] thread=%s  触发硬截断 %d → %d 条", _tid(runtime), n, len(keep))
    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *keep]}


@after_model
def log_agent_trace(state, runtime):
    """记录每次 model 调用后的消息状态，方便排查显存和对话行为。"""
    messages = state["messages"]
    last = messages[-1] if messages else None
    msg_type = type(last).__name__ if last else "-"
    content_preview = str(getattr(last, "content", ""))[:120].replace("\n", " ")
    _agent_logger.info(
        "[after_model]  thread=%s  消息数=%d  最新=[%s]  %s",
        _tid(runtime), len(messages), msg_type, content_preview,
    )
    return None


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
        # 复合工具 —— 内部封装了多步流程，优先让 Agent 使用
        capture_current_frame,     # 实时捕获：按需从 RTSP 抓一帧并检测（无需等待事件触发）
        analyze_monitoring_event,  # 完整分析：find → detect → draw → report
        quick_detect,              # 快速检测：find → detect → draw（不生成报告）
        batch_analyze,             # 批量分析：多张图片统计
        compare_events,            # 对比分析：两事件差异

        # 基础工具 —— 复合工具无法满足时使用
        find_image,                # 按 event_id 或名称查找单张图片路径
        list_images,               # 列出目录内所有图片
        generate_report,           # 自定义报告生成
    ]

    return create_agent(
        model=model,
        tools=tools,
        debug=False,
        system_prompt=load_prompt("system_prompt"),
        checkpointer=InMemorySaver(),
        middleware=[
            trim_messages,                   # 硬截断：> 20 条时保留首条 + 最近 10 条
            log_agent_trace,                 # 行为日志：记录每次 model 调用后的消息状态
            SummarizationMiddleware(
                model=model,                 # 复用同一个 vLLM 模型做摘要
                trigger=("tokens", 4000),    # context 超 4000 token 时触发
                keep=("messages", 10),       # 保留最近 10 条原文，其余压缩成摘要
            ),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "find_image": False,
                    "list_images": False,
                    "generate_report": False,
                },
                description_prefix="Tool execution pending approval",
            ),
        ],
    )


if __name__ == "__main__":
    pass
