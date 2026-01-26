import asyncio
import time
import logging
from typing import List, Dict

import cv2
import numpy as np

from .stream_reader import VideoStreamReader
from .websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)

class RTSPStreamingService:
    def __init__(self, detector, tracker):
        self.detector = detector
        self.tracker = tracker
        self.stream_reader = None
        self.websocket_manager = WebSocketManager()
        self.running = False
        self.inference_task = None
        self.current_source = None
        
        self.stats = {
            "total_frames": 0,
            "total_detections": 0,
            "total_tracks": 0,
            "start_time": None,
            "fps": 0
        }
    
    async def start_streaming(self, source: str):
        if self.running:
            await self.stop_streaming()
        
        self.current_source = source
        self.stream_reader = VideoStreamReader(source)
        self.stream_reader.start()
        
        self.running = True
        self.stats["start_time"] = time.time()
        self.stats["total_frames"] = 0
        
        self.inference_task = asyncio.create_task(self._inference_loop())
        logger.info(f"RTSP流处理已启动: {source}")
    
    async def stop_streaming(self):
        self.running = False
        if self.inference_task:
            self.inference_task.cancel()
            try:
                await self.inference_task
            except asyncio.CancelledError:
                pass
        if self.stream_reader:
            self.stream_reader.stop()
        logger.info("RTSP流处理已停止")
    
    async def _inference_loop(self):
        while self.running:
            try:
                frame = self.stream_reader.get_frame(timeout=0.1)
                if frame is None:
                    await asyncio.sleep(0.01)
                    continue
                
                detections = self.detector.detect(frame)
                tracks = self.tracker.update(detections, frame.shape[:2])
                
                self.stats["total_frames"] += 1
                self.stats["total_detections"] += len(detections)
                self.stats["total_tracks"] += len(tracks)
                
                if self.stats["start_time"]:
                    elapsed = time.time() - self.stats["start_time"]
                    if elapsed > 0:
                        self.stats["fps"] = self.stats["total_frames"] / elapsed
                
                annotated_frame = self._draw_detections(frame, tracks)
                
                _, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frame_data = buffer.tobytes()
                
                message = {
                    "type": "frame",
                    "timestamp": time.time(),
                    "frame_data": frame_data.hex(),
                    "detections": detections,
                    "tracks": tracks,
                    "stats": self.stats.copy()
                }
                
                await self.websocket_manager.broadcast(message)
                await asyncio.sleep(0.03)
            except Exception as e:
                logger.error(f"推理循环错误: {e}")
                await asyncio.sleep(0.1)
    
    def _draw_detections(self, frame: np.ndarray, tracks: List[Dict]) -> np.ndarray:
        annotated_frame = frame.copy()
        for track in tracks:
            bbox = track["bbox"]
            track_id = track["track_id"]
            label = track["label"]
            conf = track["conf"]
            
            x1, y1, x2, y2 = map(int, bbox)
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label_text = f"ID:{track_id} {label} {conf:.2f}"
            label_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(annotated_frame, (x1, y1 - label_size[1] - 10), 
                          (x1 + label_size[0], y1), (0, 255, 0), -1)
            cv2.putText(annotated_frame, label_text, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
        return annotated_frame
    
    def get_stats(self):
        return self.stats.copy()
