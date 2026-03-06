#!/usr/bin/env python3
"""Run monitoring system with optional interactive chat."""

import argparse
import logging
from dataclasses import asdict

from config import load_config, MonitoringConfig
from src.utils.runtime_env import configure_runtime_env

configure_runtime_env()

from src.agent_interface import AgentInterface
from src.monitoring_system import MonitoringSystem


def run_interactive(system: MonitoringSystem) -> None:
    print("\n" + "=" * 60)
    print("监控系统交互界面")
    print("=" * 60)
    print("输入问题与系统对话，输入 /exit 退出")
    print("=" * 60 + "\n")

    while True:
        try:
            query = input("👤 您: ").strip()
            if not query:
                continue
            if query == "/exit":
                system.stop()
                break
            response = system.handle_user_query(query, context={"current_state": "MONITORING"})
            print(f"🤖 Agent: {response.message}")
        except KeyboardInterrupt:
            system.stop()
            break
        except Exception as exc:
            logging.getLogger(__name__).error("交互异常: %s", exc, exc_info=True)


def start_monitoring(args: argparse.Namespace, defaults) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = MonitoringConfig(
        **{
            **asdict(defaults),
            "rtsp_url": args.rtsp,
            "rtsp_fps": args.fps,
            "yolo_model": args.model,
            "yolo_device": args.device,
        }
    )

    interface = AgentInterface()
    system = MonitoringSystem(config, interface)

    if args.interactive:
        thread = system.start_in_thread()
        run_interactive(system)
        thread.join()
    else:
        system.run()


def main() -> None:
    global_config = load_config()
    defaults = global_config.monitoring
    parser = argparse.ArgumentParser(description="Run monitoring system")
    parser.add_argument("--rtsp", type=str, default=defaults.rtsp_url)
    parser.add_argument("--fps", type=int, default=defaults.rtsp_fps)
    parser.add_argument("--model", type=str, default=defaults.yolo_model)
    parser.add_argument("--device", type=str, default=defaults.yolo_device)
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    if not args.rtsp:
        parser.error("--rtsp is required (or set monitoring.rtsp_url in config.json).")
    start_monitoring(args, defaults)


if __name__ == "__main__":
    main()
