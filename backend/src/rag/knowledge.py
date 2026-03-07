from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from src.utils.runtime_env import configure_runtime_env

configure_runtime_env()

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None

from config import config
from src.rag.embeddings import embed
from src.rag.indexing import Chunk, build_chunks, load_docs

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "rag_docs_api"


def _ensure_collection(persist_dir: str) -> "chromadb.api.models.Collection.Collection":
    if chromadb is None:
        raise RuntimeError("chromadb is not installed; cannot use vector retrieval.")
    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_or_create_collection(name=_COLLECTION_NAME)


def build_index(persist_dir: str) -> None:
    collection = _ensure_collection(persist_dir)
    if collection.count() > 0:
        return
    docs = load_docs()
    chunks = build_chunks(
        docs, max_chars=config.rag.chunk_max_chars, overlap=config.rag.chunk_overlap
    )
    if not chunks:
        return
    ids = [c.id for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [
        {
            "source": c.source,
            "title": c.title,
            "section": c.section,
            "image_captions": "|".join(c.image_captions),
        }
        for c in chunks
    ]
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=[embed(t) for t in documents],
    )


def dense_retrieve(query: str, k: int = 3, persist_dir: str | None = None) -> List[Chunk]:
    persist_path = persist_dir or str(Path("rag_data/chroma").resolve())
    collection = _ensure_collection(persist_path)
    if collection.count() == 0:
        build_index(persist_path)

    results = collection.query(
        query_embeddings=[embed(query)],
        n_results=k,
        include=["documents", "metadatas"],
    )
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]

    return [
        Chunk(
            id=chunk_id,
            text=doc,
            source=(meta or {}).get("source", ""),
            title=(meta or {}).get("title", ""),
            section=(meta or {}).get("section", ""),
            image_captions=((meta or {}).get("image_captions", "") or "").split("|")
            if (meta or {}).get("image_captions")
            else [],
        )
        for doc, meta, chunk_id in zip(docs, metas, ids)
    ]


def retrieve(query: str, k: int = 3, persist_dir: str | None = None) -> List[Dict[str, str]]:
    chunks = dense_retrieve(query, k=k, persist_dir=persist_dir)
    return [{"source": c.source, "content": c.text} for c in chunks]


def _simple_retrieve(query: str, k: int = 3) -> List[Dict[str, str]]:
    docs = load_docs()
    if not docs:
        return []
    scored = [(sum(1 for t in query.split() if t in item["content"]), item) for item in docs]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for score, item in scored[:k] if score > 0]


def rag_retrieve(query: str, k: int = 3) -> List[Dict[str, str]]:
    try:
        return retrieve(query, k=k)
    except Exception as exc:
        logger.warning("RAG retrieve failed; falling back to simple retrieval: %s", exc, exc_info=True)
        return _simple_retrieve(query, k=k)
