"""
Agent Interface 测试和演示脚本
展示了如何使用接口层处理事件和用户查询
"""

import logging
from datetime import datetime, timedelta
import numpy as np
from pathlib import Path

from src.monitoring_system.agent_interface import (
    AgentInterface,
    ConversationMemory,
    MessageRole,
    AgentResponse,
)
from src.monitoring_system.event_trigger import DetectionEvent, MonitorState

# 创建 agent 日志目录
LOG_DIR = Path("./logs/agent")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 配置日志
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"test_agent_{TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# 模拟 Agent
# ============================================================================

class MockAgent:
    """
    模拟 Agent，用于测试
    实现 invoke 方法以兼容 LangChain 风格
    """
    
    def invoke(self, input_data):
        """模拟 Agent 的推理过程"""
        if isinstance(input_data, dict) and "messages" in input_data:
            content = input_data["messages"][0].get("content", "")
        else:
            content = str(input_data)
        
        # 根据内容生成模拟响应
        if "火" in content or "fire" in content.lower():
            return {
                "messages": [{
                    "content": (
                        "严重警告！检测到火焰迹象。这是一个紧急情况，需要立即采取行动。\n"
                        "建议：1. 立即疏散人员 2. 启动灭火系统 3. 通知消防队"
                    )
                }]
            }
        elif "异常" in content or "alarm" in content.lower():
            return {
                "messages": [{
                    "content": (
                        "检测到异常活动。当前监控状态异常，建议进一步调查。\n"
                        "建议：1. 加强人工监控 2. 检查摄像头状态 3. 查看录像回放"
                    )
                }]
            }
        else:
            return {
                "messages": [{
                    "content": (
                        "当前监控状态正常，未检测到明显异常。"
                        "继续进行定期监控。"
                    )
                }]
            }


# ============================================================================
# 演示函数
# ============================================================================

def demo_basic_usage():
    """基础使用演示"""
    print("\n" + "="*70)
    print("演示 1: 基础使用")
    print("="*70)
    
    # 初始化
    agent = MockAgent()
    interface = AgentInterface(agent, enable_memory=True)
    
    # 创建模拟事件
    event = DetectionEvent(
        timestamp=datetime.now(),
        state=MonitorState.ALARM,
        detections=[
            {"class": "fire", "confidence": 0.95, "bbox": [100, 100, 200, 200]},
            {"class": "smoke", "confidence": 0.87, "bbox": [150, 80, 250, 180]}
        ],
        frame=None,
        confidence=0.95,
        description="检测到火焰和烟雾"
    )
    
    # 处理事件
    print("\n📍 处理检测事件...")
    response = interface.handle_event(event)
    
    print(f"✅ 成功: {response.success}")
    print(f"📊 严重程度: {response.severity}")
    print(f"🚨 是否升级: {response.should_escalate}")
    print(f"💬 Agent 分析:\n{response.message}")
    print(f"📝 元数据: {response.metadata}")


def demo_conversation_memory():
    """对话记忆演示"""
    print("\n" + "="*70)
    print("演示 2: 对话记忆管理")
    print("="*70)
    
    agent = MockAgent()
    interface = AgentInterface(agent, enable_memory=True)
    
    # 多轮对话
    queries = [
        "最近有什么异常吗？",
        "刚才的检测准确吗？",
        "需要采取什么措施？",
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"\n【第 {i} 轮】用户: {query}")
        
        response = interface.handle_user_query(query)
        print(f"Agent: {response.message}")
        
        # 显示当前对话历史
        print(f"\n📋 当前对话记忆 ({len(interface.conversation_memory.messages)} 条):")
        for msg in interface.conversation_memory.get_recent_messages(n=4):
            role_label = "👤 用户" if msg.role == MessageRole.USER else "🤖 Agent"
            content = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
            print(f"  {role_label}: {content}")


def demo_context_enrichment():
    """上下文丰富演示"""
    print("\n" + "="*70)
    print("演示 3: 上下文丰富")
    print("="*70)
    
    agent = MockAgent()
    interface = AgentInterface(agent, enable_memory=True)
    
    # 创建一些历史事件
    base_time = datetime.now()
    events = [
        DetectionEvent(
            timestamp=base_time - timedelta(minutes=5),
            state=MonitorState.SUSPECT,
            detections=[{"class": "person", "confidence": 0.75}],
            frame=None,
            confidence=0.75
        ),
        DetectionEvent(
            timestamp=base_time - timedelta(minutes=2),
            state=MonitorState.ALARM,
            detections=[{"class": "smoke", "confidence": 0.85}],
            frame=None,
            confidence=0.85
        ),
        DetectionEvent(
            timestamp=base_time,
            state=MonitorState.ALARM,
            detections=[
                {"class": "fire", "confidence": 0.95},
                {"class": "smoke", "confidence": 0.90}
            ],
            frame=None,
            confidence=0.95
        ),
    ]
    
    # 添加事件到接口的历史中
    for event in events:
        interface.last_events.append(event)
    
    # 使用丰富的上下文查询
    print("\n📍 用户查询（带详细上下文）...")
    response = interface.handle_user_query(
        query="目前的情况严重吗？需要立即采取行动吗？",
        context={
            "current_state": "ALARM",
            "alarm_count": 3,
            "duration": "10 分钟",
            "recent_events": events
        }
    )
    
    print(f"💬 Agent 响应:\n{response.message}")


def demo_unified_interface():
    """统一入口演示"""
    print("\n" + "="*70)
    print("演示 4: 统一入口 process()")
    print("="*70)
    
    agent = MockAgent()
    interface = AgentInterface(agent, enable_memory=True)
    
    # 事件驱动
    print("\n【事件驱动模式】")
    event = DetectionEvent(
        timestamp=datetime.now(),
        state=MonitorState.ALARM,
        detections=[{"class": "fire", "confidence": 0.95}],
        frame=None,
        confidence=0.95
    )
    
    response = interface.process({
        "type": "event",
        "event": event
    })
    print(f"事件响应: {response.severity} - {response.message[:60]}...")
    
    # 用户驱动
    print("\n【用户驱动模式】")
    response = interface.process({
        "type": "query",
        "query": "现在是什么情况？"
    })
    print(f"查询响应: {response.message[:80]}...")


def demo_memory_management():
    """记忆管理演示"""
    print("\n" + "="*70)
    print("演示 5: 记忆管理")
    print("="*70)
    
    agent = MockAgent()
    memory = ConversationMemory(max_history=5)  # 限制为 5 条
    interface = AgentInterface(agent, conversation_memory=memory)
    
    # 添加多条消息
    print("\n📍 添加 8 条消息到只能保存 5 条的记忆...")
    for i in range(8):
        interface.handle_user_query(f"问题 {i+1}")
    
    print(f"✅ 记忆中的消息数: {len(interface.conversation_memory.messages)}")
    print(f"   (最多保留: {interface.conversation_memory.max_history} 条)")
    
    # 显示当前消息
    print("\n📋 当前记忆内容:")
    for msg in interface.conversation_memory.get_recent_messages():
        role = "👤" if msg.role == MessageRole.USER else "🤖"
        print(f"  {role} {msg.content[:40]}...")
    
    # 清空记忆
    print("\n🗑️  清空记忆...")
    interface.clear_memory()
    print(f"✅ 记忆消息数: {len(interface.conversation_memory.messages)}")


def demo_error_handling():
    """错误处理演示"""
    print("\n" + "="*70)
    print("演示 6: 错误处理")
    print("="*70)
    
    agent = MockAgent()
    interface = AgentInterface(agent, enable_memory=True)
    
    # 无效的输入类型
    print("\n【错误 1: 无效的输入类型】")
    response = interface.process({
        "type": "invalid_type",
        "data": "something"
    })
    print(f"结果: {response.success}, 错误: {response.message}")
    
    # 缺少必要字段
    print("\n【错误 2: 缺少 event 字段】")
    response = interface.process({
        "type": "event"
    })
    print(f"结果: {response.success}, 错误: {response.message}")
    
    # 空查询
    print("\n【错误 3: 空查询字符串】")
    response = interface.process({
        "type": "query",
        "query": ""
    })
    print(f"结果: {response.success}")
    if response.message:
        print(f"响应: {response.message}")


def demo_severity_evaluation():
    """严重程度评估演示"""
    print("\n" + "="*70)
    print("演示 7: 严重程度自动评估")
    print("="*70)
    
    class SeverityTestAgent:
        """用于测试严重程度评估的 Agent"""
        
        def __init__(self, response_text):
            self.response_text = response_text
        
        def invoke(self, input_data):
            return {
                "messages": [{"content": self.response_text}]
            }
    
    test_cases = [
        ("检测到火灾，需要紧急撤离", "critical"),
        ("发现异常活动，需要注意", "warning"),
        ("当前监控状态正常", "info"),
    ]
    
    print("\n测试不同的 Agent 响应:")
    for response_text, expected_severity in test_cases:
        agent = SeverityTestAgent(response_text)
        interface = AgentInterface(agent, enable_memory=False)
        
        event = DetectionEvent(
            timestamp=datetime.now(),
            state=MonitorState.ALARM,
            detections=[],
            frame=None,
            confidence=0.8
        )
        
        response = interface.handle_event(event)
        severity_match = "✅" if response.severity == expected_severity else "❌"
        
        print(f"\n{severity_match} Response: \"{response_text}\"")
        print(f"   → 严重程度: {response.severity} (期望: {expected_severity})")
        print(f"   → 是否升级: {response.should_escalate}")


# ============================================================================
# 主程序
# ============================================================================

def main():
    """运行所有演示"""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*15 + "Agent Interface 接口层演示" + " "*22 + "║")
    print("╚" + "="*68 + "╝")
    
    demos = [
        ("基础使用", demo_basic_usage),
        ("对话记忆", demo_conversation_memory),
        ("上下文丰富", demo_context_enrichment),
        ("统一入口", demo_unified_interface),
        ("记忆管理", demo_memory_management),
        ("错误处理", demo_error_handling),
        ("严重程度评估", demo_severity_evaluation),
    ]
    
    for i, (name, demo_func) in enumerate(demos, 1):
        try:
            demo_func()
        except Exception as e:
            print(f"\n❌ 演示 {i} ({name}) 失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*70)
    print("✅ 所有演示完成！")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
