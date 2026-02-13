import base64
import os
import cv2
import numpy as np

def decode_base64_to_numpy(base64_str: str) -> np.ndarray:
    """将 base64 编码的图片解码为 numpy 数组（BGR）"""
    img_bytes = base64.b64decode(base64_str)
    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    return img



def is_url(path: str) -> bool:
    """
    判断给定路径是否是 URL。
    """
    return path.startswith("http://") or path.startswith("https://")


def encode_image_to_base64(image_path: str) -> str:
    """
    将本地图片读取并编码为 base64 格式，返回 data URI。
    支持 jpg/jpeg/png 等常用格式。
    
    Args:
        image_path: 图片文件路径
    
    Returns:
        data URI 格式的 base64 编码字符串
    """
    with open(image_path, "rb") as f:
        encoded_image = base64.b64encode(f.read())
    encoded_image_text = encoded_image.decode("utf-8")
    ext = os.path.splitext(image_path)[-1].lower().replace('.', '')
    if ext == 'jpg':
        ext = 'jpeg'
    return f"data:image/{ext};base64,{encoded_image_text}"


def encode_numpy_to_base64(frame: np.ndarray, format: str = 'jpeg') -> str:
    """
    将 numpy 数组（OpenCV 图像）编码为 base64 字符串。
    
    Args:
        frame: OpenCV 图像（numpy array）
        format: 图像格式，默认 'jpeg'
    
    Returns:
        Base64 编码的图像字符串
    
    Raises:
        ValueError: 如果编码失败
    """
    try:
        # 编码为指定格式
        ext = f'.{format.lower()}'
        success, buffer = cv2.imencode(ext, frame)
        
        if not success:
            raise ValueError(f"Failed to encode image to {format}")
        
        # 转为 Base64
        image_bytes = buffer.tobytes()
        return base64.b64encode(image_bytes).decode('utf-8')
    
    except Exception as e:
        raise ValueError(f"图像编码失败: {str(e)}")
