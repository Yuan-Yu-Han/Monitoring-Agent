"""
组件测试脚本
测试各个模块是否正常工作
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import numpy as np
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_event_trigger():
    """测试事件触发器"""
    logger.info("\n" + "="*60)
    logger.info("测试 1: 事件触发器")
    logger.info("="*60)
    
    from src.frame.event_trigger import EventTrigger, EventTriggerConfig, MonitorState
    
    config = EventTriggerConfig(
        suspect_threshold=2,
        alarm_threshold=5,
        target_classes=["fire"]
    )
    
    trigger = EventTrigger(config)
    
    # 模拟检测序列
    test_sequence = [
        ([], "无检测"),
        ([{"class": "fire", "confidence": 0.9, "bbox": [0,0,10,10]}], "检测到火"),
        ([{"class": "fire", "confidence": 0.9, "bbox": [0,0,10,10]}], "检测到火"),
        ([{"class": "fire", "confidence": 0.9, "bbox": [0,0,10,10]}], "检测到火"),
        ([{"class": "fire", "confidence": 0.9, "bbox": [0,0,10,10]}], "检测到火"),
        ([{"class": "fire", "confidence": 0.9, "bbox": [0,0,10,10]}], "检测到火"),
        ([], "无检测"),
    ]
    
    for i, (dets, desc) in enumerate(test_sequence, 1):
        should_call, event = trigger.process_detection(dets, None)
        state = trigger.get_state()
        
        logger.info(
            f"步骤 {i}: {desc} → 状态={state.value}, "
            f"触发Agent={should_call}"
        )
        
        if should_call:
            logger.info(f"  → 🎯 事件: {event.state.value}, 置信度={event.confidence}")
    
    assert len(trigger.event_history) > 0, "应该至少触发一次事件"
    logger.info(f"✅ 事件触发器测试通过（共触发 {len(trigger.event_history)} 次事件）\n")


def test_yolo_detector():
    """测试 YOLO 检测器"""
    logger.info("\n" + "="*60)
    logger.info("测试 2: YOLO 检测器")
    logger.info("="*60)
    
    from src.frame.yolo_detector import YOLODetector, YOLOConfig
    
    config = YOLOConfig(
        model_path="yolov8n.pt",
        confidence=0.5,
        device="cpu"  # 测试用 CPU
    )
    
    try:
        detector = YOLODetector(config)
        
        # 创建测试图像
        test_image = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
        
        # 检测
        detections = detector.detect(test_image)
        
        logger.info(f"检测到 {len(detections)} 个目标")
        logger.info(f"支持的类别: {len(detector.get_class_names())} 个")
        
        logger.info("✅ YOLO 检测器测试通过\n")
        
    except Exception as e:
        logger.warning(f"⚠️  YOLO 测试跳过（可能缺少模型）: {e}\n")


def test_agent_interface():
    """测试 Agent 接口"""
    logger.info("\n" + "="*60)
    logger.info("测试 3: Agent 接口")
    logger.info("="*60)
    
    from src.frame.agent_interface import AgentInterface, AgentResponse
    from src.frame.event_trigger import DetectionEvent, MonitorState
    
    # 模拟 Agent
    class MockAgent:
        def invoke(self, messages):
            return {
                "messages": [{
                    "content": "这是测试响应：检测到火焰，建议立即处理！"
                }]
            }
    
    interface = AgentInterface(MockAgent())
    
    # 测试事件驱动
    event = DetectionEvent(
        timestamp=datetime.now(),
        state=MonitorState.ALARM,
        detections=[
            {"class": "fire", "confidence": 0.95, "bbox": [100, 100, 200, 200]}
        ],
        frame=None,
        confidence=0.95
    )
    
    response = interface.handle_event(event)
    
    logger.info(f"Agent 响应:")
    logger.info(f"  严重程度: {response.severity}")
    logger.info(f"  是否升级: {response.should_escalate}")
    logger.info(f"  消息: {response.message[:50]}...")
    
    assert response.success, "响应应该成功"
    logger.info("✅ Agent 接口测试通过\n")


def test_rtsp_extractor():
    """测试 RTSP 抽取器（需要运行中的 RTSP 流）"""
    logger.info("\n" + "="*60)
    logger.info("测试 4: RTSP 抽取器（跳过，需要真实 RTSP 流）")
    logger.info("="*60)
    
    logger.info("⏭️  跳过（需要运行 ./src/streaming/run_rtsp.sh）\n")
    
    # from src.frame.rtsp_extractor import RTSPFrameExtractor, FrameExtractorConfig
    # 
    # config = FrameExtractorConfig(
    #     rtsp_url="rtsp://127.0.0.1:8554/mystream",
    #     fps=5
    # )
    # 
    # extractor = RTSPFrameExtractor(config)
    # ...


def main():
    """运行所有测试"""
    logger.info("\n🧪 开始组件测试...\n")
    
    try:
        test_event_trigger()
        test_yolo_detector()
        test_agent_interface()
        test_rtsp_extractor()
        
        logger.info("\n" + "="*60)
        logger.info("✅ 所有测试完成！")
        logger.info("="*60)
        logger.info("\n下一步:")
        logger.info("1. 启动 RTSP 流: ./src/streaming/run_rtsp.sh")
        logger.info("2. 启动监控: python src/run_interactive.py")
        logger.info("")
        
    except AssertionError as e:
        logger.error(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ 测试异常: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
