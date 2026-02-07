"""
YOLO 检测服务
封装 YOLO 模型，提供统一的检测接口
"""

from ultralytics import YOLO
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class YOLOConfig:
    """YOLO 配置"""
    model_path: str = "yolov8n.pt"  # 模型路径
    confidence: float = 0.5          # 置信度阈值
    iou: float = 0.45                # NMS IOU 阈值
    device: str = "cuda:0"           # 设备 (cpu, cuda:0, etc.)
    imgsz: int = 640                 # 输入图像大小


class YOLODetector:
    """
    YOLO 检测器
    
    封装 Ultralytics YOLO 模型，提供简化的检测接口
    """
    
    def __init__(self, config: YOLOConfig):
        self.config = config
        self.model: Optional[YOLO] = None
        self._load_model()
    
    def _load_model(self):
        """加载 YOLO 模型"""
        try:
            logger.info(f"正在加载 YOLO 模型: {self.config.model_path}")
            self.model = YOLO(self.config.model_path)
            logger.info(f"✅ YOLO 模型加载成功，设备: {self.config.device}")
        except Exception as e:
            logger.error(f"❌ YOLO 模型加载失败: {e}")
            raise
    
    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        对单帧进行检测
        
        Args:
            frame: 输入图像 (numpy array, BGR format)
            
        Returns:
            检测结果列表，每个元素包含:
            {
                "class": str,           # 类别名称
                "confidence": float,    # 置信度
                "bbox": [x1, y1, x2, y2]  # 边界框坐标
            }
        """
        if self.model is None:
            raise RuntimeError("YOLO 模型未加载")
        
        try:
            # 运行推理
            results = self.model.predict(
                frame,
                conf=self.config.confidence,
                iou=self.config.iou,
                device=self.config.device,
                imgsz=self.config.imgsz,
                verbose=False  # 关闭详细输出
            )
            
            # 解析结果
            detections = []
            if len(results) > 0:
                result = results[0]  # 单张图像
                
                if result.boxes is not None and len(result.boxes) > 0:
                    boxes = result.boxes.cpu().numpy()
                    
                    for box in boxes:
                        detection = {
                            "class": result.names[int(box.cls[0])],
                            "confidence": float(box.conf[0]),
                            "bbox": box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                        }
                        detections.append(detection)
            
            return detections
            
        except Exception as e:
            logger.error(f"YOLO 检测失败: {e}")
            return []
    
    def detect_batch(self, frames: List[np.ndarray]) -> List[List[Dict[str, Any]]]:
        """
        批量检测
        
        Args:
            frames: 图像列表
            
        Returns:
            每张图像的检测结果列表
        """
        if self.model is None:
            raise RuntimeError("YOLO 模型未加载")
        
        try:
            results = self.model.predict(
                frames,
                conf=self.config.confidence,
                iou=self.config.iou,
                device=self.config.device,
                imgsz=self.config.imgsz,
                verbose=False
            )
            
            all_detections = []
            for result in results:
                detections = []
                if result.boxes is not None and len(result.boxes) > 0:
                    boxes = result.boxes.cpu().numpy()
                    
                    for box in boxes:
                        detection = {
                            "class": result.names[int(box.cls[0])],
                            "confidence": float(box.conf[0]),
                            "bbox": box.xyxy[0].tolist()
                        }
                        detections.append(detection)
                
                all_detections.append(detections)
            
            return all_detections
            
        except Exception as e:
            logger.error(f"YOLO 批量检测失败: {e}")
            return [[] for _ in frames]
    
    def get_class_names(self) -> List[str]:
        """获取模型支持的类别名称"""
        if self.model is None:
            return []
        return list(self.model.names.values())


# 测试示例
if __name__ == "__main__":
    import cv2
    logging.basicConfig(level=logging.INFO)
    
    # 配置
    config = YOLOConfig(
        model_path="yolov8n.pt",
        confidence=0.5,
        device="cpu"  # 如果有 GPU 使用 "cuda:0"
    )
    
    # 创建检测器
    detector = YOLODetector(config)
    
    # 读取测试图像
    test_image = "/home/yuan0165/yyh/Monitoring-Agent/inputs/fire1.jpg"
    frame = cv2.imread(test_image)
    
    if frame is not None:
        # 检测
        detections = detector.detect(frame)
        
        print(f"\n检测到 {len(detections)} 个目标:")
        for i, det in enumerate(detections):
            print(f"  [{i+1}] {det['class']}: {det['confidence']:.2f}")
        
        # 可视化（可选）
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det['bbox']]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{det['class']}: {det['confidence']:.2f}"
            cv2.putText(frame, label, (x1, y1-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # 保存结果
        output_path = "./yolo_result.jpg"
        cv2.imwrite(output_path, frame)
        print(f"\n结果已保存到: {output_path}")
