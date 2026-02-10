import os
import json
import re
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI
from src.utils.image_utils import is_url, encode_image_to_base64
from prompts.prompt_loader import load_prompt
from config import load_config
from langchain.tools import tool
from src.tools.tool_interceptor import log_tool_call, log_tool_step, log_tool_result, log_tool_error


@tool
def detect_image(input_image: str) -> str:
    """调用 Qwen-VL 模型检测本地路径的图片，返回 JSON 字符串"""
    log_tool_call("detect_image", input_image=input_image)
    
    try:
        log_tool_step("加载配置...")
        config = load_config()
        
        log_tool_step(f"编码图片: {input_image}")
        image_path = input_image
        if is_url(input_image):
            log_tool_step("检测到 URL，转换为 Base64 编码...")
            image_path = input_image
        else:
            log_tool_step("检测到本地路径，编码为 Base64...")
            image_url = encode_image_to_base64(image_path)
        
        log_tool_step("构造消息...")
        messages = [
            {"role": "system", "content": load_prompt("detection_prompt")},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}}
                ],
            },
        ]

        log_tool_step("调用 Qwen-VL 模型...")
        client = OpenAI(api_key=config.vllm_chat.api_key, base_url=config.vllm_chat.base_url)
        chat_response = client.chat.completions.create(
            model="Qwen3-VL-8B-Instruct",
            messages=messages,
            max_tokens=config.vllm_chat.max_tokens,
            temperature=config.vllm_chat.temperature,
        )

        log_tool_step("解析模型响应...")
        result = chat_response.choices[0].message.content if hasattr(chat_response, "choices") else str(chat_response)
        log_tool_result(result)
        return result
    except Exception as e:
        log_tool_error(str(e))
        raise


@tool
def safe_parse_json(raw_result: str) -> list:
    """安全解析模型输出的 JSON，失败时返回 []"""
    log_tool_call("safe_parse_json", raw_result=raw_result[:100])
    
    try:
        log_tool_step("尝试直接 JSON 解析...")
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
        log_tool_error(str(e))
        raise


@tool
def safe_parse_json(raw_result: str) -> list:
    """安全解析模型输出的 JSON，失败时返回 []"""
    log_tool_call("safe_parse_json", raw_result=raw_result[:100])
    
    try:
        log_tool_step("尝试直接 JSON 解析...")
        detections = json.loads(raw_result)
        # 如果返回的是字典，提取其中的列表字段
        if isinstance(detections, dict):
            log_tool_step("检测到字典格式，提取列表字段...")
            for key in ['objects', 'detections', 'results', 'predictions']:
                if key in detections and isinstance(detections[key], list):
                    log_tool_step(f"找到字段: {key}")
                    log_tool_result(detections[key])
                    return detections[key]
            # 返回字典中的第一个列表
            for value in detections.values():
                if isinstance(value, list):
                    log_tool_step("使用第一个列表字段")
                    log_tool_result(value)
                    return value
            log_tool_result([])
            return []
        elif isinstance(detections, list):
            log_tool_step("检测到列表格式")
            log_tool_result(detections)
            return detections
        else:
            log_tool_result([])
            return []
    except json.JSONDecodeError:
        log_tool_step("直接解析失败，使用正则提取...")
        match = re.search(r"\[.*\]", raw_result, re.DOTALL)
        if match:
            try:
                log_tool_step("尝试解析提取的数据...")
                detections = json.loads(match.group(0))
                result = detections if isinstance(detections, list) else []
                log_tool_result(result)
                return result
            except json.JSONDecodeError:
                log_tool_error("正则提取的数据解析失败")
                log_tool_result([])
                return []
        log_tool_error("无法找到 JSON 数组")
        log_tool_result([])
        return []


@tool
def draw_bboxes(input_image: str, detections: list) -> str:
    """根据检测结果在图片上绘制边界框，返回新图路径"""
    log_tool_call("draw_bboxes", input_image=input_image, detections_count=len(detections) if isinstance(detections, list) else 0)
    
    try:
        import time
        config = load_config()
        
        log_tool_step("验证检测数据类型...")
        # 类型验证
        if isinstance(detections, str):
            log_tool_step("检测到字符串格式，尝试 JSON 解析...")
            try:
                detections = json.loads(detections)
                if isinstance(detections, dict):
                    for key in ['objects', 'detections', 'results']:
                        if key in detections and isinstance(detections[key], list):
                            detections = detections[key]
                            break
            except:
                log_tool_error("JSON 解析失败")
                return input_image
        
        if not isinstance(detections, list):
            log_tool_error(f"detections must be list, got {type(detections)}")
            return input_image
        
        log_tool_step(f"检查图片文件: {input_image}")
        if not os.path.exists(input_image):
            log_tool_error(f"Image not found: {input_image}")
            return input_image
        
        log_tool_step("打开图片...")
        try:
            image = Image.open(input_image).convert("RGB")
        except Exception as e:
            log_tool_error(f"Failed to open image: {e}")
            return input_image
        
        log_tool_step(f"图片尺寸: {image.size}")
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("NotoSansCJKtc-Regular.otf", 16)
        except:
            font = ImageFont.load_default()

        log_tool_step("计算坐标缩放比例...")
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
            log_tool_step(f"检测到 0-1 归一化坐标 -> 缩放为 ({scale_x}, {scale_y})")
        elif max_x > img_w or max_y > img_h:
            if max_x <= 1000 and max_y <= 1000:
                scale_x, scale_y = img_w / 1000.0, img_h / 1000.0
                log_tool_step(f"检测到 0-1000 坐标系 -> 缩放为 ({scale_x:.4f}, {scale_y:.4f})")
            elif max_x <= 1024 and max_y <= 1024:
                scale_x, scale_y = img_w / 1024.0, img_h / 1024.0
                log_tool_step(f"检测到 0-1024 坐标系 -> 缩放为 ({scale_x:.4f}, {scale_y:.4f})")
            elif max_x <= 640 and max_y <= 640:
                scale_x, scale_y = img_w / 640.0, img_h / 640.0
                log_tool_step(f"检测到 0-640 坐标系 -> 缩放为 ({scale_x:.4f}, {scale_y:.4f})")
            else:
                log_tool_step(f"无需缩放 (max_x={max_x}, max_y={max_y})")

        log_tool_step(f"开始绘制边界框 ({len(detections)} 个)...")
        # 绘制边界框
        drawn_count = 0
        for i, obj in enumerate(detections):
            try:
                if not isinstance(obj, dict):
                    log_tool_step(f"⚠️ 对象 {i} 不是字典类型，跳过")
                    continue
                if "bbox_2d" not in obj:
                    log_tool_step(f"⚠️ 对象 {i} 缺少 bbox_2d，跳过")
                    continue
                
                bbox = obj["bbox_2d"]
                if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                    log_tool_step(f"⚠️ 对象 {i} bbox 格式无效: {bbox}")
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
                
                log_tool_step(f"✅ 绘制对象 {i}: ({x1},{y1},{x2},{y2}) {label}/{sub_label}")
                drawn_count += 1
            except Exception as e:
                log_tool_step(f"⚠️ 绘制对象 {i} 失败: {e}")
                continue
        
        log_tool_step(f"成功绘制 {drawn_count}/{len(detections)} 个检测结果")

        log_tool_step("保存输出图片...")
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
        log_tool_result(output_path)
        return output_path
    
    except Exception as e:
        log_tool_error(str(e))
        raise
