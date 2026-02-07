#!/usr/bin/env python3
"""
CLI 应用 - 监控系统交互终端
提供真实的用户-Agent 交互界面，支持多轮对话和上下文维护

使用方式：
    python cli_app.py
"""

import logging
from datetime import datetime
from pathlib import Path
from config import GlobalConfig
from src.hybrid_monitoring_agent import HybridMonitoringAgent
from src.agent_interface import AgentInterface, MessageRole

# 创建 agent 日志目录
LOG_DIR = Path("./logs/agent")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 配置日志
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"cli_app_{TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()  # 同时输出到控制台
    ]
)
logger = logging.getLogger(__name__)


class InteractiveChat:
    """交互式对话管理"""
    
    def __init__(self, agent_interface: AgentInterface):
        self.interface = agent_interface
        self.chat_history = []
    
    def run(self):
        """运行交互式对话循环"""
        print("\n" + "=" * 70)
        print("🤖 监控 Agent 交互系统 - 欢迎使用")
        print("=" * 70)
        print("输入您的问题，Agent 将为您分析监控情况。")
        print("命令:")
        print("  - 输入问题：直接输入任何问题")
        print("  - /history：查看对话历史")
        print("  - /clear：清空对话历史")
        print("  - /exit：退出程序")
        print("=" * 70 + "\n")
        
        while True:
            try:
                # 获取用户输入
                user_input = input("👤 您: ").strip()
                
                if not user_input:
                    continue
                
                # 处理特殊命令
                if user_input == "/exit":
                    print("\n👋 再见！")
                    break
                elif user_input == "/history":
                    self._show_history()
                    continue
                elif user_input == "/clear":
                    self._clear_history()
                    continue
                
                # 普通对话
                self._handle_user_query(user_input)
                
            except KeyboardInterrupt:
                print("\n\n👋 程序已中断")
                break
            except Exception as e:
                print(f"\n❌ 出错: {e}")
                logger.error(f"交互循环错误: {e}", exc_info=True)
    
    def _handle_user_query(self, query: str):
        """处理用户查询"""
        print("\n⏳ Agent 正在分析...")
        
        try:
            # 调用 Agent 接口
            response = self.interface.handle_user_query(
                query,
                context={
                    "recent_events": self.interface.last_events,
                    "current_state": "MONITORING"
                }
            )
            
            # 显示响应
            print("\n" + "-" * 70)
            if response.success:
                print(f"🤖 Agent: {response.message}")
                
                # 仅在需要升级时显示提示
                if response.should_escalate:
                    print("\n🔔 提示: 需要升级处理")
            else:
                print(f"❌ Agent 错误: {response.message}")
            
            print("-" * 70 + "\n")
            
            # 记录到对话历史
            self.chat_history.append({
                "timestamp": datetime.now(),
                "type": "user",
                "content": query
            })
            self.chat_history.append({
                "timestamp": datetime.now(),
                "type": "agent",
                "content": response.message,
                "severity": response.severity,
                "escalate": response.should_escalate
            })
            
        except Exception as e:
            print(f"\n❌ 调用 Agent 失败: {e}")
            logger.error(f"Agent 调用错误: {e}", exc_info=True)
    
    def _show_history(self):
        """显示对话历史"""
        if not self.chat_history:
            print("\n📋 对话历史为空\n")
            return
        
        print("\n" + "=" * 70)
        print("📋 对话历史")
        print("=" * 70)
        
        for i, msg in enumerate(self.chat_history, 1):
            timestamp = msg["timestamp"].strftime("%H:%M:%S")
            
            if msg["type"] == "user":
                print(f"\n[{i}] 👤 用户 ({timestamp}):")
                print(f"    {msg['content']}")
            else:
                print(f"\n[{i}] 🤖 Agent ({timestamp}):")
                print(f"    {msg['content']}")
                print(f"    严重程度: {msg.get('severity', 'unknown')}")
        
        print("\n" + "=" * 70 + "\n")
    
    def _clear_history(self):
        """清空对话历史"""
        self.chat_history.clear()
        self.interface.clear_memory()
        self.interface.clear_events()
        print("\n✅ 对话历史已清空\n")


def main():
    """主函数"""
    try:
        # 初始化 Agent
        print("初始化 Agent...")
        config = GlobalConfig()
        hybrid_agent = HybridMonitoringAgent(config)
        
        # 创建接口
        interface = AgentInterface(hybrid_agent)
        
        # 启动交互式对话
        chat = InteractiveChat(interface)
        chat.run()
        
    except Exception as e:
        logger.error(f"启动失败: {e}", exc_info=True)
        print(f"❌ 启动失败: {e}")


if __name__ == "__main__":
    main()
