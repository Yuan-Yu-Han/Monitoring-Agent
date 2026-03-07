"""
事件对比技能：
  - compare_events  对比两个事件的检测结果差异
"""

import json
import logging
from pathlib import Path

from langchain.tools import tool

from src.tools.detections import detect_image, safe_parse_json
from src.tools.image_finder import _resolve_image_path
from src.skills._helpers import class_dist

logger = logging.getLogger(__name__)


@tool
def compare_events(
    event_id_1: str = None,
    event_id_2: str = None,
    query_1: str = None,
    query_2: str = None,
) -> str:
    """
    【对比分析】对比两个事件的检测结果，输出目标数量和类型变化。
    返回结构化 JSON，包含 summary（文字摘要）与逐类型的变化元数据。

    Args:
        event_id_1 / query_1: 第一个事件的 ID 或图片名
        event_id_2 / query_2: 第二个事件的 ID 或图片名
    """
    try:
        path_1 = _resolve_image_path(event_id=event_id_1, query=query_1)
        path_2 = _resolve_image_path(event_id=event_id_2, query=query_2)

        if not path_1:
            return json.dumps({
                "status": "error",
                "summary": f"未找到第一张图片（event_id={event_id_1}, query={query_1}）",
            }, ensure_ascii=False)
        if not path_2:
            return json.dumps({
                "status": "error",
                "summary": f"未找到第二张图片（event_id={event_id_2}, query={query_2}）",
            }, ensure_ascii=False)

        det_1 = safe_parse_json(detect_image.invoke({"input_image": path_1}))
        det_2 = safe_parse_json(detect_image.invoke({"input_image": path_2}))

        c1 = len(det_1) if isinstance(det_1, list) else 0
        c2 = len(det_2) if isinstance(det_2, list) else 0
        cls_1 = class_dist(det_1)
        cls_2 = class_dist(det_2)
        all_cls = set(cls_1) | set(cls_2)

        class_changes = {
            cls: {"before": cls_1.get(cls, 0), "after": cls_2.get(cls, 0)}
            for cls in sorted(all_cls)
        }
        new_classes = sorted(set(cls_2) - set(cls_1))
        removed_classes = sorted(set(cls_1) - set(cls_2))

        delta = c2 - c1
        delta_str = f"+{delta}" if delta >= 0 else str(delta)

        change_desc = []
        if new_classes:
            change_desc.append(f"新增: {', '.join(new_classes)}")
        if removed_classes:
            change_desc.append(f"消失: {', '.join(removed_classes)}")
        changed = [
            cls for cls, v in class_changes.items()
            if v["before"] != v["after"] and cls not in new_classes and cls not in removed_classes
        ]
        if changed:
            change_desc.append(f"变化: {', '.join(changed)}")

        result = {
            "status": "success",
            "summary": (
                f"{Path(path_1).name} vs {Path(path_2).name}："
                f"目标数 {c1} → {c2}（{delta_str}）"
                + (f"；{'; '.join(change_desc)}" if change_desc else "，类型无变化")
            ),
            "image_1": path_1,
            "image_2": path_2,
            "count_before": c1,
            "count_after": c2,
            "delta": delta,
            "new_classes": new_classes,
            "removed_classes": removed_classes,
            "class_changes": class_changes,
        }
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"compare_events 失败: {e}", exc_info=True)
        return json.dumps({"status": "error", "summary": f"对比分析失败: {e}"}, ensure_ascii=False)
