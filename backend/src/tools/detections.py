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
    """调用 Qwen-VL 模型检测本地路径的图片，返回 JSON 字符串"""
    try:
        config = load_config()
        
        image_path = input_image
        if is_url(input_image):
            image_path = input_image
            image_url = image_path
        else:
            image_url = encode_image_to_base64(image_path)
        
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
            # vLLM/OpenAI-compatible servers may reject max_tokens if it exceeds remaining context.
            msg = str(exc)
            allowed = max_tokens_from_context_error(msg)
            if allowed is None:
                raise
            retry_max = clamp_max_tokens(min(allowed, requested_max_tokens or allowed), hard_cap=2048)
            kwargs["max_tokens"] = retry_max
            chat_response = client.chat.completions.create(**kwargs)

        result = chat_response.choices[0].message.content if hasattr(chat_response, "choices") else str(chat_response)
        return result
    except Exception as e:
        raise


@tool
def safe_parse_json(raw_result: str) -> list:
    """安全解析模型输出的 JSON，失败时返回 []"""
    try:
        detections = json.loads(raw_result)
        # 如果返回的是字典，提取其中的列表字段
        if isinstance(detections, dict):
            for key in ['objects', 'detections', 'results', 'predictions']:
                if key in detections and isinstance(detections[key], list):
                    return detections[key]
            # 返回字典中的第一个列表
            for value in detections.values():
                if isinstance(value, list):
                    return value
            return []
        elif isinstance(detections, list):
            return detections
        else:
            return []
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw_result, re.DOTALL)
        if match:
            try:
                detections = json.loads(match.group(0))
                return detections if isinstance(detections, list) else []
            except json.JSONDecodeError:
                return []
        return []


    except Exception as e:
        raise


@tool
def safe_parse_json(raw_result: str) -> list:
    """安全解析模型输出的 JSON，失败时返回 []"""
    try:
        detections = json.loads(raw_result)
        # 如果返回的是字典，提取其中的列表字段
        if isinstance(detections, dict):
            for key in ['objects', 'detections', 'results', 'predictions']:
                if key in detections and isinstance(detections[key], list):
                    return detections[key]
            # 返回字典中的第一个列表
            for value in detections.values():
                if isinstance(value, list):
                    return value
            return []
        elif isinstance(detections, list):
            return detections
        else:
            return []
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw_result, re.DOTALL)
        if match:
            try:
                detections = json.loads(match.group(0))
                result = detections if isinstance(detections, list) else []
                return result
            except json.JSONDecodeError:
                return []
        return []


@tool
def draw_bboxes(input_image: str, detections: list) -> str:
    """根据检测结果在图片上绘制边界框，返回新图路径"""
    try:
        import time
        config = load_config()
        
        # 类型验证
        if isinstance(detections, str):
            try:
                detections = json.loads(detections)
                if isinstance(detections, dict):
                    for key in ['objects', 'detections', 'results']:
                        if key in detections and isinstance(detections[key], list):
                            detections = detections[key]
                            break
            except:
                return input_image
        
        if not isinstance(detections, list):
            return input_image
        
        if not os.path.exists(input_image):
            return input_image
        
        try:
            image = Image.open(input_image).convert("RGB")
        except Exception as e:
            return input_image
        
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("NotoSansCJKtc-Regular.otf", 16)
        except:
            font = ImageFont.load_default()

        # 计算缩放比例（处理 0-1 / 0-1000 / 0-1024 等坐标系）
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

        # 绘制边界框
        drawn_count = 0
        for i, obj in enumerate(detections):
            try:
                if not isinstance(obj, dict):
                    continue
                if "bbox_2d" not in obj:
                    continue
                
                bbox = obj["bbox_2d"]
                if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                    continue
                
                # 转换坐标为整数元组，PIL.rectangle 需要 ((x1, y1), (x2, y2)) 格式
                x1 = int(bbox[0] * scale_x)
                y1 = int(bbox[1] * scale_y)
                x2 = int(bbox[2] * scale_x)
                y2 = int(bbox[3] * scale_y)

                # 边界夹紧
                x1 = max(0, min(x1, img_w - 1))
                y1 = max(0, min(y1, img_h - 1))
                x2 = max(0, min(x2, img_w - 1))
                y2 = max(0, min(y2, img_h - 1))
                
                label = obj.get("label", "")
                sub_label = obj.get("sub_label", "")
                
                # 使用正确的坐标格式：((x1, y1), (x2, y2))
                draw.rectangle(((x1, y1), (x2, y2)), outline="red", width=3)
                
                # 文字位置：在矩形上方，保证不超出图片边界
                text_y = max(0, y1 - 20)
                draw.text((x1 + 2, text_y), f"{label} | {sub_label}", fill="yellow", font=font)
                
                drawn_count += 1
            except Exception as e:
                continue

        # 保存到 outputs/agent 文件夹
        output_dir = "./outputs/agent"
        os.makedirs(output_dir, exist_ok=True)
        
        # 使用时间戳和原文件名生成唯一的输出文件名
        import time
        base_name = os.path.splitext(os.path.basename(input_image))[0]
        ext = os.path.splitext(input_image)[1]
        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        output_path = os.path.join(output_dir, f"{base_name}_detected_{timestamp}{ext}")

        image.save(output_path)
        return output_path
    
    except Exception as e:
        raise
