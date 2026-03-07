from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    # Optional media pointers (relative to OUTPUTS_DIR, e.g. "alarm/xxx.jpg" or "agent/xxx.jpg")
    image_path: str = ""
    vl_image_path: str = ""
    vl_raw_path: str = ""
    # Evidence + final verdict (single event record, multiple sources)
    yolo: Dict[str, Any] = field(default_factory=dict)
    vl: Dict[str, Any] = field(default_factory=dict)
    final: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "CaseRecord":
        """Backward-compatible loader for JSONL records."""
        raw = raw or {}

        # Legacy top-level fields
        event_id = str(raw.get("event_id", "") or "")
        timestamp = str(raw.get("timestamp", "") or "")
        state = str(raw.get("state", "") or "")
        severity = str(raw.get("severity", "") or "")
        confidence = float(raw.get("confidence", 0.0) or 0.0)
        detection_count = int(raw.get("detection_count", 0) or 0)
        labels = raw.get("labels") or []
        if not isinstance(labels, list):
            labels = []
        labels = [str(x) for x in labels if str(x).strip()]
        summary = str(raw.get("summary", "") or "")

        image_path = str(raw.get("image_path", "") or "")
        vl_image_path = str(raw.get("vl_image_path", "") or "")
        vl_raw_path = str(raw.get("vl_raw_path", "") or "")

        yolo = raw.get("yolo") if isinstance(raw.get("yolo"), dict) else {}
        vl = raw.get("vl") if isinstance(raw.get("vl"), dict) else {}
        final = raw.get("final") if isinstance(raw.get("final"), dict) else {}

        # If nested fields missing, populate from legacy fields for consistency
        if not yolo:
            yolo = {
                "confidence": confidence,
                "detection_count": detection_count,
                "labels": labels,
                "detections": raw.get("detections") if isinstance(raw.get("detections"), list) else [],
            }
        if not vl:
            vl = {
                "summary": summary,
                "raw_path": vl_raw_path,
                "annotated_path": vl_image_path,
            }
        if not final:
            final = {
                "verdict": "unknown",
                "reviewed": False,
                "severity": severity,
                "confidence": confidence,
                "reason": "",
                "decided_by": "yolo",
            }

        # Normalize: prefer explicit final severity/confidence if present
        sev2 = str(final.get("severity") or severity)
        conf2 = float(final.get("confidence") or confidence)
        sum2 = str(vl.get("summary") or summary)
        labels2 = vl.get("labels") if isinstance(vl.get("labels"), list) else labels
        det2 = vl.get("detection_count") if isinstance(vl.get("detection_count"), int) else detection_count

        return cls(
            event_id=event_id,
            timestamp=timestamp,
            state=state,
            severity=sev2,
            confidence=conf2,
            detection_count=int(det2),
            labels=[str(x) for x in (labels2 or []) if str(x).strip()],
            summary=sum2,
            image_path=image_path,
            vl_image_path=vl_image_path,
            vl_raw_path=vl_raw_path,
            yolo=yolo,
            vl=vl,
            final=final,
        )


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
                if isinstance(raw, dict):
                    loaded.append(CaseRecord.from_dict(raw))
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

    def get(self, event_id: str) -> Optional[CaseRecord]:
        """Return the latest record for event_id, if any."""
        if not event_id:
            return None
        for rec in reversed(self._records):
            if rec.event_id == event_id:
                return rec
        return None

    def update_summary(self, event_id: str, summary: str) -> bool:
        for rec in self._records:
            if rec.event_id == event_id:
                rec.summary = summary
                rec.vl["summary"] = summary
                self._persist()
                return True
        return False

    def update_media(
        self,
        event_id: str,
        *,
        image_path: Optional[str] = None,
        vl_image_path: Optional[str] = None,
        vl_raw_path: Optional[str] = None,
    ) -> bool:
        for rec in self._records:
            if rec.event_id != event_id:
                continue
            if image_path is not None:
                rec.image_path = image_path
            if vl_image_path is not None:
                rec.vl_image_path = vl_image_path
            if vl_raw_path is not None:
                rec.vl_raw_path = vl_raw_path
                rec.vl["raw_path"] = vl_raw_path
            self._persist()
            return True
        return False

    def update_fields(
        self,
        event_id: str,
        *,
        detection_count: Optional[int] = None,
        labels: Optional[List[str]] = None,
        confidence: Optional[float] = None,
        severity: Optional[str] = None,
    ) -> bool:
        for rec in self._records:
            if rec.event_id != event_id:
                continue
            if detection_count is not None:
                rec.detection_count = int(detection_count)
                rec.vl["detection_count"] = int(detection_count)
            if labels is not None:
                rec.labels = list(labels)
                rec.vl["labels"] = list(labels)
            if confidence is not None:
                rec.confidence = float(confidence)
                rec.final["confidence"] = float(confidence)
            if severity is not None:
                rec.severity = str(severity)
                rec.final["severity"] = str(severity)
            self._persist()
            return True
        return False

    def update_final(
        self,
        event_id: str,
        *,
        verdict: Optional[str] = None,
        reviewed: Optional[bool] = None,
        severity: Optional[str] = None,
        confidence: Optional[float] = None,
        reason: Optional[str] = None,
        decided_by: Optional[str] = None,
    ) -> bool:
        for rec in self._records:
            if rec.event_id != event_id:
                continue
            if verdict is not None:
                rec.final["verdict"] = str(verdict)
            if reviewed is not None:
                rec.final["reviewed"] = bool(reviewed)
            if severity is not None:
                rec.final["severity"] = str(severity)
                rec.severity = str(severity)
            if confidence is not None:
                rec.final["confidence"] = float(confidence)
                rec.confidence = float(confidence)
            if reason is not None:
                rec.final["reason"] = str(reason)
            if decided_by is not None:
                rec.final["decided_by"] = str(decided_by)
            self._persist()
            return True
        return False

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
