from __future__ import annotations

import re
from typing import List, Tuple

from rank_bm25 import BM25Okapi

from src.rag.types import Chunk

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    def __init__(self, chunks: List[Chunk]) -> None:
        self._chunks = chunks
        self._tokenized = [_tokenize(chunk.text) for chunk in chunks]
        self._bm25 = BM25Okapi(self._tokenized)

    def search(self, query: str, k: int = 5) -> List[Tuple[Chunk, float]]:
        if not self._chunks:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results: List[Tuple[Chunk, float]] = []
        for idx, score in ranked[:k]:
            results.append((self._chunks[idx], float(score)))
        return results
