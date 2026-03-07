from __future__ import annotations

import os
from typing import List

import requests
from config import config


def embed(text: str) -> List[float]:
    """Embed a single text string via OpenAI-compatible API."""
    base_url = (
        os.getenv("RAG_API_EMBED_BASE_URL")
        or config.rag.api_embed_base_url
        or os.getenv("OPENAI_BASE_URL")
    ).rstrip("/")
    model = os.getenv("RAG_API_EMBED_MODEL") or config.rag.api_embed_model
    api_key = os.getenv("RAG_API_EMBED_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    if not api_key:
        raise RuntimeError("Embedding API key is missing. Set RAG_API_EMBED_API_KEY or OPENAI_API_KEY.")
    response = requests.post(
        f"{base_url}/embeddings",
        json={"model": model, "input": text},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if "data" in data and data["data"]:
        return data["data"][0].get("embedding", [])
    return data.get("embedding", [])
