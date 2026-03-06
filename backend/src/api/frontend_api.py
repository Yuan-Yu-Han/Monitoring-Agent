#!/usr/bin/env python3
"""Frontend-facing API for dashboard integration — FastAPI edition."""

from __future__ import annotations

import asyncio
import queue as sync_queue
import json
import os
import time
import contextlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import httpx
import logging
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agent_interface import AgentInterface
from src.context_engine.memory.case_memory import CaseMemoryStore


STREAM_SERVER_URL = os.getenv("STREAM_SERVER_URL", "http://127.0.0.1:5002").rstrip("/")
CACHE_DIR = Path(os.getenv("CACHE_DIR", "./cache"))
CASE_STORE_PATH = CACHE_DIR / "event_cases.jsonl"

app = FastAPI(title="FireGuard AI Monitor API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

def _env_flag(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "y", "on")


agent_interface = AgentInterface(
    enable_memory=_env_flag("AGENT_ENABLE_MEMORY", False),
    retrieval_targets=(["event", "chat", "knowledge"] if _env_flag("AGENT_ENABLE_RETRIEVAL", False) else []),
)
case_memory = CaseMemoryStore(CASE_STORE_PATH)
logger = logging.getLogger(__name__)


# ──────────────────────────── schemas ────────────────────────────

class ChatRequest(BaseModel):
    query: str
    # Optional per-request toggles (override server defaults)
    enable_memory: bool | None = None
    retrieval_targets: List[str] | None = None

    # Legacy flags (deprecated): keep for backward compatibility with older frontends
    enable_retrieval: bool | None = None
    enable_event_memory_retrieval: bool | None = None
    enable_chat_memory_retrieval: bool | None = None
    enable_knowledge_memory: bool | None = None


# ──────────────────────────── routes ─────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now().isoformat()}


@app.get("/dashboard/status")
def dashboard_status():
    stream_status = _safe_get_stream_status()
    records = _load_records()

    person_count = sum(max(int(rec.get("detection_count", 0)), 0) for rec in records[-8:])
    fire_probability = max(
        (float(rec.get("confidence", 0.0)) for rec in records[-8:]), default=0.0
    ) * 100.0
    unresolved = sum(
        1 for rec in records[-20:]
        if str(rec.get("severity", "info")).lower() in ("critical", "warning")
    )
    risk_level = "low"
    if unresolved >= 5 or fire_probability >= 70:
        risk_level = "high"
    elif unresolved >= 2 or fire_probability >= 30:
        risk_level = "medium"

    last_alarm_time = "-"
    if records:
        try:
            ts = datetime.fromisoformat(records[-1]["timestamp"])
            last_alarm_time = ts.strftime("%H:%M:%S")
        except Exception:
            pass

    return {
        "riskLevel": risk_level,
        "fireProbability": round(fire_probability, 1),
        "personCount": person_count,
        "lastAlarmTime": last_alarm_time,
        "unresolvedAlarms": unresolved,
        "stream": stream_status,
    }


@app.get("/dashboard/alarms")
def dashboard_alarms():
    records = [r for r in _load_records() if str(r.get("state", "")) != "chat"]
    latest = records[-30:][::-1]
    alarms = []
    for idx, rec in enumerate(latest, 1):
        ts = rec.get("timestamp", "")
        time_str = ts
        try:
            time_str = datetime.fromisoformat(ts).strftime("%H:%M:%S")
        except Exception:
            pass
        severity = str(rec.get("severity", "info")).lower()
        alarms.append(
            {
                "id": rec.get("event_id") or f"ALM-{idx:03d}",
                "time": time_str,
                "type": "fire",
                "severity": (
                    "critical" if severity == "critical"
                    else ("warning" if severity in ("warning", "warn") else "info")
                ),
                "location": "监控区域",
                "description": rec.get("summary", ""),
                "status": "processing" if severity in ("critical", "warning", "warn") else "resolved",
            }
        )
    return {"items": alarms}


@app.get("/dashboard/risk-trend")
def dashboard_risk_trend():
    records = [r for r in _load_records() if str(r.get("state", "")) != "chat"]
    buckets: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"risk": 0.0, "fire": 0.0, "person": 0.0, "count": 0.0}
    )
    for rec in records[-240:]:
        try:
            ts = datetime.fromisoformat(rec["timestamp"])
            hour = ts.strftime("%H:00")
        except Exception:
            continue
        conf = float(rec.get("confidence", 0.0)) * 100.0
        det = float(rec.get("detection_count", 0.0))
        sev = str(rec.get("severity", "info")).lower()
        sev_bonus = 20.0 if sev == "critical" else (10.0 if sev in ("warning", "warn") else 0.0)
        risk = min(100.0, conf * 0.7 + det * 3.0 + sev_bonus)
        buckets[hour]["risk"] += risk
        buckets[hour]["fire"] += conf
        buckets[hour]["person"] += min(det * 6.0, 100.0)
        buckets[hour]["count"] += 1.0

    result = []
    for h in sorted(buckets.keys()):
        b = buckets[h]
        c = max(b["count"], 1.0)
        result.append(
            {
                "time": h,
                "risk": round(b["risk"] / c, 1),
                "fire": round(b["fire"] / c, 1),
                "person": round(b["person"] / c, 1),
            }
        )
    return {"items": result[-24:]}


@app.post("/chat")
async def chat(body: ChatRequest):
    from fastapi import HTTPException
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    started = time.time()
    try:
        ctx: Dict[str, Any] = {"source": "frontend"}
        if body.enable_memory is not None:
            ctx["enable_memory"] = bool(body.enable_memory)
        if body.retrieval_targets is not None:
            ctx["retrieval_targets"] = body.retrieval_targets

        # Legacy fields (deprecated)
        if body.enable_retrieval is not None:
            ctx["enable_retrieval"] = bool(body.enable_retrieval)
        if body.enable_event_memory_retrieval is not None:
            ctx["enable_event_memory_retrieval"] = bool(body.enable_event_memory_retrieval)
        if body.enable_chat_memory_retrieval is not None:
            ctx["enable_chat_memory_retrieval"] = bool(body.enable_chat_memory_retrieval)
        if body.enable_knowledge_memory is not None:
            ctx["enable_knowledge_memory"] = bool(body.enable_knowledge_memory)

        # 在独立线程里跑同步阻塞的 LangGraph agent，避免与 uvicorn 事件循环冲突
        resp = await asyncio.to_thread(
            agent_interface.handle_user_query,
            query,
            ctx,
        )
        elapsed_ms = int((time.time() - started) * 1000)
        logger.info(f"/chat done in {elapsed_ms}ms ok={resp.success} severity={resp.severity}")
        return {"ok": resp.success, "message": resp.message, "severity": resp.severity}
    except Exception as exc:
        elapsed_ms = int((time.time() - started) * 1000)
        logger.error(f"/chat failed in {elapsed_ms}ms: {exc}", exc_info=True)
        # 把真实错误内容返回给前端，方便调试
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/chat/stream")
async def chat_stream(body: ChatRequest):
    from fastapi import HTTPException
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    q: sync_queue.Queue = sync_queue.Queue()
    ctx: Dict[str, Any] = {"source": "frontend"}
    if body.enable_memory is not None:
        ctx["enable_memory"] = bool(body.enable_memory)
    if body.retrieval_targets is not None:
        ctx["retrieval_targets"] = body.retrieval_targets

    # Legacy fields (deprecated)
    if body.enable_retrieval is not None:
        ctx["enable_retrieval"] = bool(body.enable_retrieval)
    if body.enable_event_memory_retrieval is not None:
        ctx["enable_event_memory_retrieval"] = bool(body.enable_event_memory_retrieval)
    if body.enable_chat_memory_retrieval is not None:
        ctx["enable_chat_memory_retrieval"] = bool(body.enable_chat_memory_retrieval)
    if body.enable_knowledge_memory is not None:
        ctx["enable_knowledge_memory"] = bool(body.enable_knowledge_memory)

    async def generate():
        # Run agent in a thread; it puts typed events into q and ends with 'done'/'error'
        task = asyncio.create_task(
            asyncio.to_thread(agent_interface.handle_user_query_stream, query, ctx, q)
        )
        try:
            while True:
                # Async-friendly queue.get with timeout to avoid blocking event loop
                try:
                    item = await asyncio.wait_for(asyncio.to_thread(q.get), timeout=120.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'message': '响应超时'}, ensure_ascii=False)}\n\n"
                    task.cancel()
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get("type") in ("done", "error"):
                    break
        finally:
            with contextlib.suppress(Exception):
                await task

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/stream/start")
def stream_start():
    return _proxy_stream_action("start")


@app.post("/stream/stop")
def stream_stop():
    return _proxy_stream_action("stop")


# ──────────────────────────── helpers ────────────────────────────

def _proxy_stream_action(action: str):
    try:
        r = httpx.post(f"{STREAM_SERVER_URL}/{action}", timeout=5)
        return {"ok": r.status_code < 400, "upstream": r.json() if r.content else {}}
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=str(exc))


def _safe_get_stream_status() -> Dict[str, Any]:
    try:
        r = httpx.get(f"{STREAM_SERVER_URL}/status", timeout=3)
        if r.status_code < 400:
            return r.json()
    except Exception:
        pass
    return {
        "is_running": False,
        "frames_sent": 0,
        "clients_connected": 0,
        "uptime_seconds": None,
        "rtsp_url": "",
        "last_error": "stream server unavailable",
    }


def _load_records() -> List[Dict[str, Any]]:
    if not CASE_STORE_PATH.exists():
        return []
    rows = []
    for line in CASE_STORE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def main():
    import uvicorn
    host = os.getenv("FRONTEND_API_HOST", "0.0.0.0")
    port = int(os.getenv("FRONTEND_API_PORT", "8010"))
    uvicorn.run("src.api.frontend_api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
