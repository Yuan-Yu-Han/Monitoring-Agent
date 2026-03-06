#!/usr/bin/env python3
"""
Chat Agent - 独立聊天脚本（无需监控系统）
专注于与 Agent 对话，分析历史图片、查询统计信息等

特性：
- 🎯 纯对话模式，无需启动监控系统
- 🔥 自动识别和使用 Skills
- 📊 实时显示工具调用过程
- 💾 支持保存对话记录
- 🎨 美化的输出界面

使用方式：
    python src/chat_agent.py
"""

import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.runtime_env import configure_runtime_env

configure_runtime_env()

from src.agent_interface import AgentInterface

# 配置日志（只记录到文件，不打印到控制台）
LOG_DIR = Path("./logs/chat")
LOG_DIR.mkdir(parents=True, exist_ok=True)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"chat_agent_{TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8')
        # 不添加 StreamHandler，避免日志污染输出
    ]
)
logger = logging.getLogger(__name__)


class ChatSession:
    """聊天会话管理"""

    def __init__(self):
        self.interface = AgentInterface()
        self.chat_history = []
        self.start_time = datetime.now()
        self.message_count = 0
        self.tool_call_count = 0

    def run(self):
        """运行聊天会话"""
        self._print_welcome()

        while True:
            try:
                # 获取用户输入
                user_input = self._get_user_input()

                if not user_input:
                    continue

                # 处理命令
                if user_input.startswith("/"):
                    if not self._handle_command(user_input):
                        break  # /exit 命令返回 False
                    continue

                # 处理普通对话
                self._handle_chat(user_input)

            except KeyboardInterrupt:
                print("\n\n⚠️  检测到 Ctrl+C")
                if self._confirm_exit():
                    break
            except Exception as e:
                print(f"\n❌ 错误: {e}")
                logger.error(f"会话错误: {e}", exc_info=True)

        self._print_goodbye()

    def _print_welcome(self):
        """打印欢迎信息"""
        print("\n" + "="*70)
        print("🤖  监控 Agent 聊天系统")
        print("="*70)
        print("\n💡 这是一个纯对话模式，无需启动监控系统")
        print("   你可以让 Agent 分析历史图片、查询统计信息等\n")

        print("🔥 可用的 Skills（推荐使用）:")
        print("   1. analyze_monitoring_event - 一键分析事件")
        print("   2. quick_detect - 快速检测图片")
        print("   3. batch_analyze - 批量分析")
        print("   4. compare_events - 对比分析\n")

        print("💬 命令列表:")
        print("   /help      - 显示帮助信息")
        print("   /skills    - 显示 Skills 详细说明")
        print("   /history   - 查看对话历史")
        print("   /stats     - 查看会话统计")
        print("   /save      - 保存对话记录")
        print("   /clear     - 清空对话历史")
        print("   /exit      - 退出程序")
        print("="*70 + "\n")

    def _get_user_input(self) -> str:
        """获取用户输入"""
        try:
            return input("👤 您: ").strip()
        except EOFError:
            return "/exit"

    def _handle_command(self, command: str) -> bool:
        """处理命令，返回 False 表示退出"""
        cmd = command.lower().split()[0]

        if cmd == "/exit" or cmd == "/quit":
            return False
        elif cmd == "/help":
            self._show_help()
        elif cmd == "/skills":
            self._show_skills()
        elif cmd == "/history":
            self._show_history()
        elif cmd == "/stats":
            self._show_stats()
        elif cmd == "/save":
            self._save_history()
        elif cmd == "/clear":
            self._clear_history()
        else:
            print(f"❌ 未知命令: {command}")
            print("   输入 /help 查看可用命令")

        return True

    def _handle_chat(self, query: str):
        """处理聊天消息"""
        self.message_count += 1

        # 显示思考提示
        print("\n⏳ Agent 正在思考...")

        try:
            # 调用 Agent
            response = self.interface.handle_user_query(
                query,
                context={
                    "session_id": f"chat_{TIMESTAMP}",
                    "message_count": self.message_count
                }
            )

            # 检查是否需要审批
            if self.interface.last_interrupt:
                print("\n⚠️  Agent 正在等待您的审批...")
                self._handle_approval()
                return

            # 显示响应
            self._print_response(response)

            # 记录历史
            self._record_message(query, response)

        except Exception as e:
            print(f"\n❌ Agent 调用失败: {e}")
            logger.error(f"Agent 错误: {e}", exc_info=True)

    def _handle_approval(self):
        """处理人工审批"""
        print("\n" + "-"*70)
        print("🔔 Agent 请求执行操作，需要您的审批")

        # 显示中断信息
        if self.interface.last_interrupt:
            print(f"\n操作: {self.interface.last_interrupt}")

        print("\n选项:")
        print("  [y] 批准执行")
        print("  [n] 拒绝执行")
        print("  [v] 查看详情")
        print("-"*70)

        while True:
            choice = input("\n您的决定 (y/n/v): ").strip().lower()

            if choice == "y":
                print("\n✅ 已批准，继续执行...")
                try:
                    response_text = self.interface.resume_with_decision("approve")
                    print(f"\n🤖 Agent: {response_text}")
                except Exception as e:
                    print(f"\n❌ 恢复执行失败: {e}")
                break
            elif choice == "n":
                print("\n❌ 已拒绝")
                try:
                    self.interface.resume_with_decision("reject")
                except Exception:
                    pass
                break
            elif choice == "v":
                print(f"\n详情: {json.dumps(self.interface.last_interrupt, indent=2)}")
            else:
                print("❌ 无效选项，请输入 y/n/v")

    def _print_response(self, response):
        """打印 Agent 响应"""
        print("\n" + "-"*70)

        # 根据严重程度选择图标
        severity_icons = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🚨",
            "error": "❌"
        }
        icon = severity_icons.get(response.severity, "💬")

        print(f"{icon} Agent:")
        print()

        # 分段显示消息（处理长文本）
        message_lines = response.message.split("\n")
        for line in message_lines:
            if line.strip():
                print(f"  {line}")
            else:
                print()

        # 显示元数据（如果有）
        if response.metadata:
            if "event_state" in response.metadata:
                print(f"\n  📊 事件状态: {response.metadata['event_state']}")
            if "detection_count" in response.metadata:
                print(f"  🔍 检测数量: {response.metadata['detection_count']}")

        print("-"*70 + "\n")

    def _record_message(self, query: str, response):
        """记录消息到历史"""
        self.chat_history.append({
            "timestamp": datetime.now().isoformat(),
            "type": "user",
            "content": query
        })
        self.chat_history.append({
            "timestamp": datetime.now().isoformat(),
            "type": "agent",
            "content": response.message,
            "severity": response.severity,
            "metadata": response.metadata
        })

    def _show_help(self):
        """显示帮助信息"""
        print("\n" + "="*70)
        print("📖 帮助信息")
        print("="*70)
        print("\n【基础命令】")
        print("  /help      - 显示此帮助信息")
        print("  /exit      - 退出程序")
        print()
        print("【对话管理】")
        print("  /history   - 查看完整对话历史")
        print("  /clear     - 清空对话历史和上下文")
        print("  /save      - 保存对话记录到文件")
        print()
        print("【信息查询】")
        print("  /skills    - 显示可用 Skills 的详细说明")
        print("  /stats     - 查看会话统计信息")
        print()
        print("【使用示例】")
        print("  👤 分析事件 event_001")
        print("  👤 看看 inputs 目录下有什么图片")
        print("  👤 对比今天早上和现在的监控画面")
        print("  👤 批量分析 outputs/alarm 目录")
        print("="*70 + "\n")

    def _show_skills(self):
        """显示 Skills 详细说明"""
        print("\n" + "="*70)
        print("🔥 可用的 Skills 详细说明")
        print("="*70)

        skills_info = [
            {
                "name": "analyze_monitoring_event",
                "desc": "【最常用】一键分析监控事件",
                "usage": "分析事件 event_20240315_001",
                "params": "event_id 或 query、severity、save_report"
            },
            {
                "name": "quick_detect",
                "desc": "快速检测图片中的目标",
                "usage": "检测图片 camera_01.jpg",
                "params": "event_id 或 query、draw_boxes"
            },
            {
                "name": "batch_analyze",
                "desc": "批量分析多张图片",
                "usage": "批量分析 inputs 目录下的图片",
                "params": "directory、pattern、max_images"
            },
            {
                "name": "compare_events",
                "desc": "对比两个事件的差异",
                "usage": "对比 event_001 和 event_002",
                "params": "event_id_1/query_1、event_id_2/query_2"
            }
        ]

        for i, skill in enumerate(skills_info, 1):
            print(f"\n{i}. {skill['name']}")
            print(f"   📝 {skill['desc']}")
            print(f"   💡 示例: {skill['usage']}")
            print(f"   ⚙️  参数: {skill['params']}")

        print("\n" + "="*70 + "\n")

    def _show_history(self):
        """显示对话历史"""
        if not self.chat_history:
            print("\n📋 对话历史为空\n")
            return

        print("\n" + "="*70)
        print(f"📋 对话历史（共 {len(self.chat_history)//2} 轮）")
        print("="*70)

        for i in range(0, len(self.chat_history), 2):
            user_msg = self.chat_history[i]
            agent_msg = self.chat_history[i+1] if i+1 < len(self.chat_history) else None

            # 用户消息
            time_str = datetime.fromisoformat(user_msg["timestamp"]).strftime("%H:%M:%S")
            print(f"\n[{i//2 + 1}] 👤 ({time_str})")
            print(f"    {user_msg['content']}")

            # Agent 响应
            if agent_msg:
                time_str = datetime.fromisoformat(agent_msg["timestamp"]).strftime("%H:%M:%S")
                severity_icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(
                    agent_msg.get("severity", "info"), "💬"
                )
                print(f"\n    {severity_icon} Agent ({time_str})")

                # 显示响应摘要（前100字符）
                content = agent_msg["content"]
                if len(content) > 100:
                    print(f"    {content[:100]}...")
                else:
                    print(f"    {content}")

        print("\n" + "="*70 + "\n")

    def _show_stats(self):
        """显示会话统计"""
        duration = (datetime.now() - self.start_time).total_seconds()
        minutes = int(duration // 60)
        seconds = int(duration % 60)

        print("\n" + "="*70)
        print("📊 会话统计")
        print("="*70)
        print(f"\n⏱️  会话时长: {minutes} 分 {seconds} 秒")
        print(f"💬 对话轮数: {len(self.chat_history)//2}")
        print(f"📝 消息总数: {len(self.chat_history)}")
        print(f"🔧 工具调用: {self.tool_call_count} 次")

        # 统计 Agent 响应的严重程度分布
        severity_counts = {"info": 0, "warning": 0, "critical": 0}
        for msg in self.chat_history:
            if msg["type"] == "agent":
                severity = msg.get("severity", "info")
                severity_counts[severity] = severity_counts.get(severity, 0) + 1

        if sum(severity_counts.values()) > 0:
            print(f"\n📈 响应分布:")
            print(f"   ℹ️  Info: {severity_counts['info']}")
            print(f"   ⚠️  Warning: {severity_counts['warning']}")
            print(f"   🚨 Critical: {severity_counts['critical']}")

        print(f"\n📄 日志文件: {LOG_FILE}")
        print("="*70 + "\n")

    def _save_history(self):
        """保存对话历史到文件"""
        if not self.chat_history:
            print("\n⚠️  对话历史为空，无需保存\n")
            return

        # 创建保存目录
        save_dir = Path("./outputs/chat_history")
        save_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        filename = f"chat_{TIMESTAMP}.json"
        filepath = save_dir / filename

        # 保存为 JSON
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": f"chat_{TIMESTAMP}",
                    "start_time": self.start_time.isoformat(),
                    "end_time": datetime.now().isoformat(),
                    "message_count": len(self.chat_history),
                    "history": self.chat_history
                }, f, ensure_ascii=False, indent=2)

            print(f"\n✅ 对话记录已保存: {filepath}\n")
        except Exception as e:
            print(f"\n❌ 保存失败: {e}\n")
            logger.error(f"保存历史失败: {e}", exc_info=True)

    def _clear_history(self):
        """清空对话历史"""
        if not self.chat_history:
            print("\n⚠️  对话历史已经是空的\n")
            return

        print("\n⚠️  确定要清空对话历史吗？这将重置整个会话。")
        choice = input("   输入 'yes' 确认: ").strip().lower()

        if choice == "yes":
            self.chat_history.clear()
            self.interface.clear_memory()
            self.interface.clear_events()
            self.message_count = 0
            print("\n✅ 对话历史已清空\n")
        else:
            print("\n❌ 已取消\n")

    def _confirm_exit(self) -> bool:
        """确认退出"""
        print("\n确定要退出吗？")
        choice = input("输入 'y' 确认退出: ").strip().lower()
        return choice == "y"

    def _print_goodbye(self):
        """打印退出信息"""
        duration = (datetime.now() - self.start_time).total_seconds()
        minutes = int(duration // 60)
        seconds = int(duration % 60)

        print("\n" + "="*70)
        print("👋 感谢使用监控 Agent 聊天系统")
        print("="*70)
        print(f"\n📊 本次会话统计:")
        print(f"   ⏱️  时长: {minutes} 分 {seconds} 秒")
        print(f"   💬 对话轮数: {len(self.chat_history)//2}")
        print(f"   📄 日志文件: {LOG_FILE}")

        # 询问是否保存历史
        if self.chat_history:
            print("\n是否保存对话记录？")
            choice = input("输入 'y' 保存: ").strip().lower()
            if choice == "y":
                self._save_history()

        print("\n再见！👋\n")


def main():
    """主函数"""
    try:
        session = ChatSession()
        session.run()
    except Exception as e:
        logger.error(f"启动失败: {e}", exc_info=True)
        print(f"\n❌ 启动失败: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
