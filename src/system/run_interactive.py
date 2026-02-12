"""
监控系统 + 用户对话接口

支持两种模式：
1. 后台监控（事件驱动）
2. 前台对话（用户驱动）
"""

import argparse
import logging
import sys
import threading
import signal
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.frame.monitoring_system import MonitoringSystem, MonitoringSystemConfig

# 创建 agent 日志目录
LOG_DIR = Path("./logs/agent")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 配置日志
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"run_interactive_{TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)


class InteractiveMonitoring:
    """
    交互式监控系统
    
    启动后：
    1. 后台线程持续监控 RTSP 流
    2. 主线程提供命令行对话接口
    """
    
    def __init__(self, system: MonitoringSystem):
        self.system = system
        self.monitoring_thread = None
        self.logger = logging.getLogger(__name__)
    
    def start(self):
        """启动系统"""
        # 在主线程中注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # 启动监控线程
        self.monitoring_thread = threading.Thread(
            target=self.system.run,
            daemon=True
        )
        self.monitoring_thread.start()
        self.logger.info("✅ 后台监控已启动")
        
        # 启动对话循环
        self.chat_loop()
    
    def _signal_handler(self, sig, frame):
        """主线程信号处理器"""
        self.logger.info("\n收到停止信号，正在关闭...")
        self.system.stop()
        sys.exit(0)
    
    def chat_loop(self):
        """对话循环"""
        print("\n" + "=" * 60)
        print("监控系统对话界面")
        print("=" * 60)
        print("可以询问:")
        print("  - '现在现场怎么样？'")
        print("  - '刚才那是误报吗？'")
        print("  - '最近有什么异常？'")
        print("输入 'quit' 或 'exit' 退出")
        print("=" * 60 + "\n")
        
        while True:
            try:
                # 获取用户输入
                query = input("\n👤 你: ").strip()
                
                if not query:
                    continue
                
                # 退出命令
                if query.lower() in ['quit', 'exit', 'q']:
                    self.logger.info("用户请求退出")
                    self.system.stop()
                    break
                
                # 特殊命令
                if query.lower() == 'status':
                    self._print_status()
                    continue
                
                # 调用 Agent
                print("🤖 Agent: ", end='', flush=True)
                response = self.system.handle_user_query(query)
                print(response.message)
            
            except KeyboardInterrupt:
                self.logger.info("\n用户中断")
                self.system.stop()
                break
            except Exception as e:
                self.logger.error(f"处理查询失败: {e}")
    
    def _print_status(self):
        """打印系统状态"""
        state = self.system.event_trigger.get_state()
        print(f"\n系统状态:")
        print(f"  当前状态: {state.value}")
        print(f"  处理帧数: {self.system.frame_count}")
        print(f"  事件次数: {self.system.event_count}")
        
        recent_events = self.system.event_trigger.get_event_history(limit=3)
        if recent_events:
            print(f"  最近事件:")
            for evt in recent_events:
                print(f"    - [{evt.timestamp.strftime('%H:%M:%S')}] "
                      f"{evt.state.value} ({len(evt.detections)} 检测)")


def main():
    parser = argparse.ArgumentParser(description='启动交互式监控系统')
    
    parser.add_argument('--rtsp', type=str, default='rtsp://127.0.0.1:8554/mystream')
    parser.add_argument('--fps', type=int, default=5)
    parser.add_argument('--model', type=str, default='yolov8n.pt')
    parser.add_argument('--device', type=str, default='cuda:0')
    parser.add_argument('--verbose', action='store_true')
    
    args = parser.parse_args()
    
    # 配置日志
    level = logging.DEBUG if args.verbose else logging.INFO
    
    # 创建日志目录
    log_dir = Path(__file__).parent.parent.parent / 'logs' / 'rtsp'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成带时间戳的日志文件名
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f"monitoring_{timestamp}.log"
    frame_log_file = log_dir / f"frames_{timestamp}.log"
    
    # 主日志配置（关键信息输出到控制台和文件）
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(str(log_file)),
            logging.StreamHandler(sys.stderr)  # 错误输出到 stderr，不干扰对话
        ]
    )
    
    # 创建帧日志处理器（只输出到文件，不输出到控制台）
    frame_logger = logging.getLogger('frame_logger')
    frame_logger.setLevel(logging.INFO)
    frame_handler = logging.FileHandler(str(frame_log_file))
    frame_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    frame_logger.addHandler(frame_handler)
    frame_logger.propagate = False  # 不传播到根日志记录器
    
    logger = logging.getLogger(__name__)
    
    try:
        # 创建配置
        config = MonitoringSystemConfig(
            rtsp_url=args.rtsp,
            rtsp_fps=args.fps,
            yolo_model=args.model,
            yolo_device=args.device
        )
        
        # 创建 Agent
        logger.info("正在初始化 Agent...")
        
        # 使用模拟 Agent（不需要 LLM 服务）
        class MockAgent:
            """模拟 Agent，用于测试"""
            def invoke(self, input_data, config=None):
                import random
                from datetime import datetime
                
                # 提取消息内容
                messages = input_data.get("messages", [])
                if messages:
                    user_msg = messages[-1].get("content", "")
                else:
                    user_msg = ""
                
                # 模拟分析结果
                responses = [
                    "检测到人员活动，当前状态正常。建议继续监控。",
                    "发现多个目标，可能存在异常情况，建议关注。",
                    "现场人员数量较多，请注意人员安全。",
                    "检测到连续活动，暂未发现明显异常。",
                    "监控区域内活动频繁，建议加强巡查。"
                ]
                
                response_text = random.choice(responses)
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                return {
                    "messages": [{
                        "role": "assistant",
                        "content": f"[{timestamp}] Mock Agent 分析: {response_text}"
                    }]
                }
        
        agent = MockAgent()
        logger.info("✅ 使用 Mock Agent（模拟模式）")
        
        # 创建监控系统，传入帧日志记录器
        system = MonitoringSystem(config, agent, frame_logger=frame_logger)
        
        # 启动交互式界面
        interactive = InteractiveMonitoring(system)
        interactive.start()
        
    except Exception as e:
        logger.error(f"系统异常: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
