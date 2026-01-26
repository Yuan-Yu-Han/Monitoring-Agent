import asyncio
import json
import logging
from typing import List, Callable
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_callbacks: List[Callable] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket连接已建立，当前连接数: {len(self.active_connections)}")
        for callback in self.connection_callbacks:
            try:
                await callback(websocket, "connect")
            except Exception as e:
                logger.error(f"连接回调执行失败: {e}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket连接已断开，当前连接数: {len(self.active_connections)}")
        for callback in self.connection_callbacks:
            try:
                asyncio.create_task(callback(websocket, "disconnect"))
            except Exception as e:
                logger.error(f"断开回调执行失败: {e}")
    
    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        message_copy = json.dumps(message, ensure_ascii=False)
        tasks = []
        dead_connections = []
        for websocket in self.active_connections:
            task = asyncio.create_task(self._send_message(websocket, message_copy))
            tasks.append((websocket, task))
        for websocket, task in tasks:
            try:
                await task
            except Exception as e:
                logger.warning(f"发送消息失败: {e}")
                dead_connections.append(websocket)
        for websocket in dead_connections:
            self.disconnect(websocket)
    
    async def _send_message(self, websocket: WebSocket, message: str):
        try:
            await websocket.send_text(message)
        except Exception as e:
            raise e
    
    def add_connection_callback(self, callback: Callable):
        self.connection_callbacks.append(callback)
