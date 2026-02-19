"""
Skills - 封装高频工作流，减少 Agent 调用步骤
将多个 Tool 组合成一个 Skill，提高效率并减少错误
"""

import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from langchain.tools import tool

# Import existing tools
from src.tools.detections import detect_image, safe_parse_json, draw_bboxes
from src.tools.image_finder import find_image, list_images, validate_image
from src.tools.report_generator import generate_report

logger = logging.getLogger(__name__)


@tool
def analyze_monitoring_event(
    event_id: str = None,
    query: str = None,
    severity: str = "info",
    save_report: bool = True,
    region: str = "default"
) -> str:
    """
    【核心技能】一键分析监控事件：自动执行 find_image → detect → draw_bboxes → generate_report 全流程。

    这是最常用的技能，将标准工作流封装为一个步骤，大幅提升效率。

    Args:
        event_id: 事件ID（推荐，精确匹配）
        query: 图片名称或描述（备选，模糊匹配）
        severity: 风险等级 (info/warning/critical)，默认 info
        save_report: 是否保存报告文件，默认 True
        region: 监控区域名称，默认 "default"

    Returns:
        str: 完整的分析结果（包含检测摘要、AI分析、报告路径）

    示例:
        analyze_monitoring_event(event_id="20240315_143022_alarm_a3b2c1")
        analyze_monitoring_event(query="camera_01.jpg", severity="warning")
    """
    try:
        result_parts = []
        result_parts.append("🚀 **启动一键分析流程**\n")

        # Step 1: 查找图片
        result_parts.append("📍 **步骤 1/4: 查找图片**")
        if event_id:
            find_result = find_image.invoke({"event_id": event_id})
        elif query:
            find_result = find_image.invoke({"query": query})
        else:
            return "❌ 错误: 必须提供 event_id 或 query 参数"

        # 解析图片路径
        image_path = _extract_image_path(find_result)
        if not image_path:
            result_parts.append("❌ 未找到图片")
            result_parts.append(find_result)
            return "\n".join(result_parts)

        result_parts.append(f"✅ 找到图片: {image_path}\n")

        # Step 2: 检测目标
        result_parts.append("🔍 **步骤 2/4: 检测目标**")
        detection_result = detect_image.invoke({"input_image": image_path})
        parsed_detections = safe_parse_json.invoke({"raw_result": detection_result})

        detection_count = len(parsed_detections) if isinstance(parsed_detections, list) else 0
        result_parts.append(f"✅ 检测到 {detection_count} 个目标\n")

        # Step 3: 绘制标注框
        result_parts.append("🎨 **步骤 3/4: 绘制标注框**")
        annotated_path = draw_bboxes.invoke({"input_image": image_path, "detections": parsed_detections})
        result_parts.append(f"✅ 标注图保存至: {annotated_path}\n")

        # Step 4: 生成报告
        result_parts.append("📄 **步骤 4/4: 生成分析报告**")

        # 构建分析文本
        analysis = _build_analysis(parsed_detections, severity)

        report_summary = generate_report.invoke({
            "detections": json.dumps({"detections": parsed_detections}),
            "analysis": analysis,
            "severity": severity,
            "format": "markdown",
            "save_file": save_report,
            "region": region
        })

        result_parts.append(report_summary)
        result_parts.append("\n" + "="*60)
        result_parts.append("✅ **分析完成！**")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"analyze_monitoring_event 失败: {e}", exc_info=True)
        return f"❌ 分析失败: {str(e)}"


@tool
def quick_detect(
    event_id: str = None,
    query: str = None,
    draw_boxes: bool = True
) -> str:
    """
    【快速检测】仅执行图片检测和标注，不生成完整报告。适合快速查看。

    Args:
        event_id: 事件ID（推荐）
        query: 图片名称或描述（备选）
        draw_boxes: 是否绘制标注框，默认 True

    Returns:
        str: 检测结果摘要

    示例:
        quick_detect(event_id="20240315_143022_alarm_a3b2c1")
        quick_detect(query="latest.jpg", draw_boxes=False)
    """
    try:
        result_parts = []
        result_parts.append("⚡ **快速检测模式**\n")

        # Step 1: 查找图片
        if event_id:
            find_result = find_image.invoke({"event_id": event_id})
        elif query:
            find_result = find_image.invoke({"query": query})
        else:
            return "❌ 错误: 必须提供 event_id 或 query 参数"

        image_path = _extract_image_path(find_result)
        if not image_path:
            return f"❌ 未找到图片\n{find_result}"

        result_parts.append(f"📍 图片: {image_path}\n")

        # Step 2: 检测
        detection_result = detect_image.invoke({"input_image": image_path})
        parsed_detections = safe_parse_json.invoke({"raw_result": detection_result})

        # 统计检测结果
        detection_count = len(parsed_detections) if isinstance(parsed_detections, list) else 0
        result_parts.append(f"🔍 **检测结果: {detection_count} 个目标**\n")

        if detection_count > 0:
            # 按类型分组统计
            class_counts = {}
            for det in parsed_detections:
                if isinstance(det, dict):
                    cls = det.get("label", "unknown")
                    class_counts[cls] = class_counts.get(cls, 0) + 1

            result_parts.append("📊 **目标分布:**")
            for cls, count in sorted(class_counts.items(), key=lambda x: x[1], reverse=True):
                result_parts.append(f"  - {cls}: {count} 个")

            # 绘制标注框（可选）
            if draw_boxes:
                result_parts.append("")
                annotated_path = draw_bboxes.invoke({"input_image": image_path, "detections": parsed_detections})
                result_parts.append(f"🎨 标注图: {annotated_path}")
        else:
            result_parts.append("✅ 未检测到目标对象")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"quick_detect 失败: {e}", exc_info=True)
        return f"❌ 检测失败: {str(e)}"


@tool
def batch_analyze(
    directory: str = "inputs",
    pattern: str = None,
    severity: str = "info",
    max_images: int = 5
) -> str:
    """
    【批量分析】分析指定目录中的多张图片，生成汇总报告。

    Args:
        directory: 目录名称 ('inputs', 'outputs') 或完整路径
        pattern: 文件名过滤模式，如 'camera*', '*.jpg'
        severity: 风险等级，默认 info
        max_images: 最多分析的图片数量，默认 5

    Returns:
        str: 批量分析汇总结果

    示例:
        batch_analyze(directory="inputs", pattern="*.jpg", max_images=3)
    """
    try:
        result_parts = []
        result_parts.append("📦 **批量分析模式**\n")

        # Step 1: 列出所有图片
        result_parts.append(f"📂 扫描目录: {directory}")
        images_list = list_images.invoke({"directory": directory, "pattern": pattern})

        # 解析图片路径列表
        image_paths = _parse_image_list(images_list)

        if not image_paths:
            return f"❌ 目录中没有找到图片\n{images_list}"

        # 限制数量
        image_paths = image_paths[:max_images]
        result_parts.append(f"✅ 找到 {len(image_paths)} 张图片\n")

        # Step 2: 逐个分析
        all_detections = []
        for idx, img_path in enumerate(image_paths, 1):
            result_parts.append(f"--- **图片 {idx}/{len(image_paths)}** ---")
            result_parts.append(f"📍 {Path(img_path).name}")

            try:
                # 检测
                detection_result = detect_image.invoke({"input_image": img_path})
                parsed = safe_parse_json.invoke({"raw_result": detection_result})
                count = len(parsed) if isinstance(parsed, list) else 0

                result_parts.append(f"🔍 检测到 {count} 个目标")

                all_detections.append({
                    "image": Path(img_path).name,
                    "path": img_path,
                    "detections": parsed,
                    "count": count
                })

                # 绘制标注框
                if count > 0:
                    annotated = draw_bboxes.invoke({"input_image": img_path, "detections": parsed})
                    result_parts.append(f"🎨 {Path(annotated).name}")

            except Exception as e:
                result_parts.append(f"❌ 分析失败: {str(e)}")

            result_parts.append("")

        # Step 3: 生成汇总
        result_parts.append("="*60)
        result_parts.append("📊 **汇总统计**\n")

        total_detections = sum(d["count"] for d in all_detections)
        result_parts.append(f"- 总图片数: {len(image_paths)}")
        result_parts.append(f"- 总检测数: {total_detections}")
        result_parts.append(f"- 平均每张: {total_detections / len(image_paths):.1f} 个")

        # 汇总所有类型
        all_classes = {}
        for d in all_detections:
            for det in d.get("detections", []):
                if isinstance(det, dict):
                    cls = det.get("label", "unknown")
                    all_classes[cls] = all_classes.get(cls, 0) + 1

        if all_classes:
            result_parts.append("\n**目标类型分布:**")
            for cls, count in sorted(all_classes.items(), key=lambda x: x[1], reverse=True):
                result_parts.append(f"  - {cls}: {count} 个")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"batch_analyze 失败: {e}", exc_info=True)
        return f"❌ 批量分析失败: {str(e)}"


@tool
def compare_events(
    event_id_1: str = None,
    event_id_2: str = None,
    query_1: str = None,
    query_2: str = None
) -> str:
    """
    【对比分析】对比两个事件的检测结果，找出差异。

    Args:
        event_id_1: 第一个事件ID
        event_id_2: 第二个事件ID
        query_1: 第一张图片名称（备选）
        query_2: 第二张图片名称（备选）

    Returns:
        str: 对比分析结果

    示例:
        compare_events(event_id_1="event_001", event_id_2="event_002")
        compare_events(query_1="before.jpg", query_2="after.jpg")
    """
    try:
        result_parts = []
        result_parts.append("⚖️  **对比分析模式**\n")

        # 分析第一张图片
        result_parts.append("📍 **图片 1:**")
        if event_id_1:
            find_1 = find_image.invoke({"event_id": event_id_1})
        elif query_1:
            find_1 = find_image.invoke({"query": query_1})
        else:
            return "❌ 错误: 必须提供 event_id_1 或 query_1"

        path_1 = _extract_image_path(find_1)
        if not path_1:
            return f"❌ 未找到第一张图片\n{find_1}"

        result_parts.append(f"  {Path(path_1).name}")
        detection_1 = detect_image.invoke({"input_image": path_1})
        parsed_1 = safe_parse_json.invoke({"raw_result": detection_1})
        count_1 = len(parsed_1) if isinstance(parsed_1, list) else 0
        result_parts.append(f"  检测到 {count_1} 个目标\n")

        # 分析第二张图片
        result_parts.append("📍 **图片 2:**")
        if event_id_2:
            find_2 = find_image.invoke({"event_id": event_id_2})
        elif query_2:
            find_2 = find_image.invoke({"query": query_2})
        else:
            return "❌ 错误: 必须提供 event_id_2 或 query_2"

        path_2 = _extract_image_path(find_2)
        if not path_2:
            return f"❌ 未找到第二张图片\n{find_2}"

        result_parts.append(f"  {Path(path_2).name}")
        detection_2 = detect_image.invoke({"input_image": path_2})
        parsed_2 = safe_parse_json.invoke({"raw_result": detection_2})
        count_2 = len(parsed_2) if isinstance(parsed_2, list) else 0
        result_parts.append(f"  检测到 {count_2} 个目标\n")

        # 统计差异
        result_parts.append("="*60)
        result_parts.append("📊 **对比结果**\n")

        # 数量差异
        diff = count_2 - count_1
        if diff > 0:
            result_parts.append(f"📈 目标数量增加: +{diff} 个")
        elif diff < 0:
            result_parts.append(f"📉 目标数量减少: {diff} 个")
        else:
            result_parts.append(f"➡️  目标数量不变: {count_1} 个")

        # 类型差异
        classes_1 = _get_class_distribution(parsed_1)
        classes_2 = _get_class_distribution(parsed_2)

        result_parts.append("\n**类型对比:**")
        all_classes = set(classes_1.keys()) | set(classes_2.keys())

        for cls in sorted(all_classes):
            c1 = classes_1.get(cls, 0)
            c2 = classes_2.get(cls, 0)
            if c1 == c2:
                result_parts.append(f"  - {cls}: {c1} → {c2} (不变)")
            elif c2 > c1:
                result_parts.append(f"  - {cls}: {c1} → {c2} (增加 {c2-c1})")
            else:
                result_parts.append(f"  - {cls}: {c1} → {c2} (减少 {c1-c2})")

        # 新增和消失的类型
        new_classes = set(classes_2.keys()) - set(classes_1.keys())
        removed_classes = set(classes_1.keys()) - set(classes_2.keys())

        if new_classes:
            result_parts.append(f"\n🆕 **新增类型:** {', '.join(new_classes)}")
        if removed_classes:
            result_parts.append(f"\n🗑️  **消失类型:** {', '.join(removed_classes)}")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"compare_events 失败: {e}", exc_info=True)
        return f"❌ 对比分析失败: {str(e)}"


# ============================================================================
# 辅助函数（内部使用）
# ============================================================================

def _extract_image_path(find_result: str) -> Optional[str]:
    """从 find_image 的结果中提取图片路径"""
    lines = find_result.split("\n")
    for line in lines:
        if "路径:" in line or "📍" in line:
            # 提取路径
            path = line.split(":", 1)[-1].strip()
            if Path(path).exists():
                return path
        # 如果是完整路径（以 / 开头）
        if line.strip().startswith("/") and Path(line.strip()).exists():
            return line.strip()
    return None


def _parse_image_list(list_result: str) -> List[str]:
    """从 list_images 的结果中提取所有图片路径"""
    paths = []
    lines = list_result.split("\n")
    for line in lines:
        if "Full path:" in line:
            path = line.split(":", 1)[-1].strip()
            if Path(path).exists():
                paths.append(path)
    return paths


def _get_class_distribution(detections: List[Dict]) -> Dict[str, int]:
    """统计检测结果中各类型的数量"""
    class_counts = {}
    if isinstance(detections, list):
        for det in detections:
            if isinstance(det, dict):
                cls = det.get("label", "unknown")
                class_counts[cls] = class_counts.get(cls, 0) + 1
    return class_counts


def _build_analysis(detections: List[Dict], severity: str) -> str:
    """根据检测结果构建分析文本"""
    if not detections or not isinstance(detections, list):
        return "未检测到异常目标，场景正常。"

    count = len(detections)
    class_dist = _get_class_distribution(detections)

    analysis_parts = []

    # 摘要
    analysis_parts.append(f"本次监控共检测到 {count} 个目标对象。")

    # 类型分布
    if class_dist:
        top_classes = sorted(class_dist.items(), key=lambda x: x[1], reverse=True)[:3]
        class_desc = ", ".join([f"{cls}({cnt}个)" for cls, cnt in top_classes])
        analysis_parts.append(f"主要类型包括: {class_desc}。")

    # 风险评估
    if severity == "critical":
        analysis_parts.append("⚠️ 检测到高风险情况，建议立即采取行动。")
    elif severity == "warning":
        analysis_parts.append("⚠️ 检测到可疑情况，建议加强监控。")
    else:
        analysis_parts.append("✅ 场景整体正常，继续保持监控。")

    return " ".join(analysis_parts)
