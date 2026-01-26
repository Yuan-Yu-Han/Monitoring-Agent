import logging
import uvicorn

from web.rtsp_service import RTSPStreamingService
from web.app import RTSPWebApp

# 你需要实现或导入的检测器和跟踪器示例
class DummyDetector:
    def detect(self, frame):
        # 返回空检测示例
        return []

class DummyTracker:
    def update(self, detections, frame_shape):
        # 返回空跟踪示例
        return []

def main():
    logging.basicConfig(level=logging.INFO)
    
    detector = DummyDetector()
    tracker = DummyTracker()
    streaming_service = RTSPStreamingService(detector, tracker)
    
    web_app = RTSPWebApp(streaming_service)
    
    uvicorn.run(web_app.app, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()
