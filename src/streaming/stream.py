import threading
import time
import queue
import logging

try:
    import cv2
    import numpy as np
except ImportError:
    raise ImportError("opencv-python and numpy are required")

logger = logging.getLogger(__name__)

class VideoStreamReader:
    """视频流读取器"""
    
    def __init__(self, source: str, queue_size: int = 10):
        self.source = source
        self.queue = queue.Queue(maxsize=queue_size)
        self.cap = None
        self.running = False
        self.thread = None
        self.last_frame_time = 0
        self.fps = 30
        self.frame_interval = 1.0 / self.fps
    
    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._read_frames, daemon=True)
        self.thread.start()
        logger.info(f"视频流读取器已启动: {self.source}")
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
        logger.info("视频流读取器已停止")
    
    def _read_frames(self):
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            logger.error(f"无法打开视频源: {self.source}")
            return
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                logger.warning("读取帧失败，尝试重新连接...")
                time.sleep(1)
                self.cap.release()
                self.cap = cv2.VideoCapture(self.source)
                continue
            
            current_time = time.time()
            if current_time - self.last_frame_time < self.frame_interval:
                continue
            self.last_frame_time = current_time
            
            try:
                self.queue.put(frame, block=False)
            except queue.Full:
                try:
                    self.queue.get_nowait()
                    self.queue.put(frame, block=False)
                except queue.Empty:
                    pass
    
    def get_frame(self, timeout: float = 0.1):
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None
