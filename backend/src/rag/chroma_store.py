from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

from src.utils.runtime_env import configure_runtime_env

configure_runtime_env()

import requests
import chromadb
from requests import exceptions as req_exc

from config import config
from src.rag.doc_loader import load_docs
from src.rag.chunking import build_chunks
from src.rag.types import Chunk


def _vllm_embed(text: str) -> List[float]:
    # 使用 vLLM embedding 服务
    base_url = config.vllm_embed.base_url.rstrip("/")
    url = f"{base_url}/embeddings"
    payload = {"model": config.vllm_embed.model_name, "input": text}
    headers = {}
    if config.vllm_embed.api_key and config.vllm_embed.api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {config.vllm_embed.api_key}"
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()
    if "data" in data and data["data"]:
        return data["data"][0].get("embedding", [])
    return data.get("embedding", [])


def _api_embed(text: str) -> List[float]:
    # 预留 API embedding（默认走 OpenAI 兼容接口）
    base_url = (
        os.getenv("RAG_API_EMBED_BASE_URL")
        or config.rag.api_embed_base_url
        or os.getenv("OPENAI_BASE_URL")
    ).rstrip("/")
    model = os.getenv("RAG_API_EMBED_MODEL") or config.rag.api_embed_model
    api_key = os.getenv("RAG_API_EMBED_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    if not api_key or api_key.strip().upper() == "EMPTY":
        raise RuntimeError("API embedding backend enabled but API key is missing.")

    url = f"{base_url}/embeddings"
    payload = {"model": model, "input": text}
    headers = {"Authorization": f"Bearer {api_key}"}
    # Optional OpenAI headers (some setups use project/org scoping)
    org = os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION")
    project = os.getenv("OPENAI_PROJECT") or os.getenv("OPENAI_PROJECT_ID")
    if org:
        headers["OpenAI-Organization"] = org
    if project:
        headers["OpenAI-Project"] = project
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    try:
        response.raise_for_status()
    except req_exc.HTTPError as exc:
        status = getattr(response, "status_code", None)
        if status in (401, 403):
            raise RuntimeError(
                "API embedding Unauthorized: please set a valid RAG_API_EMBED_API_KEY (or OPENAI_API_KEY), "
                "or switch rag.embedding_backend to 'vllm'."
            ) from exc
        raise
    data = response.json()
    if "data" in data and data["data"]:
        return data["data"][0].get("embedding", [])
    return data.get("embedding", [])


def _embedding_backend() -> str:
    backend = (getattr(config.rag, "embedding_backend", "vllm") or "").strip().lower()
    if backend in {"vllm", "api"}:
        return backend
    return "vllm"


def _collection_name() -> str:
    return f"rag_docs_{_embedding_backend()}"


def _embed(text: str) -> List[float]:
    backend = _embedding_backend()
    if backend == "api":
        return _api_embed(text)
    return _vllm_embed(text)


def _ensure_collection(persist_dir: str) -> chromadb.api.models.Collection.Collection:
    client = chromadb.PersistentClient(path=persist_dir)
    name = _collection_name()
    return client.get_or_create_collection(name=name)


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
    embeddings = [_embed(text) for text in documents]
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )


def dense_retrieve(query: str, k: int = 3, persist_dir: str | None = None) -> List[Chunk]:
    persist_path = persist_dir or str(Path("rag_data/chroma").resolve())
    collection = _ensure_collection(persist_path)
    if collection.count() == 0:
        build_index(persist_path)

    query_embedding = _embed(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "metadatas"],
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
