from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


@dataclass
class CaseRecord:
    event_id: str
    timestamp: str
    state: str
    severity: str
    confidence: float
    detection_count: int
    labels: List[str] = field(default_factory=list)
    summary: str = ""


class CaseMemoryStore:
    """Simple JSONL-backed episodic memory for event case retrieval."""

    def __init__(self, store_path: Path, max_records: int = 5000) -> None:
        self.store_path = store_path
        self.max_records = max_records
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: List[CaseRecord] = []
        self._load()

    def _load(self) -> None:
        if not self.store_path.exists():
            self._records = []
            return
        loaded: List[CaseRecord] = []
        for line in self.store_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                loaded.append(CaseRecord(**raw))
            except Exception:
                continue
        self._records = loaded[-self.max_records :]

    def _persist(self) -> None:
        lines = [json.dumps(asdict(item), ensure_ascii=False) for item in self._records[-self.max_records :]]
        self.store_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def add(self, record: CaseRecord) -> None:
        self._records.append(record)
        if len(self._records) > self.max_records:
            self._records = self._records[-self.max_records :]
        self._persist()

    def search(
        self,
        query: str,
        top_k: int = 3,
        state: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> List[CaseRecord]:
        if not self._records:
            return []

        query_tokens = _tokenize(query)
        label_set = set((labels or []))
        scored: List[tuple[float, CaseRecord]] = []

        for rec in self._records:
            if state and rec.state != state:
                continue

            haystack = " ".join(
                [
                    rec.event_id,
                    rec.timestamp,
                    rec.state,
                    rec.severity,
                    " ".join(rec.labels),
                    rec.summary,
                ]
            ).lower()

            token_hits = sum(1 for token in query_tokens if token in haystack)
            overlap = 0.0
            if label_set:
                overlap = len(label_set.intersection(set(rec.labels))) / max(len(label_set), 1)

            try:
                rec_ts = datetime.fromisoformat(rec.timestamp)
                age_days = max((datetime.now() - rec_ts).total_seconds() / 86400.0, 0.0)
                recency_bonus = 1.0 / (1.0 + age_days)
            except Exception:
                recency_bonus = 0.0

            score = token_hits + overlap * 2.0 + recency_bonus
            if score > 0:
                scored.append((score, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in scored[: max(top_k, 0)]]


def extract_labels(detections: List[Dict]) -> List[str]:
    labels: List[str] = []
    for det in detections or []:
        if not isinstance(det, dict):
            continue
        label = det.get("class") or det.get("label")
        if label:
            labels.append(str(label))
    return sorted(set(labels))


def format_case_context(cases: List[CaseRecord]) -> str:
    if not cases:
        return ""

    lines = []
    for idx, rec in enumerate(cases, 1):
        lines.append(
            f"{idx}. event_id={rec.event_id}, time={rec.timestamp}, state={rec.state}, "
            f"severity={rec.severity}, labels={','.join(rec.labels) if rec.labels else '-'}, "
            f"summary={rec.summary[:120]}"
        )
    return "\n".join(lines)


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())



# case_memory.py：

# 负责结构化持久化（JSONL）
# 定义 CaseRecord（event_id/time/state/severity/labels/summary 等）
# 提供本地检索 search(...)（关键词/标签/时间新近性打分）
# 适合作为可审计、可回退的数据底座
# vector_memory.py：

# 负责向量化检索层（Chroma）
# 把记录写进 event_memory / chat_memory 两个 collection
# 存 metadata（type/timestamp/ts_unix/state/severity/labels/event_id）
# 提供语义检索与时间过滤（如过去 N 天）
# 简化理解：

# case_memory.py = 真正账本（source of truth）
# vector_memory.py = 语义召回加速器（检索性能/模糊匹配更强）