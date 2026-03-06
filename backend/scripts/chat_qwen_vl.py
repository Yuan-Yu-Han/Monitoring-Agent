import os
import base64

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import json

# 配置API参数
OPENAI_API_KEY = "EMPTY"
OPENAI_API_BASE = "http://127.0.0.1:8000/v1"
MODEL_NAME = "Qwen2.5-VL"

OUTPUT_DIR = "./outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PROMPT = """
请检测图像中的所有火灾、烟雾和人员安全帽佩戴情况，并以坐标形式返回每个目标的位置。输出格式如下：

- fire对象:{"bbox_2d": [x1, y1, x2, y2], "label": "fire", "sub_label": "severe" / "slight" }
- person对象:{"bbox_2d": [x1, y1, x2, y2], "label": "person", "sub_label": "firefighter" / "passersby" }
- car对象:{"bbox_2d": [x1, y1, x2, y2], "label": "car", "sub_label": "fire truck" / "car on fire" / "normal car"}

请严格按照上述格式输出所有检测到的对象及其坐标和属性，三类对象分别输出。

检测规则：
- fire: 图像中存在明显火焰或燃烧迹象。
- person: 图像中有完整或部分可见的人体。
- firefighter: 图像中衣着装备符合消防员特征。
- passersby: 图像中没有消防员特征的人体
- car: 图像中有完整或部分可见的车辆。
- fire truck: 图像中存在明显的消防车特征的车辆。
- car on fire: 图像中存在明显的着火特征的车辆。
- normal car: 图像中没有消防车特征并且没有起火特征的普通车辆。

注意事项：
- 输出结果应尽量准确。
- 输出检测到的对象不要超过 20 个。

结果示例：
[
    {"bbox_2d": [100, 200, 180, 300], "label": "fire"},
    {"bbox_2d": [400, 320, 480, 420], "label": "person", "sub_label": "firefighter"},
    {"bbox_2d": [520, 330, 600, 430], "label": "car", "sub_label": "car on fire"}
]
"""

# - 烟雾对象：{"bbox_2d": [x1, y1, x2, y2], "label": "烟雾", "sub_label": "轻微" / "中等" / "严重" / "不确定"}
# - 人员对象：{"bbox_2d": [x1, y1, x2, y2], "label": "人员", "sub_label": "佩戴安全帽" / "未佩戴安全帽" / "不确定"}
# - 烟雾：图像中存在明显的烟雾扩散现象。
# - 安全帽佩戴：安全帽必须正确佩戴在头部，且帽檐朝前；若无法判断，则标记为 "不确定"。
    # {"bbox_2d": [220, 150, 350, 280], "label": "烟雾", "sub_label": "轻微"},

client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_API_BASE,
)

def is_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")

def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        encoded_image = base64.b64encode(f.read())
    encoded_image_text = encoded_image.decode("utf-8")
    ext = os.path.splitext(image_path)[-1].lower().replace('.', '')
    if ext == 'jpg':
        ext = 'jpeg'
    return f"data:image/{ext};base64,{encoded_image_text}"

def detect_image(image: str, prompt: str = PROMPT) -> str:
    if is_url(image):
        image_url = image
    else:
        image_url = encode_image_to_base64(image)
    chat_response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt},
                ],
            },
        ],
    )
    return chat_response.choices[0].message.content if hasattr(chat_response, 'choices') else str(chat_response)

def safe_parse_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取中括号内内容
        import re
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        # 最后返回空列表
        return []
        
def draw_bboxes(image_path: str, detections: list):
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("NotoSansCJK-Regular.ttc", 16)
    except:
        font = ImageFont.load_default()
    
    for obj in detections:
        bbox = obj["bbox_2d"]
        label = obj["label"]
        sub_label = obj["sub_label"]
        draw.rectangle(bbox, outline="red", width=3)
        draw.text((bbox[0], bbox[1]-16), f"{label} | {sub_label}", fill="yellow", font=font)

    output_path = os.path.join(OUTPUT_DIR, os.path.basename(image_path))
    image.save(output_path)
    return output_path
    
def main():
    local_images = [
        # 可在此添加需要检测的本地图片路径
        # "/workspace/qwen2.5-vl-7b-instruct/inputs/image_1.jpg",
        "./inputs/fire1.jpg",
    ]
    url_images = [
        # 可在此添加需要检测的互联网图片URL
        # "https://www.cdstm.cn/gallery/hycx/child/201703/W020170307572370556544.jpg"
    ]
    all_images = local_images + url_images

    results = []
    for img in all_images:
        print(f"检测图片: {img}")
        try:
            result = detect_image(img)
            print(f"结果: {result}\n{'-'*40}")
            output_img = draw_bboxes(img, safe_parse_json(result))
            print(f"带框图片已保存: {output_img}\n{'-'*40}")
            results.append({"image": img, "result": result, "output": output_img})
        except Exception as e:
            print(f"检测失败: {e}\n{'-'*40}")
            results.append({"image": img, "result": f"检测失败: {e}"})

if __name__ == "__main__":
    main()