import os
import json
import re
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI
from src.utils.image_utils import is_url, encode_image_to_base64
from src.utils.openai_compat import clamp_max_tokens, max_tokens_from_context_error
from prompts.prompt_loader import load_prompt
from config import load_config
from langchain.tools import tool


@tool
def detect_image(input_image: str) -> str:
    """调用 Qwen-VL 模型检测本地路径的图片，返回 JSON 字符串（含 description 和 objects）"""
    try:
        config = load_config()

        if is_url(input_image):
            image_url = input_image
        else:
            image_url = encode_image_to_base64(input_image)

        messages = [
            {"role": "system", "content": load_prompt("detection_prompt")},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}}
                ],
            },
        ]

        client = OpenAI(api_key=config.vllm_chat.api_key, base_url=config.vllm_chat.base_url)
        requested_max_tokens = clamp_max_tokens(getattr(config.vllm_chat, "max_tokens", None), hard_cap=2048)
        kwargs = {
            "model": "Qwen3-VL-8B-Instruct",
            "messages": messages,
            "temperature": config.vllm_chat.temperature,
        }
        if requested_max_tokens is not None:
            kwargs["max_tokens"] = requested_max_tokens

        try:
            chat_response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            msg = str(exc)
            allowed = max_tokens_from_context_error(msg)
            if allowed is None:
                raise
            retry_max = clamp_max_tokens(min(allowed, requested_max_tokens or allowed), hard_cap=2048)
            kwargs["max_tokens"] = retry_max
            chat_response = client.chat.completions.create(**kwargs)

        return chat_response.choices[0].message.content if hasattr(chat_response, "choices") else str(chat_response)
    except Exception:
        raise


def safe_parse_json(raw_result: str) -> list:
    """从模型输出中提取 objects 检测列表。供内部调用，不作为 Agent 工具暴露。"""
    try:
        parsed = json.loads(raw_result)
        # 新格式：{"description": "...", "objects": [...]}
        if isinstance(parsed, dict):
            for key in ["objects", "detections", "results", "predictions"]:
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
            for value in parsed.values():
                if isinstance(value, list):
                    return value
            return []
        # 兼容旧格式：直接返回数组
        if isinstance(parsed, list):
            return parsed
        return []
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw_result, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []


def extract_description(raw_result: str) -> str:
    """从模型输出中提取自然语言场景描述。供内部调用，不作为 Agent 工具暴露。"""
    try:
        parsed = json.loads(raw_result)
        if isinstance(parsed, dict):
            return str(parsed.get("description", "")).strip()
        return ""
    except json.JSONDecodeError:
        match = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', raw_result)
        if match:
            return match.group(1).replace('\\"', '"').replace("\\n", "\n").strip()
        return ""


def draw_bboxes(input_image: str, detections: list) -> str:
    """根据检测结果在图片上绘制边界框，返回新图路径"""
    try:
        import time

        if isinstance(detections, str):
            try:
                detections = json.loads(detections)
                if isinstance(detections, dict):
                    for key in ['objects', 'detections', 'results']:
                        if key in detections and isinstance(detections[key], list):
                            detections = detections[key]
                            break
            except Exception:
                return input_image

        if not isinstance(detections, list):
            return input_image

        if not os.path.exists(input_image):
            return input_image

        try:
            image = Image.open(input_image).convert("RGB")
        except Exception:
            return input_image

        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("NotoSansCJKtc-Regular.otf", 16)
        except Exception:
            font = ImageFont.load_default()

        img_w, img_h = image.size
        max_x = 0
        max_y = 0
        for obj in detections:
            if isinstance(obj, dict) and "bbox_2d" in obj:
                bbox = obj["bbox_2d"]
                if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                    max_x = max(max_x, bbox[0], bbox[2])
                    max_y = max(max_y, bbox[1], bbox[3])

        scale_x, scale_y = 1.0, 1.0
        if max_x <= 1.5 and max_y <= 1.5:
            scale_x, scale_y = img_w, img_h
        elif max_x > img_w or max_y > img_h:
            if max_x <= 1000 and max_y <= 1000:
                scale_x, scale_y = img_w / 1000.0, img_h / 1000.0
            elif max_x <= 1024 and max_y <= 1024:
                scale_x, scale_y = img_w / 1024.0, img_h / 1024.0
            elif max_x <= 640 and max_y <= 640:
                scale_x, scale_y = img_w / 640.0, img_h / 640.0

        for obj in detections:
            try:
                if not isinstance(obj, dict) or "bbox_2d" not in obj:
                    continue
                bbox = obj["bbox_2d"]
                if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                    continue

                x1 = max(0, min(int(bbox[0] * scale_x), img_w - 1))
                y1 = max(0, min(int(bbox[1] * scale_y), img_h - 1))
                x2 = max(0, min(int(bbox[2] * scale_x), img_w - 1))
                y2 = max(0, min(int(bbox[3] * scale_y), img_h - 1))

                label = obj.get("label", "")
                sub_label = obj.get("sub_label", "")

                draw.rectangle(((x1, y1), (x2, y2)), outline="red", width=3)
                text_y = max(0, y1 - 20)
                draw.text((x1 + 2, text_y), f"{label} | {sub_label}", fill="yellow", font=font)
            except Exception:
                continue

        output_dir = "./outputs/vl/annotated"
        os.makedirs(output_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(input_image))[0]
        ext = os.path.splitext(input_image)[1]
        timestamp = int(time.time() * 1000)
        output_path = os.path.join(output_dir, f"{base_name}_detected_{timestamp}{ext}")

        try:
            if ext.lower() in (".jpg", ".jpeg"):
                image.save(output_path, quality=95, subsampling=0, optimize=True)
            else:
                image.save(output_path)
        except Exception:
            # Fallback without extra parameters
            image.save(output_path)
        return output_path

    except Exception:
        raise
