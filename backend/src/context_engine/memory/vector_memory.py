from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

try:
    import chromadb
except Exception:  # pragma: no cover - optional dependency in some runtime
    chromadb = None
import requests

from config import config
from src.context_engine.memory.case_memory import CaseRecord


def _vllm_embed(text: str) -> List[float]:
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
    base_url = (
        os.getenv("RAG_API_EMBED_BASE_URL")
        or config.rag.api_embed_base_url
        or os.getenv("OPENAI_BASE_URL")
    ).rstrip("/")
    model = os.getenv("RAG_API_EMBED_MODEL") or config.rag.api_embed_model
    api_key = os.getenv("RAG_API_EMBED_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    if not api_key:
        raise RuntimeError("API embedding backend enabled but API key is missing.")

    url = f"{base_url}/embeddings"
    payload = {"model": model, "input": text}
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()
    if "data" in data and data["data"]:
        return data["data"][0].get("embedding", [])
    return data.get("embedding", [])


def _embedding_backend() -> str:
    backend = (getattr(config.rag, "embedding_backend", "vllm") or "").strip().lower()
    if backend in {"vllm", "api"}:
        return backend
    return "vllm"


def _embed(text: str) -> List[float]:
    if _embedding_backend() == "api":
        return _api_embed(text)
    return _vllm_embed(text)


def parse_history_days(query: str) -> Optional[int]:
    q = (query or "").lower()
    patterns = [
        r"(?:过去|最近|近)\s*(\d+)\s*天",
        r"(\d+)\s*天(?:内|以来)?",
        r"last\s+(\d+)\s+days?",
        r"past\s+(\d+)\s+days?",
    ]
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            value = int(match.group(1))
            if value > 0:
                return value

    zh_map = {
        "一天": 1,
        "两天": 2,
        "三天": 3,
        "四天": 4,
        "五天": 5,
        "一周": 7,
        "七天": 7,
    }
    for token, value in zh_map.items():
        if token in q:
            return value
    return None


class VectorMemoryStore:
    def __init__(self, persist_dir: Path) -> None:
        if chromadb is None:
            raise RuntimeError("chromadb is not installed")
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.event_collection = self.client.get_or_create_collection(name="event_memory")
        self.chat_collection = self.client.get_or_create_collection(name="chat_memory")

    def _collection_for(self, memory_type: str):
        if memory_type == "event":
            return self.event_collection
        if memory_type == "chat":
            return self.chat_collection
        raise ValueError(f"unknown memory_type={memory_type}")

    def add(self, record: CaseRecord, memory_type: str) -> None:
        collection = self._collection_for(memory_type)
        ts_unix = self._to_unix(record.timestamp)
        labels = ",".join(record.labels or [])
        text = (
            f"event_id={record.event_id} state={record.state} severity={record.severity} "
            f"labels={labels} summary={record.summary}"
        ).strip()
        embedding = _embed(text)
        record_id = f"{memory_type}:{record.event_id}:{record.timestamp}"
        metadata = {
            "type": memory_type,
            "timestamp": record.timestamp,
            "ts_unix": ts_unix,
            "state": record.state,
            "severity": record.severity,
            "labels": labels,
            "event_id": record.event_id,
            "detection_count": int(record.detection_count),
            "confidence": float(record.confidence),
        }
        collection.upsert(
            ids=[record_id],
            documents=[text],
            metadatas=[metadata],
            embeddings=[embedding],
        )

    def search(self, query: str, memory_type: str, top_k: int = 3, days: Optional[int] = None) -> List[Dict[str, str]]:
        collection = self._collection_for(memory_type)
        query_embedding = _embed(query)
        where = None
        if days and days > 0:
            cutoff = (datetime.now() - timedelta(days=days)).timestamp()
            where = {"ts_unix": {"$gte": cutoff}}

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=max(top_k, 1),
            include=["documents", "metadatas"],
            where=where,
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        output: List[Dict[str, str]] = []
        for doc, meta in zip(docs, metas):
            meta = meta or {}
            output.append(
                {
                    "content": doc or "",
                    "type": str(meta.get("type", memory_type)),
                    "timestamp": str(meta.get("timestamp", "")),
                    "state": str(meta.get("state", "")),
                    "severity": str(meta.get("severity", "")),
                    "labels": str(meta.get("labels", "")),
                    "event_id": str(meta.get("event_id", "")),
                }
            )
        return output

    @staticmethod
    def _to_unix(iso_time: str) -> float:
        try:
            return datetime.fromisoformat(iso_time).timestamp()
        except Exception:
            return 0.0
