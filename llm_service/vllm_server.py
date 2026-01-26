#!/usr/bin/env python3
"""
vLLM服务器管理器
提供启动、检测状态、停止vLLM服务器的功能
"""

import os
import time
import subprocess
import threading
import queue
from typing import Optional


class VLLMServerManager:
    """vLLM服务器管理器"""

    def __init__(self):
        self.pid_file = "./outputs/vllm_server.pid"
        self.log_dir = "./outputs/logs"
        self.base_url = "http://127.0.0.1:8000/v1"
        self.health_check_url = "http://127.0.0.1:8000/health"

    def is_server_running(self) -> bool:
        """检查vLLM服务器是否运行"""
        try:
            import requests
            response = requests.get(self.health_check_url, timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def get_server_pid(self) -> Optional[int]:
        """获取服务器PID"""
        try:
            if os.path.exists(self.pid_file):
                with open(self.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)  # 检查进程是否存在
                return pid
        except Exception:
            pass
        return None

    def start_server(self) -> bool:
        """启动vLLM服务器"""

        if self.is_server_running():
            print("✅ vLLM服务器已在运行")
            return True

        print("🚀 启动vLLM服务器...")

        os.makedirs(self.log_dir, exist_ok=True)

        def read_output(pipe, output_queue):
            """读取子进程输出的线程函数"""
            try:
                for line in iter(pipe.readline, ''):
                    if line:
                        output_queue.put(line.rstrip())
                pipe.close()
            except Exception:
                pass

        try:
            process = subprocess.Popen(
                ["./scripts/run_qwen_vl.sh"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            print(f"📋 启动脚本进程已启动，PID: {process.pid}")

            output_queue = queue.Queue()
            output_thread = threading.Thread(target=read_output, args=(process.stdout, output_queue))
            output_thread.daemon = True
            output_thread.start()

            # 监控启动日志（最多等待180秒）
            start_time = time.time()
            while time.time() - start_time < 180:
                while not output_queue.empty():
                    line = output_queue.get_nowait()
                    print(f"📝 {line}")
                    if "Application startup complete" in line:
                        print("🎉 vLLM服务器启动完成!")
                        return True
                if process.poll() is not None:
                    break
                time.sleep(0.5)

            if process.returncode not in (None, 0):
                print(f"❌ 启动脚本失败，返回码: {process.returncode}")
                return False

            # 启动超时后检测服务器状态
            if self.is_server_running():
                print("✅ vLLM服务器已就绪!")
                return True
            else:
                print("⚠️ 服务器启动超时或未就绪")
                return False

        except Exception as e:
            print(f"❌ 启动vLLM服务器时出错: {e}")
            return False

    def stop_server(self) -> bool:
        """停止vLLM服务器"""
        pid = self.get_server_pid()
        if pid:
            try:
                os.kill(pid, 9)
                print(f"✅ 已停止vLLM服务器 (PID: {pid})")
                return True
            except Exception as e:
                print(f"❌ 停止服务器时出错: {e}")
                return False

        # 尝试使用pkill
        try:
            subprocess.run(["pkill", "-f", "vllm.entrypoints.openai.api_server"], capture_output=True)
            print("✅ 已通过pkill停止vLLM服务器")
            return True
        except Exception as e:
            print(f"⚠️ pkill停止失败: {e}")

        print("⚠️ 未找到运行的vLLM服务器")
        return False


if __name__ == "__main__":
    manager = VLLMServerManager()

    import argparse

    parser = argparse.ArgumentParser(description="vLLM服务器管理工具")
    parser.add_argument("command", choices=["start", "stop", "status"], help="命令: start 启动, stop 停止, status 状态检测")
    args = parser.parse_args()

    if args.command == "start":
        success = manager.start_server()
        exit(0 if success else 1)
    elif args.command == "stop":
        success = manager.stop_server()
        exit(0 if success else 1)
    elif args.command == "status":
        running = manager.is_server_running()
        print(f"vLLM服务器运行状态: {'运行中' if running else '未运行'}")
        exit(0 if running else 1)
