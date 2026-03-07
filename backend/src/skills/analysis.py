"""
单事件分析类技能：
  - analyze_monitoring_event  完整分析流程（查图 → 检测 → 标注 → 报告）
  - quick_detect              仅检测 + 可选标注，不生成报告
"""

import json
import logging
from pathlib import Path

from langchain.tools import tool

from src.tools.detections import detect_image, extract_description, safe_parse_json, draw_bboxes
from src.tools.image_finder import _resolve_image_path
from src.tools.report_generator import generate_report
from src.skills._helpers import build_analysis, class_dist

logger = logging.getLogger(__name__)


@tool
def analyze_monitoring_event(
    event_id: str = None,
    query: str = None,
    severity: str = "info",
    save_report: bool = True,
    region: str = "default",
) -> str:
    """
    【核心技能】一键分析监控事件：find_image → detect → draw_bboxes → generate_report。

    优先使用 event_id 精确定位；若无 event_id，用 query 模糊匹配图片名或路径。
    返回结构化 JSON，包含 summary（文字摘要）与各项元数据。

    Args:
        event_id: 事件唯一ID（推荐）
        query: 图片名称或路径（备选，模糊匹配）
        severity: 风险等级 info / warning / critical
        save_report: 是否保存报告文件
        region: 监控区域名称
    """
    try:
        image_path = _resolve_image_path(event_id=event_id, query=query)
        if not image_path:
            return json.dumps({
                "status": "error",
                "summary": f"未找到图片（event_id={event_id}, query={query}）",
            }, ensure_ascii=False)

        # 一次 VL 调用同时得到检测结果和场景描述
        raw = detect_image.invoke({"input_image": image_path})
        detections = safe_parse_json(raw)
        scene_description = extract_description(raw)

        count = len(detections) if isinstance(detections, list) else 0
        dist = class_dist(detections)

        annotated_path = draw_bboxes(image_path, detections) if count > 0 else None

        report_summary = generate_report.invoke({
            "detections": json.dumps({"detections": detections}),
            "analysis": scene_description or build_analysis(detections, severity),
            "severity": severity,
            "format": "markdown",
            "save_file": save_report,
            "region": region,
        })

        # 从 report_summary 中提取保存路径（如果有）
        report_path = None
        for line in report_summary.splitlines():
            if "报告已保存" in line or "report_" in line:
                parts = line.split("：", 1) if "：" in line else line.split(":", 1)
                if len(parts) == 2:
                    report_path = parts[1].strip()
                    break

        dist_text = "、".join(f"{k}×{v}" for k, v in dist.items()) if dist else "无目标"
        result = {
            "status": "success",
            "summary": scene_description or f"检测到 {count} 个目标（{dist_text}），风险等级: {severity}",
            "event_id": event_id,
            "image_path": image_path,
            "annotated_path": annotated_path,
            "detection_count": count,
            "class_distribution": dist,
            "detections": detections,
            "severity": severity,
            "report_path": report_path,
            "region": region,
        }
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"analyze_monitoring_event 失败: {e}", exc_info=True)
        return json.dumps({"status": "error", "summary": f"分析失败: {e}"}, ensure_ascii=False)


@tool
def quick_detect(
    event_id: str = None,
    query: str = None,
    draw_boxes: bool = True,
) -> str:
    """
    【快速检测】检测图片中的目标并可选绘制标注框，不生成完整报告。
    返回结构化 JSON，包含 summary（文字摘要）与检测元数据。

    Args:
        event_id: 事件ID（推荐）
        query: 图片名称或路径（备选）
        draw_boxes: 是否绘制标注框
    """
    try:
        image_path = _resolve_image_path(event_id=event_id, query=query)
        if not image_path:
            return json.dumps({
                "status": "error",
                "summary": f"未找到图片（event_id={event_id}, query={query}）",
            }, ensure_ascii=False)

        raw = detect_image.invoke({"input_image": image_path})
        detections = safe_parse_json(raw)
        scene_description = extract_description(raw)

        count = len(detections) if isinstance(detections, list) else 0
        dist = class_dist(detections)

        annotated_path = None
        if count > 0 and draw_boxes:
            annotated_path = draw_bboxes(image_path, detections)

        dist_text = "、".join(f"{k}×{v}" for k, v in dist.items()) if dist else "无目标"
        result = {
            "status": "success",
            "summary": scene_description or f"图片 {Path(image_path).name} 检测到 {count} 个目标（{dist_text}）",
            "event_id": event_id,
            "image_path": image_path,
            "annotated_path": annotated_path,
            "detection_count": count,
            "class_distribution": dist,
            "detections": detections,
            "scene_description": scene_description,
        }
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"quick_detect 失败: {e}", exc_info=True)
        return json.dumps({"status": "error", "summary": f"检测失败: {e}"}, ensure_ascii=False)
