#!/usr/bin/env python3
"""RAG health check script.

Usage:
  python3 scripts/test_rag.py --query "火灾应急处置"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.runtime_env import configure_runtime_env

configure_runtime_env()


def _embedding_backend(config) -> str:
    backend = (getattr(config.rag, "embedding_backend", "vllm") or "").strip().lower()
    if backend in {"vllm", "api"}:
        return backend
    return "vllm"


def _persist_path() -> Path:
    return Path("rag_data/chroma").resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG health check")
    parser.add_argument("--query", type=str, default="火灾应急处置流程")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    try:
        from config import config  # noqa: E402
        from src.rag.doc_loader import DOCS_ROOT, load_docs  # noqa: E402
        from src.rag.chunking import build_chunks  # noqa: E402
        from src.rag.retrieve import rag_retrieve  # noqa: E402
    except Exception as exc:
        print("=== RAG Health Check ===")
        print(f"初始化失败: {exc}")
        print("请先安装依赖后重试，例如: pip install -r requirements.txt")
        return 1

    docs = load_docs()
    chunks = build_chunks(
        docs,
        max_chars=config.rag.chunk_max_chars,
        overlap=config.rag.chunk_overlap,
    )

    print("=== RAG Health Check ===")
    current_backend = _embedding_backend(config)
    print(f"embedding_backend: {current_backend}")
    print(f"knowledge_dir: {DOCS_ROOT}")
    print(f"knowledge_docs: {len(docs)}")
    print(f"chunk_count: {len(chunks)}")

    if docs:
        print("sample_docs:")
        for item in docs[:5]:
            print(f"  - {item.get('source', '')}")

    persist_path = _persist_path()
    collection_name = f"rag_docs_{current_backend}"
    print(f"chroma_persist_path: {persist_path}")
    print(f"chroma_collection: {collection_name}")
    try:
        import chromadb  # type: ignore

        client = chromadb.PersistentClient(path=str(persist_path))
        existing = {c.name for c in client.list_collections()}
        if collection_name in existing:
            collection = client.get_collection(name=collection_name)
            print(f"chroma_collection_count: {collection.count()}")
        else:
            print("chroma_collection_count: 0")
    except Exception as exc:
        print(f"chroma_collection_count: unknown (chroma unavailable: {exc})")

    print(f"\nquery: {args.query}")
    if not docs:
        print("retrieved: skipped (knowledge 文档为空)")
    else:
        try:
            results = rag_retrieve(args.query, k=max(args.top_k, 1))
            print(f"retrieved: {len(results)}")

            for idx, item in enumerate(results, 1):
                source = item.get("source", "")
                content = (item.get("content", "") or "").replace("\n", " ").strip()
                print(f"{idx}. source={source}")
                print(f"   content={content[:220]}")
        except Exception as exc:
            print(f"retrieved: failed ({exc})")

    if not docs:
        print("\n[Hint] rag_data/knowledge 目录为空，请放入 .pdf/.md/.txt/.docx 原始文档后重试。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
