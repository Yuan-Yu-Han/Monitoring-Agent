#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export FRONTEND_API_HOST="${FRONTEND_API_HOST:-0.0.0.0}"
export FRONTEND_API_PORT="${FRONTEND_API_PORT:-8010}"
export STREAM_SERVER_URL="${STREAM_SERVER_URL:-http://127.0.0.1:5002}"

cd "$PROJECT_ROOT"
python3 src/api/frontend_api.py
