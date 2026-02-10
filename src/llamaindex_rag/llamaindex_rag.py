from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List

import chromadb
from llama_index.core import Settings, SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.chroma import ChromaVectorStore

from config import config


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "knowledge"


def _persist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "chroma_llamaindex"


def _build_settings() -> None:
    Settings.embed_model = OpenAIEmbedding(
        api_base=config.vllm_embed.base_url,
        api_key=config.vllm_embed.api_key,
        model=config.vllm_embed.model_name,
    )
    Settings.llm = OpenAI(
        api_base=config.vllm_chat.base_url,
        api_key=config.vllm_chat.api_key,
        model=config.vllm_chat.model_name,
        temperature=config.vllm_chat.temperature,
        max_tokens=config.vllm_chat.max_tokens,
    )
    Settings.chunk_size = config.rag.chunk_max_chars
    Settings.chunk_overlap = config.rag.chunk_overlap


@lru_cache(maxsize=1)
def _get_index() -> VectorStoreIndex:
    _build_settings()
    data_dir = _data_dir()
    persist_dir = _persist_dir()
    persist_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(persist_dir))
    collection = client.get_or_create_collection(name="rag_docs")
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    if data_dir.exists():
        documents = SimpleDirectoryReader(str(data_dir)).load_data()
    else:
        documents = []

    if collection.count() == 0 and documents:
        return VectorStoreIndex.from_documents(documents, storage_context=storage_context)

    return VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)


def rag_retrieve(query: str, k: int = 3) -> List[Dict[str, str]]:
    index = _get_index()
    query_engine = index.as_query_engine(similarity_top_k=k)
    response = query_engine.query(query)

    results: List[Dict[str, str]] = []
    for node in response.source_nodes[:k]:
        metadata = node.metadata or {}
        source = metadata.get("file_path") or metadata.get("file_name") or ""
        results.append({"source": source, "content": node.text})
    return results
