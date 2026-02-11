from __future__ import annotations

from typing import Dict, List
import traceback

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
        # 打印异常，便于定位检索链路问题
        traceback.print_exc()
        return simple_retrieve(query, k=k)


if __name__ == "__main__":
    # 简单自测：输入查询并打印检索结果
    test_query = "监控区域告警"  # 可按需修改
    results = rag_retrieve(test_query, k=3)
    if not results:
        print("NO RESULTS")
    for item in results:
        source = item.get("source", "")
        print(f"SOURCE: {source}")
        print(item.get("content", ""))
        print("-" * 40)
