"""Skills 内部共享辅助函数，不对外暴露为 Agent 工具。"""

from pathlib import Path
from typing import Dict, List


def class_dist(detections) -> Dict[str, int]:
    """统计检测结果中各类型的数量。"""
    d: Dict[str, int] = {}
    if isinstance(detections, list):
        for det in detections:
            if isinstance(det, dict):
                cls = det.get("label", "unknown")
                d[cls] = d.get(cls, 0) + 1
    return d


def build_analysis(detections, severity: str) -> str:
    """根据检测结果构建简短分析文本，供 generate_report 使用。"""
    if not detections or not isinstance(detections, list):
        return "未检测到异常目标，场景正常。"
    count = len(detections)
    dist = class_dist(detections)
    top = sorted(dist.items(), key=lambda x: -x[1])[:3]
    desc = "、".join(f"{k}({v}个)" for k, v in top)
    risk_msg = {
        "critical": "存在高风险情况，建议立即处置。",
        "warning": "检测到可疑情况，建议加强监控。",
    }.get(severity, "场景整体正常，保持常规巡检。")
    return f"共检测到 {count} 个目标，主要包括: {desc}。{risk_msg}"


def parse_image_list(list_result: str) -> List[str]:
    """从 list_images 工具的输出中提取图片绝对路径列表。"""
    paths = []
    for line in list_result.split("\n"):
        if "Full path:" in line:
            path = line.split(":", 1)[-1].strip()
            if Path(path).exists():
                paths.append(path)
    return paths
