#!/usr/bin/env python3
"""Frontend-facing API for dashboard integration."""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import logging

import requests
from flask import Flask, jsonify, request

from src.agent_interface import AgentInterface
from src.context_engine.memory.case_memory import CaseMemoryStore


STREAM_SERVER_URL = os.getenv("STREAM_SERVER_URL", "http://127.0.0.1:5002").rstrip("/")
CACHE_DIR = Path(os.getenv("CACHE_DIR", "./cache"))
CASE_STORE_PATH = CACHE_DIR / "event_cases.jsonl"

app = Flask(__name__)
agent_interface = AgentInterface()
case_memory = CaseMemoryStore(CASE_STORE_PATH)
logger = logging.getLogger(__name__)


@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "time": datetime.now().isoformat()})


@app.route("/dashboard/status", methods=["GET"])
def dashboard_status():
    stream_status = _safe_get_stream_status()
    records = _load_records()

    person_count = sum(max(int(rec.get("detection_count", 0)), 0) for rec in records[-8:])
    fire_probability = max((float(rec.get("confidence", 0.0)) for rec in records[-8:]), default=0.0) * 100.0
    unresolved = sum(1 for rec in records[-20:] if str(rec.get("severity", "info")).lower() in ("critical", "warning"))
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

    return jsonify(
        {
            "riskLevel": risk_level,
            "fireProbability": round(fire_probability, 1),
            "personCount": person_count,
            "lastAlarmTime": last_alarm_time,
            "unresolvedAlarms": unresolved,
            "stream": stream_status,
        }
    )


@app.route("/dashboard/alarms", methods=["GET"])
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
                "severity": "critical" if severity == "critical" else ("warning" if severity in ("warning", "warn") else "info"),
                "location": "监控区域",
                "description": rec.get("summary", ""),
                "status": "processing" if severity in ("critical", "warning", "warn") else "resolved",
            }
        )
    return jsonify({"items": alarms})


@app.route("/dashboard/risk-trend", methods=["GET"])
def dashboard_risk_trend():
    records = [r for r in _load_records() if str(r.get("state", "")) != "chat"]
    buckets: Dict[str, Dict[str, float]] = defaultdict(lambda: {"risk": 0.0, "fire": 0.0, "person": 0.0, "count": 0.0})
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
    return jsonify({"items": result[-24:]})


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    if not query:
        return jsonify({"ok": False, "error": "query is required"}), 400
    started = time.time()
    try:
        resp = agent_interface.handle_user_query(query, context={"source": "frontend"})
        elapsed_ms = int((time.time() - started) * 1000)
        logger.info(f"/chat done in {elapsed_ms}ms, ok={resp.success}, severity={resp.severity}")
        return jsonify({"ok": resp.success, "message": resp.message, "severity": resp.severity})
    except Exception as exc:
        elapsed_ms = int((time.time() - started) * 1000)
        logger.error(f"/chat failed in {elapsed_ms}ms: {exc}", exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/stream/start", methods=["POST"])
def stream_start():
    return _proxy_stream_action("start")


@app.route("/stream/stop", methods=["POST"])
def stream_stop():
    return _proxy_stream_action("stop")


def _proxy_stream_action(action: str):
    try:
        r = requests.post(f"{STREAM_SERVER_URL}/{action}", timeout=5)
        return jsonify({"ok": r.status_code < 400, "upstream": r.json() if r.content else {}})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


def _safe_get_stream_status() -> Dict[str, Any]:
    try:
        r = requests.get(f"{STREAM_SERVER_URL}/status", timeout=3)
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
    host = os.getenv("FRONTEND_API_HOST", "0.0.0.0")
    port = int(os.getenv("FRONTEND_API_PORT", "8010"))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
