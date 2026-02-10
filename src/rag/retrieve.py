from __future__ import annotations

from typing import Dict, List

from src.rag.doc_loader import load_docs
from src.rag.pipeline import get_pipeline


def simple_retrieve(query: str, k: int = 3) -> List[Dict[str, str]]:
    docs = load_docs()
    if not docs:
        return []

    scored = []
    for item in docs:
        text = item["content"]
        score = sum(1 for token in query.split() if token in text)
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for s, t in scored[:k] if s > 0]


def rag_retrieve(query: str, k: int = 3) -> List[Dict[str, str]]:
    try:
        pipeline = get_pipeline()
        return pipeline.retrieve(query, k=k)
    except Exception:
        return simple_retrieve(query, k=k)
