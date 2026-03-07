"""
实时捕获技能：
  - capture_current_frame  从 RTSP 流按需抓取一帧并立即分析
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import cv2
from langchain.tools import tool

from src.tools.detections import detect_image, extract_description, safe_parse_json, draw_bboxes
from src.utils.frame_registry import frame_registry
from src.skills._helpers import build_analysis, class_dist

logger = logging.getLogger(__name__)

# 按需捕获帧的保存目录
CAPTURE_DIR = Path(__file__).parent.parent.parent / "outputs" / "captures"


@tool
def capture_current_frame(
    description: str = "按需捕获",
    draw_boxes: bool = True,
    save_report: bool = False,
) -> str:
    """
    【实时捕获】从当前 RTSP 流按需抓取一帧并立即进行目标检测分析。
    适合用户主动询问"现在摄像头里有什么""当前画面正常吗"等实时查看需求。
    不依赖事件触发，随时可以调用。
    返回结构化 JSON，包含 summary（文字摘要）与检测元数据。

    Args:
        description: 本次捕获的说明标签（用于文件命名）
        draw_boxes: 是否在图片上绘制检测框
        save_report: 是否同时生成文字报告
    """
    try:
        from config import load_config
        config = load_config()

        rtsp_url = getattr(config.monitoring, "rtsp_url", None)
        if not rtsp_url:
            return json.dumps({
                "status": "error",
                "summary": "未配置 RTSP 地址（monitoring.rtsp_url），无法捕获实时画面。",
            }, ensure_ascii=False)

        # 连接 RTSP，抓取一帧
        frame = _grab_single_frame(rtsp_url)
        if frame is None:
            return json.dumps({
                "status": "error",
                "summary": f"无法连接 RTSP 流或读取帧（{rtsp_url}），请确认流地址是否正确且在线。",
                "rtsp_url": rtsp_url,
            }, ensure_ascii=False)

        # 保存帧到磁盘
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        event_id = f"capture_{ts}_{int(time.time() * 1000) % 10000}"
        image_path = str(CAPTURE_DIR / f"{event_id}.jpg")
        cv2.imwrite(image_path, frame)

        # 注册到 frame_registry，方便后续 event_id 查找
        frame_registry.register(event_id, image_path)
        logger.info(f"实时帧已保存: {image_path} (event_id={event_id})")

        # 一次 VL 调用同时得到检测结果和场景描述
        raw = detect_image.invoke({"input_image": image_path})
        detections = safe_parse_json(raw)
        scene_description = extract_description(raw)

        count = len(detections) if isinstance(detections, list) else 0
        dist = class_dist(detections)

        # 可选标注框
        annotated_path = None
        if count > 0 and draw_boxes:
            annotated_path = draw_bboxes(image_path, detections)

        dist_text = "、".join(f"{k}×{v}" for k, v in dist.items()) if dist else "无目标"
        fallback_summary = (
            f"实时画面捕获完成（{ts}），检测到 {count} 个目标（{dist_text}）。"
            if count > 0
            else f"实时画面捕获完成（{ts}），当前画面未检测到异常目标，场景正常。"
        )
        result = {
            "status": "success",
            "summary": scene_description or fallback_summary,
            "event_id": event_id,
            "captured_at": ts,
            "rtsp_url": rtsp_url,
            "image_path": image_path,
            "annotated_path": annotated_path,
            "detection_count": count,
            "class_distribution": dist,
            "detections": detections,
            "scene_description": scene_description,
        }

        if save_report:
            result["analysis"] = build_analysis(detections, "info")

        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"capture_current_frame 失败: {e}", exc_info=True)
        return json.dumps({"status": "error", "summary": f"捕获失败: {e}"}, ensure_ascii=False)


def _grab_single_frame(rtsp_url: str, timeout_sec: int = 8):
    """连接 RTSP 流，读取一帧后立即断开。返回 numpy 帧或 None。"""
    cap = None
    try:
        url = rtsp_url if "?" in rtsp_url else rtsp_url + "?tcp"
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_sec * 1000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_sec * 1000)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            logger.warning(f"无法打开 RTSP 流: {rtsp_url}")
            return None

        # 丢弃缓冲帧，取最新帧（最多尝试5次）
        frame = None
        for _ in range(5):
            ret, f = cap.read()
            if ret and f is not None and f.size > 0:
                frame = f
        return frame

    except Exception as e:
        logger.error(f"RTSP 抓帧异常: {e}")
        return None
    finally:
        if cap is not None:
            cap.release()
