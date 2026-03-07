"""
批量分析技能：
  - batch_analyze  扫描目录内多张图片并汇总检测结果
"""

import json
import logging
from pathlib import Path

from langchain.tools import tool

from src.tools.detections import detect_image, safe_parse_json, draw_bboxes
from src.tools.image_finder import list_images
from src.skills._helpers import class_dist, parse_image_list

logger = logging.getLogger(__name__)


@tool
def batch_analyze(
    directory: str = "inputs",
    pattern: str = None,
    severity: str = "info",
    max_images: int = 5,
) -> str:
    """
    【批量分析】扫描指定目录中的多张图片，逐一检测并返回汇总统计。
    返回结构化 JSON，包含 summary（文字摘要）与每张图片的检测元数据。

    Args:
        directory: 目录名称（'inputs' / 'outputs' 或完整路径）
        pattern: 文件名过滤，如 '*.jpg' 或 'camera*'
        severity: 风险等级（用于判断）
        max_images: 最多分析的图片数量
    """
    try:
        images_text = list_images.invoke({"directory": directory, "pattern": pattern})
        image_paths = parse_image_list(images_text)

        if not image_paths:
            return json.dumps({
                "status": "error",
                "summary": f"目录 {directory} 中未找到图片",
            }, ensure_ascii=False)

        image_paths = image_paths[:max_images]
        total_count = 0
        all_classes: dict = {}
        per_image = []

        for path in image_paths:
            item: dict = {"image": Path(path).name, "image_path": path}
            try:
                raw = detect_image.invoke({"input_image": path})
                detections = safe_parse_json(raw)
                count = len(detections) if isinstance(detections, list) else 0
                dist = class_dist(detections)
                total_count += count
                for k, v in dist.items():
                    all_classes[k] = all_classes.get(k, 0) + v

                annotated_path = draw_bboxes(path, detections) if count > 0 else None
                item.update({
                    "status": "success",
                    "detection_count": count,
                    "class_distribution": dist,
                    "annotated_path": annotated_path,
                })
            except Exception as e:
                item.update({"status": "error", "error": str(e), "detection_count": 0})

            per_image.append(item)

        dist_text = "、".join(
            f"{k}×{v}" for k, v in sorted(all_classes.items(), key=lambda x: -x[1])
        ) if all_classes else "无目标"

        result = {
            "status": "success",
            "summary": (
                f"批量分析完成，共 {len(image_paths)} 张图片，"
                f"合计 {total_count} 个目标（{dist_text}）"
            ),
            "directory": directory,
            "total_images": len(image_paths),
            "total_detections": total_count,
            "class_distribution": all_classes,
            "per_image": per_image,
        }
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"batch_analyze 失败: {e}", exc_info=True)
        return json.dumps({"status": "error", "summary": f"批量分析失败: {e}"}, ensure_ascii=False)
