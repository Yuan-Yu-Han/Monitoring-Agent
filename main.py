#!/usr/bin/env python3
"""
统一入口：从项目根目录一键启动监控 + Dashboard 相关服务栈。

本文件负责拉起多个子进程，并在任意一个服务异常退出时，统一关闭其它服务。

可用环境变量（可按需覆盖默认值）：
- MAIN_STREAM_PORT: 流服务端口（默认 5002）
- MAIN_API_HOST: API 监听地址（默认 0.0.0.0）
- MAIN_API_PORT: API 端口（默认 8010）
- MAIN_FRONTEND_PORT: 前端 dev server 端口（默认 3000）
- MAIN_RUN_FRONTEND_DEV: 是否启动前端 dev（默认 0；设为 1/true/yes 可开启）
- MAIN_FRONTEND_DIR: 前端目录（默认自动探测 ./frontend）
"""

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


# 项目根目录（Monitoring-Agent/）
PROJECT_ROOT = Path(__file__).resolve().parent
# 后端根目录（Monitoring-Agent/backend/）
BACKEND_ROOT = PROJECT_ROOT / "backend"


MAX_RESTARTS = 5       # 单个服务最多重启次数
RESTART_DELAY = 5.0   # 重启前等待秒数


@dataclass
class ServiceProc:
    name: str
    proc: subprocess.Popen
    cmd: List[str] = None          # type: ignore[assignment]
    cwd: Path = None               # type: ignore[assignment]
    env: dict = None               # type: ignore[assignment]
    restart_count: int = 0
    essential: bool = True         # False = 崩溃不触发全局关闭


def spawn(cmd: List[str], *, name: str, cwd: Path, env: dict, essential: bool = True) -> ServiceProc:
    proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, start_new_session=True)
    return ServiceProc(name=name, proc=proc, cmd=cmd, cwd=cwd, env=env, essential=essential)


def terminate_all(services: List[ServiceProc]) -> None:
    for svc in services:
        if svc.proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(svc.proc.pid, signal.SIGTERM)
                else:
                    svc.proc.terminate()
            except ProcessLookupError:
                pass
    deadline = time.time() + 8
    while time.time() < deadline:
        if all(svc.proc.poll() is not None for svc in services):
            return
        time.sleep(0.2)
    for svc in services:
        if svc.proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(svc.proc.pid, signal.SIGKILL)
                else:
                    svc.proc.kill()
            except ProcessLookupError:
                pass


def main() -> int:
    # 工作目录切到后端根目录，让 -m src.xxx 导入路径正确
    os.chdir(BACKEND_ROOT)

    stream_port = int(os.getenv("MAIN_STREAM_PORT", "5002"))
    api_port = int(os.getenv("MAIN_API_PORT", "8010"))
    api_host = os.getenv("MAIN_API_HOST", "0.0.0.0")
    frontend_port = int(os.getenv("MAIN_FRONTEND_PORT", "3000"))
    run_frontend_dev = os.getenv("MAIN_RUN_FRONTEND_DEV", "1").strip().lower() in {"1", "true", "yes"}
    env = os.environ.copy()

    # 把 backend/ 加入 PYTHONPATH，确保子进程能导入 src.xxx
    old_pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = (
        str(BACKEND_ROOT) if not old_pythonpath
        else f"{BACKEND_ROOT}{os.pathsep}{old_pythonpath}"
    )

    services: List[ServiceProc] = []

    try:
        # 1) 流服务（RTSP → WebSocket）—— 非核心，崩溃自动重启
        services.append(
            spawn(
                [sys.executable, "-m", "src.streaming.server", "start", "--port", str(stream_port)],
                name="stream",
                cwd=BACKEND_ROOT,
                env=env,
                essential=False,
            )
        )
        print(f"[main] stream started at http://127.0.0.1:{stream_port}")

        # 2) FastAPI 后端（Dashboard API）
        api_env = env.copy()
        api_env["FRONTEND_API_HOST"] = api_host
        api_env["FRONTEND_API_PORT"] = str(api_port)
        api_env["STREAM_SERVER_URL"] = f"http://127.0.0.1:{stream_port}"
        services.append(
            spawn(
                [sys.executable, "-m", "src.api.frontend_api"],
                name="api",
                cwd=BACKEND_ROOT,
                env=api_env,
            )
        )
        print(f"[main] api started at http://127.0.0.1:{api_port}")

        # 3) 监控逻辑
        services.append(
            spawn(
                [sys.executable, "-m", "src.start_monitoring"],
                name="monitoring",
                cwd=BACKEND_ROOT,
                env=env,
            )
        )
        print("[main] monitoring started")

        if run_frontend_dev:
            # 4) 前端 dev server（可选）
            fe_env = env.copy()
            fe_env["NEXT_PUBLIC_BACKEND_URL"] = f"http://127.0.0.1:{api_port}"
            fe_env["NEXT_PUBLIC_STREAM_URL"] = f"http://127.0.0.1:{stream_port}"
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
                print("[main] frontend not started: pnpm/npm not found in PATH")
            else:
                frontend_dir_env = os.getenv("MAIN_FRONTEND_DIR", "").strip()
                if frontend_dir_env:
                    candidates = [Path(frontend_dir_env).expanduser()]
                else:
                    candidates = [PROJECT_ROOT / "frontend"]

                frontend_dir: Path | None = None
                for cand in candidates:
                    if (cand / "package.json").exists():
                        frontend_dir = cand
                        break

                if frontend_dir is None:
                    print("[main] frontend not started: directory not found "
                          "(set MAIN_FRONTEND_DIR=/path/to/frontend)")
                else:
                    services.append(
                        spawn(frontend_cmd, name="frontend", cwd=frontend_dir, env=fe_env)
                    )
                    print(f"[main] frontend dev started at http://127.0.0.1:{frontend_port}")
        else:
            print("[main] frontend dev not started (set MAIN_RUN_FRONTEND_DEV=1 to enable)")

    except Exception as exc:
        print(f"[main] startup failed: {exc!r}")
        terminate_all(services)
        raise

    print("[main] press Ctrl+C to stop all services")

    def _handle_sig(_sig, _frm):
        print("[main] signal received, stopping services...")
        terminate_all(services)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    try:
        while True:
            for svc in services:
                code = svc.proc.poll()
                if code is None:
                    continue
                print(f"[main] service exited: {svc.name} code={code}")
                if svc.restart_count < MAX_RESTARTS:
                    svc.restart_count += 1
                    print(f"[main] restarting {svc.name} "
                          f"(attempt {svc.restart_count}/{MAX_RESTARTS}) in {RESTART_DELAY}s ...")
                    time.sleep(RESTART_DELAY)
                    svc.proc = subprocess.Popen(
                        svc.cmd, cwd=str(svc.cwd), env=svc.env, start_new_session=True
                    )
                    print(f"[main] {svc.name} restarted (pid={svc.proc.pid})")
                else:
                    print(f"[main] {svc.name} exceeded max restarts ({MAX_RESTARTS})")
                    if svc.essential:
                        print("[main] essential service down — stopping all")
                        terminate_all(services)
                        return 1
                    else:
                        print(f"[main] {svc.name} is non-essential, continuing without it")
            time.sleep(0.5)
    except KeyboardInterrupt:
        terminate_all(services)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
