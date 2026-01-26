import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

class RTSPWebApp:
    def __init__(self, streaming_service):
        self.streaming_service = streaming_service
        self.app = None
        self._create_app()
    
    def _create_app(self):
        self.app = FastAPI(title="YOLO RTSP Streaming Service")
        try:
            self.app.mount("/static", StaticFiles(directory="static"), name="static")
        except Exception:
            pass
        self._setup_routes()
    
    def _setup_routes(self):
        @self.app.get("/")
        async def root():
            return HTMLResponse(self._get_index_html())
        
        @self.app.get("/health")
        async def health():
            return {"status": "ok", "streaming": self.streaming_service.running}
        
        @self.app.post("/start")
        async def start_streaming(data: dict):
            source = data.get("source")
            if not source:
                return JSONResponse({"status": "error", "error": "Missing source"}, status_code=400)
            try:
                await self.streaming_service.start_streaming(source)
                return {"status": "started", "source": source}
            except Exception as e:
                return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
        
        @self.app.post("/stop")
        async def stop_streaming():
            try:
                await self.streaming_service.stop_streaming()
                return {"status": "stopped"}
            except Exception as e:
                return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
        
        @self.app.get("/stats")
        async def get_stats():
            return self.streaming_service.get_stats()
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.streaming_service.websocket_manager.connect(websocket)
            try:
                while True:
                    data = await websocket.receive_text()
                    await websocket.send_text(f"ack: {data}")
            except WebSocketDisconnect:
                self.streaming_service.websocket_manager.disconnect(websocket)
            except Exception as e:
                logger.error(f"WebSocket错误: {e}")
                self.streaming_service.websocket_manager.disconnect(websocket)
    
    def _get_index_html(self) -> str:
        return """
<!DOCTYPE html>
<html>
<head>
    <title>YOLO RTSP Streaming</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .video-container { text-align: center; margin: 20px 0; }
        .controls { margin: 20px 0; }
        .stats { background: #f5f5f5; padding: 10px; border-radius: 5px; margin: 10px 0; }
        input[type="text"] { width: 300px; padding: 5px; }
        button { padding: 8px 16px; margin: 5px; cursor: pointer; }
        #videoFrame { max-width: 100%; border: 1px solid #ccc; }
    </style>
</head>
<body>
    <div class="container">
        <h1>YOLO RTSP Streaming Service</h1>
        
        <div class="controls">
            <input type="text" id="sourceInput" placeholder="输入RTSP地址或视频文件路径" 
                   value="rtsp://admin:password@192.168.1.10:554/stream">
            <button onclick="startStreaming()">开始流</button>
            <button onclick="stopStreaming()">停止流</button>
        </div>
        
        <div class="stats" id="stats">
            <h3>统计信息</h3>
            <div id="statsContent">等待连接...</div>
        </div>
        
        <div class="video-container">
            <img id="videoFrame" src="" alt="视频流">
        </div>
    </div>

    <script>
        let ws = null;
        let statsInterval = null;

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            ws = new WebSocket(wsUrl);
            
            ws.onopen = function() {
                console.log('WebSocket连接已建立');
                updateStats();
                statsInterval = setInterval(updateStats, 1000);
            };
            
            ws.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'frame') {
                        const frameData = data.frame_data;
                        const binaryData = new Uint8Array(frameData.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
                        const blob = new Blob([binaryData], {type: 'image/jpeg'});
                        const url = URL.createObjectURL(blob);
                        document.getElementById('videoFrame').src = url;
                        updateStatsDisplay(data.stats);
                    }
                } catch (e) {
                    console.log('收到文本消息:', event.data);
                }
            };
            
            ws.onclose = function() {
                console.log('WebSocket连接已关闭');
                if (statsInterval) clearInterval(statsInterval);
            };
            
            ws.onerror = function(error) {
                console.error('WebSocket错误:', error);
            };
        }

        function startStreaming() {
            const source = document.getElementById('sourceInput').value;
            if (!source) {
                alert('请输入视频源');
                return;
            }
            
            fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({source: source})
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'started') {
                    console.log('流处理已启动');
                } else {
                    alert('启动失败: ' + data.error);
                }
            })
            .catch(error => {
                console.error('启动错误:', error);
                alert('启动失败: ' + error);
            });
        }

        function stopStreaming() {
            fetch('/stop', {method: 'POST'})
            .then(response => response.json())
            .then(data => {
                console.log('流处理已停止');
            })
            .catch(error => {
                console.error('停止错误:', error);
            });
        }

        function updateStats() {
            fetch('/stats')
            .then(response => response.json())
            .then(data => updateStatsDisplay(data))
            .catch(error => console.error('获取统计信息失败:', error));
        }

        function updateStatsDisplay(stats) {
            const statsContent = document.getElementById('statsContent');
            statsContent.innerHTML = `
                <p>总帧数: ${stats.total_frames || 0}</p>
                <p>总检测数: ${stats.total_detections || 0}</p>
                <p>总跟踪数: ${stats.total_tracks || 0}</p>
                <p>FPS: ${stats.fps ? stats.fps.toFixed(2) : 0}</p>
                <p>运行时间: ${stats.start_time ? Math.floor((Date.now()/1000 - stats.start_time)) : 0}秒</p>
            `;
        }

        window.onload = connectWebSocket;
    </script>
</body>
</html>
"""
