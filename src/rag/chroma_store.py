from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import requests
import chromadb

from config import config
from src.rag.doc_loader import load_docs
from src.rag.chunking import build_chunks
from src.rag.types import Chunk


def _vllm_embed(text: str) -> List[float]:
    base_url = config.vllm_chat.base_url.rstrip("/")
    url = f"{base_url}/embeddings"
    payload = {"model": config.vllm_chat.model_name, "input": text}
    headers = {}
    if config.vllm_chat.api_key and config.vllm_chat.api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {config.vllm_chat.api_key}"
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()
    if "data" in data and data["data"]:
        return data["data"][0].get("embedding", [])
    return data.get("embedding", [])


def _ensure_collection(persist_dir: str) -> chromadb.api.models.Collection.Collection:
    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_or_create_collection(name="nomadpilot_docs")


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
    embeddings = [_vllm_embed(text) for text in documents]

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )


def dense_retrieve(query: str, k: int = 3, persist_dir: str | None = None) -> List[Chunk]:
    persist_path = persist_dir or str(Path("data/chroma").resolve())
    collection = _ensure_collection(persist_path)
    if collection.count() == 0:
        build_index(persist_path)

    query_embedding = _vllm_embed(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "metadatas", "ids"],
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]

    output: List[Chunk] = []
    for doc, meta, chunk_id in zip(docs, metas, ids):
        meta = meta or {}
        output.append(
            Chunk(
                id=chunk_id,
                text=doc,
                source=meta.get("source", ""),
                title=meta.get("title", ""),
                section=meta.get("section", ""),
                image_captions=(meta.get("image_captions", "") or "").split("|")
                if meta.get("image_captions")
                else [],
            )
        )

    return output


def retrieve(query: str, k: int = 3, persist_dir: str | None = None) -> List[Dict[str, str]]:
    chunks = dense_retrieve(query, k=k, persist_dir=persist_dir)
    return [{"source": c.source, "content": c.text} for c in chunks]
