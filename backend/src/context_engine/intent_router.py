from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

import requests

from config import config
from src.context_engine.memory.vector_memory import parse_history_days


@dataclass
class IntentPlan:
    use_event_memory: bool
    use_chat_memory: bool
    use_knowledge_memory: bool
    days: Optional[int] = None
    reason: str = ""


def _looks_like_event_id(query: str) -> bool:
    q = (query or "").lower()
    if "event_id" in q or "eventid" in q:
        return True
    # Common event_id pattern in this repo: 20260218_171730_alarm_ab12cd
    if re.search(r"\b\d{8}_\d{6}\b", q):
        return True
    return False


def route_intent(query: str, context_kind: str = "user", use_llm: bool = True) -> IntentPlan:
    normalized = (query or "").strip().lower()
    if not normalized:
        return IntentPlan(False, False, False, reason="empty_query")

    if use_llm:
        plan = _route_by_llm(query=normalized, context_kind=context_kind)
        if plan is not None:
            if plan.days is None:
                plan.days = parse_history_days(normalized)
            return plan

    return _route_by_rules(query=normalized, context_kind=context_kind)


def _route_by_rules(query: str, context_kind: str) -> IntentPlan:
    days = parse_history_days(query)
    history_kw = (
        "历史", "过去", "最近", "统计", "回顾", "回溯", "查询", "搜索", "检索",
        "history", "events", "past ", "last ", "latest", "recent",
        "今天", "昨日", "昨天", "前天", "本周", "上周", "本月", "上个月",
        "最新", "上一条",
    )
    event_kw = (
        "告警", "报警", "事件", "记录", "火情", "烟雾", "火灾", "smoke", "fire",
        "监控", "摄像头", "画面", "截图", "抓拍", "视频", "rtsp", "yolo",
        "suspect", "warning", "alarm",
    )
    chat_kw = (
        "你刚才", "你刚刚", "你之前", "你上次", "我们之前", "我们上次",
        "刚才说", "前面说", "上面说", "提到过", "对话", "聊天", "聊天记录", "对话记录",
    )
    knowledge_kw = (
        "怎么", "如何", "为什么", "处置", "建议", "步骤", "规范", "标准", "流程", "预案", "应急",
        "what", "why", "how", "？", "?",
    )

    has_history = days is not None or any(k in query for k in history_kw)
    wants_event = _looks_like_event_id(query) or any(k in query for k in event_kw)
    wants_chat = any(k in query for k in chat_kw)
    wants_knowledge = any(k in query for k in knowledge_kw)

    if context_kind == "event":
        return IntentPlan(
            use_event_memory=True,
            use_chat_memory=has_history or wants_chat,
            use_knowledge_memory=True,
            days=days,
            reason="rule:event",
        )

    # Explicitly asking about past/latest alarms/events/records: retrieve event memory.
    if has_history and (wants_event or not wants_knowledge):
        return IntentPlan(
            use_event_memory=True,
            use_chat_memory=wants_chat,
            use_knowledge_memory=wants_knowledge,
            days=days,
            reason="rule:history_event",
        )

    # Direct event-like query without time window (e.g. "最新告警是什么")
    if wants_event and not wants_knowledge:
        return IntentPlan(
            use_event_memory=True,
            use_chat_memory=wants_chat,
            use_knowledge_memory=False,
            days=days,
            reason="rule:event_query",
        )

    # Chat-focused "remind me what I said" queries.
    if wants_chat and not wants_event:
        return IntentPlan(
            use_event_memory=False,
            use_chat_memory=True,
            use_knowledge_memory=wants_knowledge,
            days=days,
            reason="rule:chat_query",
        )

    return IntentPlan(
        use_event_memory=False,
        use_chat_memory=False,
        use_knowledge_memory=True,
        days=days,
        reason="rule:knowledge_only",
    )


def _route_by_llm(query: str, context_kind: str) -> Optional[IntentPlan]:
    base_url = config.vllm_chat.base_url.rstrip("/")
    model = config.vllm_chat.model_name
    if not base_url or not model:
        return None

    api_key = config.vllm_chat.api_key or os.getenv("OPENAI_API_KEY", "")
    headers = {"Content-Type": "application/json"}
    if api_key and api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {api_key}"

    system = (
        "你是意图路由器。根据 query 决定是否需要检索三类记忆："
        "event memory、chat memory、knowledge memory。"
        "输出必须是 JSON 对象，字段仅限："
        "use_event_memory(boolean), use_chat_memory(boolean), use_knowledge_memory(boolean), days(number|null), reason(string)。"
        "当 query 是历史/统计/过去N天类，优先开启 event/chat memory。"
        "当 query 需要知识解释/步骤/规范时，开启 knowledge memory。"
        "当 query 询问最新告警/报警/事件/记录时，开启 event memory。"
        "当 query 询问'你刚才/你之前说过什么'时，开启 chat memory。"
        "如果 context_kind=event，一般需要 use_event_memory=true。"
    )
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 140,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"context_kind={context_kind}\nquery={query}"},
        ],
    }

    try:
        url = f"{base_url}/chat/completions"
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        raw = _extract_json_object(content)
        data = json.loads(raw)
        days_raw = data.get("days")
        days: Optional[int] = None
        if isinstance(days_raw, (int, float)) and days_raw > 0:
            days = int(days_raw)
        return IntentPlan(
            use_event_memory=bool(data.get("use_event_memory", False)),
            use_chat_memory=bool(data.get("use_chat_memory", False)),
            use_knowledge_memory=bool(data.get("use_knowledge_memory", False)),
            days=days,
            reason=f"llm:{str(data.get('reason', 'intent_router'))}",
        )
    except Exception:
        return None


def _extract_json_object(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    match = re.search(r"\{[\s\S]*\}", stripped)
    if not match:
        raise ValueError("no json object found")
    return match.group(0)
