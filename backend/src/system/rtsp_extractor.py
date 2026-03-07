"""
RTSP 帧抽取器
从 RTSP 流中按指定间隔抽取帧
"""

import cv2
import numpy as np
from typing import Optional, Iterator
from dataclasses import dataclass
import logging
import time
import os

# 抑制 OpenCV/FFmpeg 的警告信息
os.environ['OPENCV_FFMPEG_LOGLEVEL'] = '-8'
os.environ['OPENCV_LOG_LEVEL'] = 'ERROR'

logger = logging.getLogger(__name__)


@dataclass
class FrameExtractorConfig:
    """帧抽取器配置"""
    rtsp_url: str                       # RTSP 流地址
    fps: float = 1.0                    # 抽帧频率（每秒抽取多少帧）
    resize_width: Optional[int] = None  # 缩放宽度（None 表示不缩放）
    resize_height: Optional[int] = None # 缩放高度
    reconnect_interval: int = 5         # 重连间隔（秒）
    max_reconnect_attempts: int = 5    # 最大重连次数（-1 表示无限）
    use_tcp: bool = True                # 使用 TCP 传输（更稳定，但延迟稍高）


class RTSPFrameExtractor:
    """
    RTSP 帧抽取器
    
    核心功能：
    1. 连接 RTSP 流
    2. 按指定 FPS 抽取帧
    3. 断线自动重连
    4. 提供迭代器接口
    
    使用示例：
        config = FrameExtractorConfig(
            rtsp_url="rtsp://127.0.0.1:8554/mystream",
            fps=1
        )
        extractor = RTSPFrameExtractor(config)
        
        for frame in extractor.stream():
            # 处理帧
            process_frame(frame)
    """
    
    def __init__(self, config: FrameExtractorConfig):
        self.config = config
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_connected = False
        if float(config.fps) <= 0:
            raise ValueError("FrameExtractorConfig.fps must be > 0")
        self.frame_interval = 1.0 / float(config.fps)  # 帧间隔（秒）
        
    def connect(self) -> bool:
        """连接 RTSP 流"""
        try:# 构建 RTSP URL（如果需要使用 TCP）
            rtsp_url = self.config.rtsp_url
            if self.config.use_tcp and '?' not in rtsp_url:
                rtsp_url += "?tcp"
            
            logger.info(f"正在连接 RTSP 流: {rtsp_url}")
            
            # 使用 CAP_FFMPEG 后端
            self.cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            
            # 设置 OpenCV 参数以提高容错性
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 最小缓冲区，获取最新帧
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)  # 减小缓冲区，降低延迟
                # 设置超时
                self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
            
            if not self.cap.isOpened():
                logger.error("无法打开 RTSP 流")
                return False
            
            # 读取一帧测试
            ret, _ = self.cap.read()
            if not ret:
                logger.error("无法读取 RTSP 流数据")
                self.cap.release()
                return False
            
            self.is_connected = True
            logger.info("✅ RTSP 流连接成功")
            return True
            
        except Exception as e:
            logger.error(f"连接 RTSP 流失败: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.is_connected = False
        logger.info("RTSP 流已断开")
    
    def _resize_frame(self, frame: np.ndarray) -> np.ndarray:
        """缩放帧"""
        if self.config.resize_width and self.config.resize_height:
            return cv2.resize(
                frame, 
                (self.config.resize_width, self.config.resize_height)
            )
        return frame
    
    def read_frame(self) -> Optional[np.ndarray]:
        """读取一帧"""
        if not self.is_connected or self.cap is None:
            return None
        
        try:
            ret, frame = self.cap.read()
            if not ret:
                logger.warning("读取帧失败，可能流已断开")
                self.is_connected = False
                return None
            
            # 检查帧是否有效
            if frame is None or frame.size == 0:
                logger.debug("收到空帧，跳过")
                return None
            
            return self._resize_frame(frame)
            
        except Exception as e:
            logger.error(f"读取帧异常: {e}")
            self.is_connected = False
            return None
    
    def stream(self) -> Iterator[np.ndarray]:
        """
        生成器：持续抽取帧
        
        Yields:
            numpy.ndarray: 图像帧 (BGR 格式)
        """
        reconnect_count = 0
        
        while True:
            # 连接或重连
            if not self.is_connected:
                if (self.config.max_reconnect_attempts >= 0 and 
                    reconnect_count >= self.config.max_reconnect_attempts):
                    logger.error("达到最大重连次数，退出")
                    break
                
                if not self.connect():
                    reconnect_count += 1
                    logger.warning(
                        f"重连失败 ({reconnect_count}/"
                        f"{self.config.max_reconnect_attempts}), "
                        f"{self.config.reconnect_interval} 秒后重试"
                    )
                    time.sleep(self.config.reconnect_interval)
                    continue
                
                reconnect_count = 0  # 重置计数
            
            # 读取帧
            frame = self.read_frame()
            if frame is not None:
                yield frame
            
            # 控制帧率
            time.sleep(self.frame_interval)
    
    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.disconnect()


# 简单的测试示例
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    config = FrameExtractorConfig(
        rtsp_url="rtsp://127.0.0.1:8554/mystream",
        fps=5,
        resize_width=640,
        resize_height=480
    )
    
    extractor = RTSPFrameExtractor(config)
    
    try:
        for i, frame in enumerate(extractor.stream()):
            print(f"收到第 {i+1} 帧，shape: {frame.shape}")
            
            # 测试显示（需要 X11 环境）
            # cv2.imshow("RTSP Stream", frame)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     break
            
            if i >= 100:  # 测试 100 帧后退出
                break
    
    finally:
        extractor.disconnect()
        # cv2.destroyAllWindows()
