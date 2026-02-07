"""
事件触发器模块
基于 YOLO 检测结果的状态机，决定何时调用 Agent

状态转换：
- Idle: 空闲状态，无检测
- Suspect: 怀疑状态，检测到目标但未确认
- Alarm: 报警状态，确认异常事件

只在状态转换时触发 Agent 调用
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MonitorState(Enum):
    """监控状态"""
    IDLE = "idle"           # 空闲
    SUSPECT = "suspect"     # 怀疑
    ALARM = "alarm"         # 报警


@dataclass
class DetectionEvent:
    """检测事件"""
    timestamp: datetime
    state: MonitorState
    detections: List[Dict[str, Any]]  # YOLO 检测结果
    frame: Any  # 图像帧（numpy array 或其他格式）
    confidence: float
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "state": self.state.value,
            "detections": self.detections,
            "confidence": self.confidence,
            "description": self.description
        }


@dataclass
class EventTriggerConfig:
    """事件触发器配置"""
    # 检测阈值
    suspect_threshold: int = 2      # 连续检测多少次进入怀疑状态
    alarm_threshold: int = 5        # 连续检测多少次进入报警状态
    idle_threshold: int = 10        # 连续多少次无检测回到空闲状态
    
    # 置信度阈值
    min_confidence: float = 0.5     # 最小置信度
    high_confidence: float = 0.8    # 高置信度阈值
    
    # 目标类别（火灾检测示例）
    target_classes: List[str] = field(default_factory=lambda: ["fire", "smoke"])
    
    # 是否启用 Agent 分析
    enable_agent_on_suspect: bool = True
    enable_agent_on_alarm: bool = True


class EventTrigger:
    """
    事件触发器
    
    核心逻辑：
    1. 接收 YOLO 检测结果
    2. 维护状态机
    3. 在状态转换时返回 True（需要调用 Agent）
    """
    
    def __init__(self, config: EventTriggerConfig):
        self.config = config
        self.state = MonitorState.IDLE
        
        # 计数器
        self.detection_count = 0      # 连续检测到目标的次数
        self.no_detection_count = 0   # 连续未检测到的次数
        
        # 历史记录
        self.event_history: List[DetectionEvent] = []
        self.last_event: Optional[DetectionEvent] = None
        
    def process_detection(
        self, 
        detections: List[Dict[str, Any]], 
        frame: Any
    ) -> tuple[bool, Optional[DetectionEvent]]:
        """
        处理 YOLO 检测结果
        
        Args:
            detections: YOLO 检测结果列表，每个元素包含 {class, confidence, bbox}
            frame: 当前帧图像
            
        Returns:
            (should_call_agent, event): 
                - should_call_agent: 是否应该调用 Agent
                - event: 如果需要调用 Agent，返回事件对象
        """
        # 过滤目标类别和置信度
        filtered = self._filter_detections(detections)
        has_detection = len(filtered) > 0
        
        # 更新计数器
        if has_detection:
            self.detection_count += 1
            self.no_detection_count = 0
        else:
            self.detection_count = 0
            self.no_detection_count += 1
        
        # 状态转换
        old_state = self.state
        new_state = self._update_state()
        
        # 状态改变时触发 Agent
        if old_state != new_state:
            event = self._create_event(new_state, filtered, frame)
            self.event_history.append(event)
            self.last_event = event
            
            should_call = self._should_call_agent(new_state)
            
            logger.info(
                f"状态转换: {old_state.value} → {new_state.value} "
                f"(检测次数: {self.detection_count}, 触发Agent: {should_call})"
            )
            
            return should_call, event
        
        return False, None
    
    def _filter_detections(self, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤检测结果"""
        filtered = []
        for det in detections:
            if (det.get("class") in self.config.target_classes and 
                det.get("confidence", 0) >= self.config.min_confidence):
                filtered.append(det)
        return filtered
    
    def _update_state(self) -> MonitorState:
        """更新状态机"""
        # Idle → Suspect
        if (self.state == MonitorState.IDLE and 
            self.detection_count >= self.config.suspect_threshold):
            self.state = MonitorState.SUSPECT
        
        # Suspect → Alarm
        elif (self.state == MonitorState.SUSPECT and 
              self.detection_count >= self.config.alarm_threshold):
            self.state = MonitorState.ALARM
        
        # Suspect/Alarm → Idle
        elif (self.state in [MonitorState.SUSPECT, MonitorState.ALARM] and 
              self.no_detection_count >= self.config.idle_threshold):
            self.state = MonitorState.IDLE
        
        return self.state
    
    def _should_call_agent(self, new_state: MonitorState) -> bool:
        """判断是否应该调用 Agent"""
        if new_state == MonitorState.SUSPECT:
            return self.config.enable_agent_on_suspect
        elif new_state == MonitorState.ALARM:
            return self.config.enable_agent_on_alarm
        return False
    
    def _create_event(
        self, 
        state: MonitorState, 
        detections: List[Dict[str, Any]], 
        frame: Any
    ) -> DetectionEvent:
        """创建事件对象"""
        confidence = max([d.get("confidence", 0) for d in detections], default=0)
        
        return DetectionEvent(
            timestamp=datetime.now(),
            state=state,
            detections=detections,
            frame=frame,
            confidence=confidence
        )
    
    def get_state(self) -> MonitorState:
        """获取当前状态"""
        return self.state
    
    def get_last_event(self) -> Optional[DetectionEvent]:
        """获取最后一次事件"""
        return self.last_event
    
    def get_event_history(self, limit: int = 10) -> List[DetectionEvent]:
        """获取事件历史"""
        return self.event_history[-limit:]
    
    def reset(self):
        """重置状态"""
        self.state = MonitorState.IDLE
        self.detection_count = 0
        self.no_detection_count = 0
        logger.info("EventTrigger 已重置")
