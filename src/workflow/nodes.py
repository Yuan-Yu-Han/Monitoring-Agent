from typing import Dict
from datetime import datetime

def image_input() -> Dict:
    """
    这个节点自动触发，模拟输入一张图片路径
    未来可以改成从FastAPI传入
    """
    image_path = "./inputs/fire1.jpg"  # 你这张测试图片路径
    print(f"📥 图片路径: {image_path}")
    return {
        "image_path": image_path,
        "timestamp": datetime.now().isoformat()
    }
