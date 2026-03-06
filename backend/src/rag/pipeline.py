from __future__ import annotations

from functools import lru_cache
from typing import Dict, Iterable, List

from config import config
from src.rag.bm25_index import BM25Index
from src.rag.chunking import build_chunks
from src.rag.chroma_store import dense_retrieve
from src.rag.doc_loader import load_docs
from src.rag.types import Chunk


def _rrf_fuse(ranked_lists: Iterable[List[str]], k: int = 60) -> List[str]:
    scores: Dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]


class RagPipeline:
    def __init__(self) -> None:
        docs = load_docs()
        self._chunks = build_chunks(
            docs, max_chars=config.rag.chunk_max_chars, overlap=config.rag.chunk_overlap
        )
        self._chunk_map = {chunk.id: chunk for chunk in self._chunks}
        self._bm25 = BM25Index(self._chunks)

    def _rerank(self, query: str, chunks: List[Chunk]) -> List[Chunk]:
        if not chunks:
            return []
        from sentence_transformers import CrossEncoder

        reranker = CrossEncoder(config.rag.rerank_model)
        pairs = [(query, chunk.text) for chunk in chunks]
        scores = reranker.predict(pairs)
        ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
        return [chunk for chunk, _ in ranked]

    def retrieve(self, query: str, k: int = 3) -> List[Dict[str, str]]:
        dense_chunks = dense_retrieve(query, k=config.rag.dense_k)
        sparse_chunks = [chunk for chunk, _ in self._bm25.search(query, k=config.rag.sparse_k)]

        dense_ids = [chunk.id for chunk in dense_chunks]
        sparse_ids = [chunk.id for chunk in sparse_chunks]
        fused_ids = _rrf_fuse([dense_ids, sparse_ids], k=config.rag.rrf_k)

        candidates: List[Chunk] = []
        for doc_id in fused_ids:
            chunk = self._chunk_map.get(doc_id)
            if chunk:
                candidates.append(chunk)

        if not candidates:
            return []

        rerank_limit = min(config.rag.rerank_k, len(candidates))
        reranked = self._rerank(query, candidates[:rerank_limit])
        remaining = candidates[rerank_limit:]
        ordered = reranked + remaining

        results = []
        for chunk in ordered[:k]:
            results.append({"source": chunk.source, "content": chunk.text})
        return results


@lru_cache(maxsize=1)
def get_pipeline() -> RagPipeline:
    return RagPipeline()
