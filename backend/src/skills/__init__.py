"""
src/skills — Agent 可调用的高级技能包

导出所有 Skill，供 hybrid_monitoring_agent 注册到工具列表。
每个 Skill 封装完整工作流，Agent 无需逐步调用底层工具。
"""

from src.skills.analysis import analyze_monitoring_event, quick_detect
from src.skills.batch import batch_analyze
from src.skills.compare import compare_events
from src.skills.capture import capture_current_frame

__all__ = [
    "analyze_monitoring_event",
    "quick_detect",
    "batch_analyze",
    "compare_events",
    "capture_current_frame",
]
