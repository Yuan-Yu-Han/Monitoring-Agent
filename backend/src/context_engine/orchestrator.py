from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.context_engine.intent_router import IntentPlan, route_intent
from src.context_engine.retrievers import (
    retrieve_chat_memory,
    retrieve_event_memory,
    retrieve_knowledge_memory,
)
from src.context_engine.memory.case_memory import CaseMemoryStore
from src.context_engine.memory.vector_memory import VectorMemoryStore


@dataclass
class ContextBundle:
    plan: IntentPlan
    event_memory: str = ""
    chat_memory: str = ""
    knowledge_memory: str = ""


def build_context_bundle(
    *,
    query: str,
    context_kind: str,
    case_memory: CaseMemoryStore,
    vector_memory: Optional[VectorMemoryStore],
    labels: Optional[List[str]] = None,
    top_k: int = 3,
    use_llm_router: bool = True,
    enable_event_memory: bool = True,
    enable_chat_memory: bool = True,
    enable_knowledge_memory: bool = True,
) -> ContextBundle:
    plan = route_intent(query=query, context_kind=context_kind, use_llm=use_llm_router)
    bundle = ContextBundle(plan=plan)

    if enable_event_memory and plan.use_event_memory:
        bundle.event_memory = retrieve_event_memory(
            query=query,
            case_memory=case_memory,
            vector_memory=vector_memory,
            top_k=top_k,
            days=plan.days,
            labels=labels,
        )
    if enable_chat_memory and plan.use_chat_memory:
        bundle.chat_memory = retrieve_chat_memory(
            query=query,
            case_memory=case_memory,
            vector_memory=vector_memory,
            top_k=top_k,
            days=plan.days,
        )
    if enable_knowledge_memory and plan.use_knowledge_memory:
        bundle.knowledge_memory = retrieve_knowledge_memory(query, top_k=top_k)

    return bundle
