import os
import json
import re
from PIL import Image, ImageDraw, ImageFont
from utils.image_utils import is_url, encode_image_to_base64
from config import CONFIG, client, SYSTEM_PROMPT, USER_PROMPT_TEMPLATES
from detection_agent.state import AgentState
from utils.nms_utils import apply_nms_with_config


def detect_image(state: AgentState) -> AgentState:
    """调用 Qwen-VL 模型检测图片，返回 JSON 字符串"""
    image_path = state["input_image"]
    
    # 获取检测模式 (支持动态切换)
    detection_mode = state.get("detection_mode", "default")
    user_prompt = USER_PROMPT_TEMPLATES.get(detection_mode, USER_PROMPT_TEMPLATES["default"])

    if is_url(image_path):
        image_url = image_path
    else:
        image_url = encode_image_to_base64(image_path)

    chat_response = client.chat.completions.create(
        model=CONFIG["model"]["name"],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},  # 🚀 专业化system prompt，高缓存价值
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": user_prompt},  # 🚀 简洁user prompt，动态切换
                ],
            },
        ],
        max_tokens=CONFIG["model"]["max_tokens"],
        temperature=CONFIG["model"]["temperature"],
    )
    result = chat_response.choices[0].message.content if hasattr(chat_response, "choices") else str(chat_response)
    state["raw_result"] = result
    return state


def safe_parse_json(state: AgentState) -> AgentState:
    """安全解析模型输出的 JSON，失败时返回 []"""
    text = state["raw_result"]

    try:
        detections = json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取中括号内内容
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                detections = json.loads(match.group(0))
            except json.JSONDecodeError:
                detections = []
        else:
            detections = []
    
    # 🚀 新增：应用非极大值抑制去除重复检测框
    if detections and CONFIG.get("detection", {}).get("enable_nms", True):
        # 获取NMS配置
        nms_config = CONFIG.get("detection", {}).get("nms_mode", "moderate")
        
        # 记录原始检测数量
        original_count = len(detections)
        
        # 应用NMS
        detections = apply_nms_with_config(detections, nms_config)
        
        # 记录NMS效果（如果启用统计）
        if CONFIG.get("detection", {}).get("nms_stats", True):
            nms_count = len(detections)
            state["nms_stats"] = {
                "original_count": original_count,
                "nms_count": nms_count,
                "removed_count": original_count - nms_count,
                "nms_config": nms_config
            }
    
    state["detections"] = detections
    return state


def draw_bboxes(state: AgentState) -> AgentState:
    """根据检测结果在图片上绘制边界框，返回新图路径"""
    image_path = state["input_image"]
    detections = state.get("detections", [])

    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("NotoSansCJKtc-Regular.otf", 16)  # 字体存不存在？
    except:
        font = ImageFont.load_default()
    
    for obj in detections:
        bbox = obj["bbox_2d"]
        label = obj.get("label", "")
        sub_label = obj.get("sub_label", "")
        draw.rectangle(bbox, outline="red", width=3)
        draw.text((bbox[0], bbox[1] - 16), f"{label} | {sub_label}", fill="yellow", font=font)

    # 保持子文件夹结构
    output_dir = CONFIG["io"]["output_dir"]
    input_dir = CONFIG["io"]["input_dir"]
    
    # 计算相对路径，保持子文件夹结构
    rel_path = os.path.relpath(image_path, input_dir)
    output_path = os.path.join(output_dir, rel_path)
    
    # 创建输出目录（包括子目录）
    output_subdir = os.path.dirname(output_path)
    os.makedirs(output_subdir, exist_ok=True)
    
    image.save(output_path)
    state["output_image"] = output_path
    return state


# 工具集成（节点函数）
tools = [detect_image, safe_parse_json, draw_bboxes]
