#!/usr/bin/env python3
"""Unified entrypoint for monitoring + dashboard stack."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parent


@dataclass
class ServiceProc:
    name: str
    proc: subprocess.Popen


def spawn(cmd: List[str], *, name: str, cwd: Path, env: dict) -> ServiceProc:
    proc = subprocess.Popen(cmd, cwd=str(cwd), env=env)
    return ServiceProc(name=name, proc=proc)


def terminate_all(services: List[ServiceProc]) -> None:
    for svc in services:
        if svc.proc.poll() is None:
            svc.proc.terminate()
    deadline = time.time() + 8
    while time.time() < deadline:
        if all(svc.proc.poll() is not None for svc in services):
            return
        time.sleep(0.2)
    for svc in services:
        if svc.proc.poll() is None:
            svc.proc.kill()



def main() -> int:
    stream_port = int(os.getenv("MAIN_STREAM_PORT", "5002"))
    api_port = int(os.getenv("MAIN_API_PORT", "8010"))
    api_host = os.getenv("MAIN_API_HOST", "0.0.0.0")
    frontend_port = int(os.getenv("MAIN_FRONTEND_PORT", "3000"))
    run_frontend_dev = os.getenv("MAIN_RUN_FRONTEND_DEV", "1").strip().lower() in {"1", "true", "yes"}
    env = os.environ.copy()
    root_str = str(ROOT)
    old_pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = root_str if not old_pythonpath else f"{root_str}{os.pathsep}{old_pythonpath}"
    services: List[ServiceProc] = []

    services.append(
        spawn(
            [sys.executable, "-m", "src.streaming.server", "start", "--port", str(stream_port)],
            name="stream",
            cwd=ROOT,
            env=env,
        )
    )
    print(f"[main] stream started at http://127.0.0.1:{stream_port}")

    api_env = env.copy()
    api_env["FRONTEND_API_HOST"] = api_host
    api_env["FRONTEND_API_PORT"] = str(api_port)
    api_env["STREAM_SERVER_URL"] = f"http://127.0.0.1:{stream_port}"
    services.append(
        spawn(
            [sys.executable, "-m", "src.api.frontend_api"],
            name="api",
            cwd=ROOT,
            env=api_env,
        )
    )
    print(f"[main] api started at http://127.0.0.1:{api_port}")

    services.append(
        spawn(
            [sys.executable, "-m", "src.start_monitoring"],
            name="monitoring",
            cwd=ROOT,
            env=env,
        )
    )
    print("[main] monitoring started via src/start_monitoring.py")

    if run_frontend_dev:
        fe_env = env.copy()
        fe_env["NEXT_PUBLIC_BACKEND_URL"] = f"http://127.0.0.1:{api_port}"
        fe_env["NEXT_PUBLIC_STREAM_SERVER_URL"] = f"http://127.0.0.1:{stream_port}"
        fe_env["PORT"] = str(frontend_port)
        frontend_cmd: List[str] | None = None
        pnpm_bin = shutil.which("pnpm")
        if pnpm_bin is None:
            candidate = Path.home() / ".local" / "share" / "pnpm" / "pnpm"
            if candidate.exists():
                pnpm_bin = str(candidate)

        if pnpm_bin:
            frontend_cmd = [pnpm_bin, "dev"]
        elif shutil.which("npm"):
            frontend_cmd = ["npm", "run", "dev"]

        if frontend_cmd is None:
            print("[main] frontend not started: neither pnpm nor npm found in PATH")
        else:
            print(f"[main] frontend command: {' '.join(frontend_cmd)}")
            services.append(
                spawn(
                    frontend_cmd,
                    name="frontend",
                    cwd=ROOT / "frontend",
                    env=fe_env,
                )
            )
            print(f"[main] frontend dev started at http://127.0.0.1:{frontend_port}")
    else:
        print("[main] frontend dev not started (set MAIN_RUN_FRONTEND_DEV=1 to enable)")

    print("[main] press Ctrl+C to stop all services")

    def _handle_sig(_sig, _frm):
        terminate_all(services)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    try:
        while True:
            for svc in services:
                code = svc.proc.poll()
                if code is not None:
                    print(f"[main] service exited: {svc.name} code={code}")
                    terminate_all(services)
                    return code
            time.sleep(0.5)
    except KeyboardInterrupt:
        terminate_all(services)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
