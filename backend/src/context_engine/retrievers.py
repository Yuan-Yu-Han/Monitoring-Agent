from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from src.context_engine.memory.case_memory import CaseMemoryStore, extract_labels, format_case_context
from src.context_engine.memory.vector_memory import VectorMemoryStore
from src.rag.knowledge import rag_retrieve
from src.system.event_trigger import DetectionEvent


def build_event_query(event: DetectionEvent) -> str:
    return f"{event.state.value} {' '.join(extract_labels(event.detections))}".strip()


def retrieve_event_memory(
    *,
    query: str,
    case_memory: CaseMemoryStore,
    vector_memory: Optional[VectorMemoryStore],
    top_k: int = 3,
    days: Optional[int] = None,
    labels: Optional[List[str]] = None,
) -> str:
    if vector_memory is not None:
        hits = vector_memory.search(query=query, memory_type="event", top_k=top_k, days=days)
        if hits:
            lines = ["[事件记忆]"]
            for idx, hit in enumerate(hits, 1):
                lines.append(
                    f"{idx}. event_id={hit.get('event_id','')}, time={hit.get('timestamp','')}, "
                    f"state={hit.get('state','')}, severity={hit.get('severity','')}, "
                    f"labels={hit.get('labels','-')}, content={hit.get('content','')[:140]}"
                )
            return "\n".join(lines)

    return _fallback_case_context(
        case_memory, query=query, top_k=top_k, days=days, labels=labels, exclude_state="chat"
    )


def retrieve_chat_memory(
    *,
    query: str,
    case_memory: CaseMemoryStore,
    vector_memory: Optional[VectorMemoryStore],
    top_k: int = 3,
    days: Optional[int] = None,
) -> str:
    if vector_memory is not None:
        hits = vector_memory.search(query=query, memory_type="chat", top_k=top_k, days=days)
        if hits:
            lines = ["[对话记忆]"]
            for idx, hit in enumerate(hits, 1):
                lines.append(
                    f"{idx}. event_id={hit.get('event_id','')}, time={hit.get('timestamp','')}, "
                    f"state={hit.get('state','')}, severity={hit.get('severity','')}, "
                    f"labels={hit.get('labels','-')}, content={hit.get('content','')[:140]}"
                )
            return "\n".join(lines)

    return _fallback_case_context(
        case_memory, query=query, top_k=top_k, days=days, labels=None, state="chat"
    )


def retrieve_knowledge_memory(query: str, top_k: int = 3) -> str:
    items = rag_retrieve(query, k=top_k)
    if not items:
        return ""
    lines = []
    for idx, item in enumerate(items, 1):
        source = item.get("source", "")
        content = (item.get("content", "") or "").replace("\n", " ").strip()
        lines.append(f"{idx}. source={source}, content={content[:220]}")
    return "\n".join(lines)


def _fallback_case_context(
    case_memory: CaseMemoryStore,
    *,
    query: str,
    top_k: int,
    days: Optional[int],
    labels: Optional[List[str]],
    state: Optional[str] = None,
    exclude_state: Optional[str] = None,
) -> str:
    fallback_cases = case_memory.search(query=query, top_k=top_k * 2, labels=labels, state=state)
    if exclude_state:
        fallback_cases = [r for r in fallback_cases if r.state != exclude_state]
    if days and days > 0:
        now = datetime.now()
        filtered = []
        for rec in fallback_cases:
            try:
                if (now - datetime.fromisoformat(rec.timestamp)).days <= days:
                    filtered.append(rec)
            except Exception:
                continue
        fallback_cases = filtered
    return format_case_context(fallback_cases[:top_k])
