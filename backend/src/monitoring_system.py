"""
系统层 - MonitoringSystem (重构版)
整合所有组件，实现事件驱动的监控系统

架构：
RTSP → 抽帧 → YOLO → Event Trigger → Agent (仅在状态转换时)

重构要点：
1. 清晰的职责分离（流处理、检测、事件、Agent）
2. 定义清晰的公开接口
3. 支持不同的运行模式（后台线程、单步调试等）
4. 完整的生命周期管理
5. 事件回调和统计查询
"""

import logging
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import signal
import sys
import threading
import json
import time

from config import MonitoringConfig
from config import config as global_config
from src.system.event_trigger import EventTrigger, EventTriggerConfig, DetectionEvent, MonitorState

# 创建 agent 日志目录
LOG_DIR = Path("./logs/agent")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 配置日志
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"monitoring_system_{TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
    ]
)

logger = logging.getLogger(__name__)


# ============================================================================
# 配置和枚举
# ============================================================================

class MonitoringState(Enum):
    """监控系统状态"""
    IDLE = "idle"              # 空闲
    RUNNING = "running"        # 运行中
    PAUSED = "paused"          # 暂停
    STOPPED = "stopped"        # 已停止



@dataclass
class SystemStats:
    """系统统计信息"""
    start_time: Optional[datetime] = None
    frame_count: int = 0
    event_count: int = 0
    alarm_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    
    def reset(self):
        """重置统计"""
        self.start_time = datetime.now()
        self.frame_count = 0
        self.event_count = 0
        self.alarm_count = 0
        self.warning_count = 0
        self.error_count = 0
    
    def get_uptime_seconds(self) -> float:
        """获取运行时间（秒）"""
        if self.start_time is None:
            return 0.0
        return (datetime.now() - self.start_time).total_seconds()
    
    def get_fps(self) -> float:
        """获取实际 FPS"""
        uptime = self.get_uptime_seconds()
        if uptime == 0:
            return 0.0
        return self.frame_count / uptime
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_seconds": self.get_uptime_seconds(),
            "frame_count": self.frame_count,
            "fps": self.get_fps(),
            "event_count": self.event_count,
            "alarm_count": self.alarm_count,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
        }


# ============================================================================
# 核心系统类
# ============================================================================

class MonitoringSystem:
    """
    系统层 - 监控系统 (重构版)
    
    职责：
    1. 管理 RTSP 流读取、YOLO 检测、事件触发等组件
    2. 状态机（idle → running → paused → stopped）
    3. 决定何时调用 Agent（事件驱动）
    4. 维护系统级统计（帧数、事件数）
    
    不关心：
    - Agent 的内部逻辑
    - 对话记忆
    - 具体的应用业务逻辑
    """
    
    def __init__(self, config: MonitoringConfig, agent_interface):
        """
        初始化监控系统
        
        Args:
            config: 配置对象
            agent_interface: Agent 接口（来自接口层）
        """
        self.config = config
        self.agent_interface = agent_interface
        
        # 初始化子模块
        logger.info("🔧 初始化监控系统...")
        self._init_components()
        
        # 状态管理
        self.state = MonitoringState.IDLE
        self.stats = SystemStats()
        
        # 回调函数
        self.on_event: Optional[Callable[[DetectionEvent, Any], None]] = None
        self.on_state_changed: Optional[Callable[[MonitoringState, MonitoringState], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        
        # 线程控制
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()

        # Agent 异步执行管理
        self._agent_threads: List[threading.Thread] = []

        logger.info("✅ 系统初始化完成")
    
    def _init_components(self):
        """初始化各个子模块"""
        # 1. RTSP 抽帧器
        from src.system.rtsp_extractor import RTSPFrameExtractor, FrameExtractorConfig
        self.frame_extractor = RTSPFrameExtractor(
            FrameExtractorConfig(
                rtsp_url=self.config.rtsp_url,
                fps=self.config.rtsp_fps
            )
        )
        logger.info("✓ RTSP 抽帧器初始化完成")

        # 2. YOLO 检测器
        from src.system.yolo_detector import YOLODetector, YOLOConfig
        self.detector = YOLODetector(
            YOLOConfig(
                model_path=self.config.yolo_model,
                confidence=self.config.yolo_confidence,
                device=self.config.yolo_device
            )
        )
        logger.info("✓ YOLO 检测器初始化完成")

        # 3. 事件触发器（必需）
        self.event_trigger = EventTrigger(
            EventTriggerConfig(
                suspect_threshold=self.config.suspect_threshold,
                alarm_threshold=self.config.alarm_threshold,
                idle_threshold=self.config.idle_threshold,
                target_classes=self.config.target_classes
            )
        )
        logger.info("✓ 事件触发器初始化完成")

        # 4. 事件记录 (case store)
        from src.context_engine.memory.case_memory import CaseMemoryStore
        from src.context_engine.memory.vector_memory import VectorMemoryStore
        cache_dir = Path(getattr(self.config, "cache_dir", "./cache"))
        self.case_store = CaseMemoryStore(cache_dir / "event_cases.jsonl")
        self.vector_memory = None
        if bool(getattr(getattr(global_config, "rag", None), "enable_vector_memory", False)):
            try:
                self.vector_memory = VectorMemoryStore(cache_dir / "vector_memory")
                logger.info("✓ 向量事件记忆已启用")
            except Exception as exc:
                logger.warning(f"向量事件记忆初始化失败，将仅使用JSONL记忆: {exc}")
        self._monitor_status_path = cache_dir / "monitor_status.json"
        self._last_status_write_ts = 0.0
        self._risk_samples_path = cache_dir / "risk_samples.jsonl"
        self._last_risk_sample_ts = 0.0
        self._last_detection_frame_save_ts = 0.0
        self._last_prune_ts = 0.0
        logger.info("✓ 事件记录初始化完成")

    # 已移除模拟组件逻辑，组件导入失败将直接抛出异常
    
    # ========================================================================
    # 生命周期控制
    # ========================================================================
    
    def run(self):
        """启动监控（同步阻塞方式）"""
        if self.state == MonitoringState.RUNNING:
            logger.warning("系统已在运行中")
            return
        
        logger.info("🚀 启动监控系统...")
        self._set_state(MonitoringState.RUNNING)
        self.stats.reset()
        self._stop_event.clear()
        self._pause_event.clear()
        
        if self.config.enable_signal_handling:
            self._setup_signal_handlers()
        
        try:
            self._run_loop()
        except Exception as e:
            logger.error(f"❌ 监控循环异常: {e}", exc_info=True)
            self._handle_error(str(e))
        finally:
            self._cleanup()
    
    def start(self):
        """同义词，兼容新接口"""
        self.run()
    
    def start_in_thread(self) -> threading.Thread:
        """在后台线程启动监控"""
        thread = threading.Thread(target=self.run, daemon=False)
        thread.start()
        return thread
    
    def stop(self):
        """停止监控"""
        if self.state == MonitoringState.STOPPED:
            logger.warning("系统已停止")
            return
        
        logger.info("🛑 停止监控...")
        self._stop_event.set()
        self._pause_event.clear()
        self._set_state(MonitoringState.STOPPED)
    
    def pause(self):
        """暂停监控"""
        if self.state != MonitoringState.RUNNING:
            logger.warning("只有运行中的系统才能暂停")
            return
        
        logger.info("⏸️  暂停监控")
        self._pause_event.set()
        self._set_state(MonitoringState.PAUSED)
    
    def resume(self):
        """继续监控"""
        if self.state != MonitoringState.PAUSED:
            logger.warning("只有暂停的系统才能继续")
            return
        
        logger.info("▶️  继续监控")
        self._pause_event.clear()
        self._set_state(MonitoringState.RUNNING)
    
    # ========================================================================
    # 核心处理循环
    # ========================================================================
    
    def _run_loop(self):
        """主监控循环（YOLO 逐帧检测）"""
        logger.info("进入主循环")
        for frame in self.frame_extractor.stream():
            if self._stop_event.is_set():
                break
            while self._pause_event.is_set():
                if self._stop_event.is_set():
                    break
                threading.Event().wait(0.1)
            if self._stop_event.is_set():
                break

            self.stats.frame_count += 1
            try:
                detections = self.detector.detect(frame)
                should_call_agent, event = self.event_trigger.process_detection(detections, frame)
                self._maybe_write_monitor_status(detections)
                self._maybe_write_risk_sample(detections)
                if self.stats.frame_count % self.config.log_interval == 0:
                    self._log_stats()
                if should_call_agent and event is not None:
                    self._process_event(event)
                if self.config.save_detection_frames and detections:
                    self._maybe_save_detection_frame(frame, detections)
                self._maybe_prune_outputs()
            except Exception as e:
                logger.error(f"处理帧异常: {e}", exc_info=True)
                self.stats.error_count += 1
                self._handle_error(f"处理帧异常: {e}")

        # Best-effort final status write
        try:
            self._write_monitor_status(last_filtered_count=0)
        except Exception:
            pass
        try:
            self._append_risk_sample(
                risk=0.0, fire=0.0, target=0.0, severity="info", state=MonitorState.IDLE.value
            )
        except Exception:
            pass

    def _maybe_write_monitor_status(self, detections: List[Dict[str, Any]]) -> None:
        """Write monitor status periodically for the dashboard (shared via cache file)."""
        now = time.time()
        if now - getattr(self, "_last_status_write_ts", 0.0) < 1.0:
            return
        cfg = getattr(self.event_trigger, "config", None)
        try:
            target_classes = set(getattr(cfg, "target_classes", []) or [])
            min_conf = float(getattr(cfg, "min_confidence", 0.0))
            filtered_count = sum(
                1
                for d in (detections or [])
                if isinstance(d, dict)
                and d.get("class") in target_classes
                and float(d.get("confidence", 0.0) or 0.0) >= min_conf
            )
        except Exception:
            filtered_count = 0
        self._write_monitor_status(last_filtered_count=filtered_count)
        self._last_status_write_ts = now

    def _maybe_write_risk_sample(self, detections: List[Dict[str, Any]]) -> None:
        """Append a risk sample at most once per 3 minutes (for trend chart)."""
        now = time.time()
        if now - getattr(self, "_last_risk_sample_ts", 0.0) < 180.0:
            return
        risk, fire, target, severity, state = self._compute_risk_snapshot(detections)
        self._append_risk_sample(
            risk=risk, fire=fire, target=target, severity=severity, state=state
        )
        self._last_risk_sample_ts = now

    def _compute_risk_snapshot(self, detections: List[Dict[str, Any]]) -> tuple[float, float, float, str, str]:
        """Compute a single snapshot from current frame detections + state machine."""
        cfg = getattr(self.event_trigger, "config", None)
        target_classes = set(getattr(cfg, "target_classes", []) or [])
        min_conf = float(getattr(cfg, "min_confidence", 0.0))
        filtered = [
            d
            for d in (detections or [])
            if isinstance(d, dict)
            and d.get("class") in target_classes
            and float(d.get("confidence", 0.0) or 0.0) >= min_conf
        ]
        fire = max((float(d.get("confidence", 0.0) or 0.0) for d in filtered), default=0.0) * 100.0
        target = float(len(filtered))
        state = getattr(self.event_trigger, "state", MonitorState.IDLE).value
        severity = "critical" if state == MonitorState.ALARM.value else ("warning" if state == MonitorState.SUSPECT.value else "info")
        sev_bonus = 20.0 if severity == "critical" else (10.0 if severity == "warning" else 0.0)
        risk = min(100.0, fire * 0.7 + target * 3.0 + sev_bonus)
        return float(risk), float(fire), float(min(target * 6.0, 100.0)), severity, str(state)

    def _append_risk_sample(self, *, risk: float, fire: float, target: float, severity: str, state: str) -> None:
        path: Path = getattr(self, "_risk_samples_path", Path("./cache/risk_samples.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "risk": round(float(risk), 1),
            "fire": round(float(fire), 1),
            "target": round(float(target), 1),
            "severity": str(severity),
            "state": str(state),
        }
        # Append JSONL, keep size bounded (best-effort)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        try:
            if path.stat().st_size > 2_000_000:  # ~2MB
                lines = path.read_text(encoding="utf-8").splitlines()[-5000:]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass

    def _write_monitor_status(self, *, last_filtered_count: int) -> None:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "state": getattr(self.event_trigger, "state", MonitorState.IDLE).value,
            "detection_streak": int(getattr(self.event_trigger, "detection_count", 0)),
            "no_detection_streak": int(getattr(self.event_trigger, "no_detection_count", 0)),
            "last_filtered_count": int(max(last_filtered_count, 0)),
            "frame_count": int(self.stats.frame_count),
            "fps": float(self.stats.get_fps()),
        }
        path: Path = getattr(self, "_monitor_status_path", Path("./cache/monitor_status.json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    
    def _process_event(self, event: DetectionEvent):
        """处理事件：保存帧、写记录，后台做一次轻量 VL 描述。"""
        self.stats.event_count += 1
        logger.info(f"⚡ 事件 #{self.stats.event_count}: {event.state.value}")

        try:
            save_frame = getattr(self.config, 'save_event_frames', True)
            if save_frame and event.frame is not None:
                saved_path = self._save_event_frame(event)
                event_id = getattr(event, 'event_id', None)
                if saved_path and event_id:
                    t = threading.Thread(
                        target=self._vl_summarize_event,
                        args=(event_id, saved_path),
                        daemon=True,
                    )
                    t.start()

        except Exception as e:
            logger.error(f"处理事件异常: {e}", exc_info=True)
            self.stats.error_count += 1
            self._handle_error(str(e))

    
    def handle_user_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        处理用户查询（用户驱动模式）
        
        Args:
            query: 用户问题
            context: 额外上下文
            
        Returns:
            Agent 的响应
        """
        logger.info(f"💬 处理用户查询: {query}")
        
        # 构建上下文
        if context is None:
            context = {}
        
        # 添加系统统计信息
        context.setdefault("current_state", self.event_trigger.state.value)
        context.setdefault("frame_count", self.stats.frame_count)
        context.setdefault("event_count", self.stats.event_count)
        
        # 调用接口层
        response = self.agent_interface.handle_user_query(query, context)
        
        logger.info(f"Agent 回复: {response.message[:100]}...")
        
        return response
    
    def process_user_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> Any:
        """同义词，兼容新接口"""
        return self.handle_user_query(query, context)
    
    # ========================================================================
    # 查询和统计
    # ========================================================================
    
    def get_state(self) -> MonitoringState:
        """获取系统状态"""
        return self.state
    
    def get_stats(self) -> SystemStats:
        """获取系统统计"""
        return self.stats
    
    def get_monitor_state(self) -> MonitorState:
        """获取监控状态（事件触发器的状态）"""
        return self.event_trigger.state
    
    def get_event_history(self, limit: int = 10) -> List[DetectionEvent]:
        """获取事件历史"""
        return self.event_trigger.event_history[-limit:] if self.event_trigger.event_history else []
    
    def get_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        return {
            "state": self.state.value,
            "monitor_state": self.get_monitor_state().value,
            "stats": self.stats.to_dict(),
            "config": {
                "rtsp_url": self.config.rtsp_url,
                "rtsp_fps": self.config.rtsp_fps,
                "yolo_model": self.config.yolo_model,
                "yolo_device": self.config.yolo_device,
                "target_classes": self.config.target_classes,
            }
        }
    
    # ========================================================================
    # 回调和事件
    # ========================================================================
    
    def set_event_callback(self, callback: Callable[[DetectionEvent, Any], None]):
        """设置事件回调
        
        Args:
            callback: 函数签名 callback(event: DetectionEvent, response: AgentResponse)
        """
        self.on_event = callback
    
    def set_state_changed_callback(self, callback: Callable[[MonitoringState, MonitoringState], None]):
        """设置状态改变回调
        
        Args:
            callback: 函数签名 callback(old_state, new_state)
        """
        self.on_state_changed = callback
    
    def set_error_callback(self, callback: Callable[[str], None]):
        """设置错误回调
        
        Args:
            callback: 函数签名 callback(error_message)
        """
        self.on_error = callback
    
    # ========================================================================
    # 内部方法
    # ========================================================================
    
    def _set_state(self, new_state: MonitoringState):
        """设置状态并触发回调"""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            
            logger.debug(f"状态转换: {old_state.value} → {new_state.value}")
            
            if self.on_state_changed:
                try:
                    self.on_state_changed(old_state, new_state)
                except Exception as e:
                    logger.error(f"状态回调异常: {e}")
    
    def _handle_error(self, error_msg: str):
        """处理错误"""
        if self.on_error:
            try:
                self.on_error(error_msg)
            except Exception as e:
                logger.error(f"错误回调异常: {e}")
    
    def _log_stats(self):
        """打印统计信息"""
        logger.info(
            f"📊 统计: "
            f"帧数={self.stats.frame_count}, "
            f"FPS={self.stats.get_fps():.1f}, "
            f"事件数={self.stats.event_count}, "
            f"报警数={self.stats.alarm_count}, "
            f"状态={self.event_trigger.state.value}"
        )
    
    def _save_event_frame(self, event: DetectionEvent):
        """保存事件帧"""
        import os
        import cv2
        
        try:
            os.makedirs(self.config.output_dir, exist_ok=True)
            from uuid import uuid4
            from src.utils.frame_registry import frame_registry
            # 生成唯一 event_id
            event_id = getattr(event, 'event_id', None)
            if not event_id:
                event_id = f"{event.timestamp.strftime('%Y%m%d_%H%M%S')}_{event.state.value}_{str(uuid4())[:6]}"
                setattr(event, 'event_id', event_id)
            filename = f"{event_id}.jpg"
            filepath = os.path.join(self.config.output_dir, filename)
            # Use higher JPEG quality to avoid visible artifacts in saved frames
            cv2.imwrite(filepath, event.frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            # 注册到 FrameRegistry
            frame_registry.register(event_id, filepath)
            logger.info(f"💾 事件帧已保存: {filepath} (event_id={event_id})")

            # 写入事件记录，供前端仪表盘展示
            from src.context_engine.memory.case_memory import CaseRecord, extract_labels
            detections = getattr(event, 'detections', []) or []
            confidence = max((d.get("confidence", 0) for d in detections), default=0.0)
            severity = "critical" if event.state.value == "alarm" else "warning"
            # Store path relative to OUTPUTS_DIR (default: ./outputs)
            try:
                outputs_root = Path("./outputs").resolve()
                rel_image_path = str(Path(filepath).resolve().relative_to(outputs_root)).replace("\\", "/")
            except Exception:
                rel_image_path = ""
            yolo_labels = extract_labels(detections)
            yolo_evidence = {
                "confidence": confidence,
                "detection_count": len(detections),
                "labels": yolo_labels,
            }
            if bool(getattr(self.config, "persist_yolo_detections", False)):
                yolo_evidence["detections"] = detections
            if bool(getattr(self.config, "persist_yolo_raw", False)):
                try:
                    outputs_root = Path("./outputs").resolve()
                    yolo_raw_dir = outputs_root / "yolo" / "raw"
                    yolo_raw_dir.mkdir(parents=True, exist_ok=True)
                    raw_path = yolo_raw_dir / f"{event_id}.json"
                    raw_path.write_text(json.dumps(detections, ensure_ascii=False), encoding="utf-8")
                    yolo_evidence["raw_path"] = str(raw_path.relative_to(outputs_root)).replace("\\", "/")
                except Exception as exc:
                    logger.warning(f"YOLO 原始结果落盘失败 ({event_id}): {exc}")

            record = CaseRecord(
                event_id=event_id,
                timestamp=event.timestamp.isoformat(),
                state=event.state.value,
                severity=severity,
                confidence=confidence,
                detection_count=len(detections),
                labels=yolo_labels,
                summary="",
                image_path=rel_image_path,
                yolo=yolo_evidence,
                vl={},
                final={
                    # Use YOLO-triggered verdict initially; VL may override later.
                    "verdict": "fire",
                    "reviewed": False,
                    "severity": severity,
                    "confidence": confidence,
                    "reason": "triggered_by_yolo",
                    "decided_by": "yolo",
                },
            )
            self.case_store.add(record)
            if self.vector_memory is not None:
                try:
                    self.vector_memory.add(record, memory_type="event")
                except Exception as exc:
                    logger.warning(f"向量事件记忆写入失败（已忽略）({event_id}): {exc}")
            return filepath
        except Exception as e:
            logger.error(f"保存事件帧失败: {e}")
            return None

    def _vl_summarize_event(self, event_id: str, image_path: str):
        """后台线程：对事件帧调用 detect_image，把 description 写入 summary。"""
        try:
            from src.tools.detections import detect_image, extract_description, safe_parse_json, draw_bboxes
            raw = detect_image.invoke({"input_image": image_path})
            # Persist raw VL output for debugging/audit
            try:
                outputs_root = Path("./outputs").resolve()
                raw_dir = outputs_root / "vl" / "raw"
                raw_dir.mkdir(parents=True, exist_ok=True)
                raw_path = raw_dir / f"{event_id}.json"
                raw_path.write_text(str(raw), encoding="utf-8")
                rel_raw = str(raw_path.relative_to(outputs_root)).replace("\\", "/")
                self.case_store.update_media(event_id, vl_raw_path=rel_raw)
            except Exception as exc:
                logger.warning(f"VL 原始结果落盘失败 ({event_id}): {exc}")
            summary = extract_description(raw)
            if summary:
                self.case_store.update_summary(event_id, summary)
                logger.info(f"📝 VL 描述已写入 {event_id}: {summary[:60]}...")
            try:
                dets = safe_parse_json(raw)
                if dets:
                    annotated_path = draw_bboxes(image_path, dets)
                    if annotated_path and annotated_path != image_path:
                        try:
                            outputs_root = Path("./outputs").resolve()
                            rel_vl_path = str(Path(annotated_path).resolve().relative_to(outputs_root)).replace("\\", "/")
                        except Exception:
                            rel_vl_path = ""
                        if rel_vl_path:
                            self.case_store.update_media(event_id, vl_image_path=rel_vl_path)
                    try:
                        vl_labels = sorted(
                            {
                                str(d.get("label") or d.get("class") or "").strip()
                                for d in dets
                                if isinstance(d, dict) and (d.get("label") or d.get("class"))
                            }
                        )
                        if vl_labels:
                            self.case_store.update_fields(event_id, detection_count=len(dets), labels=vl_labels)
                    except Exception:
                        pass
                # Update VL evidence + final verdict (simple heuristic)
                try:
                    self.case_store.update_media(event_id, vl_raw_path=str(rel_raw) if "rel_raw" in locals() else None)
                except Exception:
                    pass

                verdict, reviewed, reason = self._decide_final_verdict(summary or "", dets or [])
                if verdict != "unknown":
                    final_sev = "info" if verdict == "non_fire" else "critical"
                else:
                    final_sev = None
                self.case_store.update_final(
                    event_id,
                    verdict=verdict,
                    reviewed=reviewed,
                    severity=final_sev,
                    reason=reason,
                    decided_by="vl",
                )
                # Upsert the updated record into vector memory for better retrieval.
                if self.vector_memory is not None:
                    try:
                        rec = self.case_store.get(event_id)
                        if rec is not None:
                            self.vector_memory.add(rec, memory_type="event")
                    except Exception as exc:
                        logger.warning(f"向量事件记忆更新失败（已忽略）({event_id}): {exc}")
            except Exception as exc:
                logger.warning(f"VL 标注图生成失败 ({event_id}): {exc}")
        except Exception as e:
            logger.warning(f"VL 描述失败 ({event_id}): {e}")

    @staticmethod
    def _decide_final_verdict(summary: str, vl_dets: List[Dict[str, Any]]) -> tuple[str, bool, str]:
        """Heuristic: decide fire/non_fire/unknown from VL summary + labels.

        Conservative: only flip to non_fire when stage-lighting cues are strong and fire cues absent.
        """
        text = (summary or "").lower()
        labels = []
        for d in (vl_dets or []):
            if isinstance(d, dict):
                lab = d.get("label") or d.get("class")
                if lab:
                    labels.append(str(lab).lower())
        label_text = " ".join(labels)

        fire_pos = ("火", "明火", "火焰", "起火", "着火", "燃烧", "火灾", "浓烟", "烟雾")
        stage_neg = ("演唱会", "舞台", "灯光", "特效", "观众", "表演", "烟雾机", "屏幕", "氛围", "过曝")

        has_fire = any(k in text for k in fire_pos) or any(k in label_text for k in ("fire", "smoke", "flame"))
        has_stage = any(k in text for k in stage_neg)

        if has_fire and not has_stage:
            return "fire", True, "vl_fire_cues"
        if has_stage and not has_fire:
            return "non_fire", True, "vl_stage_lighting_cues"
        return "unknown", False, "insufficient_vl_signal"
    
    def _save_detection_frame(self, frame, detections):
        """保存检测帧"""
        import os
        import json
        import cv2
        
        try:
            output_dir = os.path.join(self.config.output_dir, "detections")
            os.makedirs(output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_name = f"{timestamp}_frame{self.stats.frame_count}"
            
            # 保存图像
            img_path = os.path.join(output_dir, f"{base_name}.jpg")
            annotated = frame.copy()
            
            for det in detections:
                try:
                    bbox = det.get("bbox", [0, 0, 0, 0])
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    label = f"{det.get('class', '?')}: {det.get('confidence', 0):.2f}"
                    
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(annotated, label, (x1, max(y1 - 10, 0)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                except Exception as e:
                    logger.warning(f"绘制检测框失败: {e}")
            
            cv2.imwrite(img_path, annotated)
            
            # 保存元数据
            json_path = os.path.join(output_dir, f"{base_name}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({
                    "frame_count": self.stats.frame_count,
                    "timestamp": timestamp,
                    "detections": detections
                }, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logger.error(f"保存检测帧失败: {e}")

    def _maybe_save_detection_frame(self, frame, detections) -> None:
        """Rate-limit detection snapshot saving to avoid output explosion."""
        interval = int(getattr(self.config, "detection_save_interval", 0) or 0)
        if interval <= 0:
            return
        now = time.time()
        if now - getattr(self, "_last_detection_frame_save_ts", 0.0) < float(interval):
            return
        self._save_detection_frame(frame, detections)
        self._last_detection_frame_save_ts = now

    def _maybe_prune_outputs(self) -> None:
        """Prune old images periodically based on retention settings."""
        interval = int(getattr(self.config, "prune_interval_seconds", 60) or 60)
        if interval <= 0:
            return
        now = time.time()
        if now - getattr(self, "_last_prune_ts", 0.0) < float(interval):
            return

        try:
            alarm_dir = Path(self.config.output_dir).resolve()
            outputs_root = Path("./outputs").resolve()
            # Legacy: older builds stored annotated images under outputs/agent
            agent_dir = outputs_root / "agent"
            vl_annot_dir = outputs_root / "vl" / "annotated"
            vl_raw_dir = outputs_root / "vl" / "raw"
            yolo_raw_dir = outputs_root / "yolo" / "raw"
            det_dir = alarm_dir / "detections"

            self._prune_dir(alarm_dir, keep=int(getattr(self.config, "max_event_images", 0) or 0))
            self._prune_dir(det_dir, keep=int(getattr(self.config, "max_detection_images", 0) or 0))
            self._prune_dir(agent_dir, keep=int(getattr(self.config, "max_agent_images", 0) or 0))
            self._prune_dir(vl_annot_dir, keep=int(getattr(self.config, "max_agent_images", 0) or 0))
            self._prune_dir(vl_raw_dir, keep=int(getattr(self.config, "max_vl_raw_files", 0) or 0))
            self._prune_dir(yolo_raw_dir, keep=int(getattr(self.config, "max_yolo_raw_files", 0) or 0))
        except Exception as exc:
            logger.warning(f"输出清理失败（已忽略）: {exc}")
        finally:
            self._last_prune_ts = now

    @staticmethod
    def _prune_dir(dir_path: Path, *, keep: int) -> None:
        """Keep only newest N image files under dir_path (best-effort)."""
        if keep <= 0:
            return
        if not dir_path.exists() or not dir_path.is_dir():
            return
        files = []
        for pat in ("*.jpg", "*.jpeg", "*.png", "*.json", "*.txt"):
            files.extend([p for p in dir_path.glob(pat) if p.is_file()])
        if len(files) <= keep:
            return
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[keep:]:
            try:
                p.unlink()
            except Exception:
                continue
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            logger.debug("✓ 信号处理已注册")
    
    def _signal_handler(self, sig, frame):
        """处理 Ctrl+C 等信号"""
        logger.info("收到停止信号，正在关闭...")
        self.stop()
    
    def _cleanup(self):
        """清理资源"""
        logger.info("清理资源...")

        try:
            self.frame_extractor.disconnect()
        except Exception as e:
            logger.warning(f"断开 RTSP 连接失败: {e}")

        logger.info(
            f"✅ 监控已停止。\n"
            f"  总处理帧数: {self.stats.frame_count}\n"
            f"  平均 FPS: {self.stats.get_fps():.1f}\n"
            f"  触发事件: {self.stats.event_count}\n"
            f"  报警数: {self.stats.alarm_count}\n"
            f"  警告数: {self.stats.warning_count}\n"
            f"  错误数: {self.stats.error_count}\n"
            f"  运行时间: {self.stats.get_uptime_seconds():.1f}s"
        )
