import os
import threading
import time
from collections import OrderedDict
from uuid import uuid4

class TTLFrameRegistry:
    """
    TTL帧注册表，支持事件帧的唯一ID注册、自动过期清理和最大容量限制。
    """
    def __init__(self, ttl_seconds=600, max_size=500):
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._lock = threading.Lock()
        self._registry = OrderedDict()  # event_id -> (path, timestamp)

    def register(self, event_id, path):
        now = time.time()
        with self._lock:
            self._registry[event_id] = (path, now)
            self._cleanup()

    def get(self, event_id):
        with self._lock:
            item = self._registry.get(event_id)
            if not item:
                return None
            path, ts = item
            # 检查是否过期
            if time.time() - ts > self.ttl:
                del self._registry[event_id]
                return None
            return path

    def _cleanup(self):
        # 清理过期和超量
        now = time.time()
        # 先清理过期
        expired = [k for k, (_, ts) in self._registry.items() if now - ts > self.ttl]
        for k in expired:
            del self._registry[k]
        # 再清理超量
        while len(self._registry) > self.max_size:
            self._registry.popitem(last=False)

    def all_event_ids(self):
        with self._lock:
            return list(self._registry.keys())

    def all_items(self):
        with self._lock:
            return list(self._registry.items())

# 单例
frame_registry = TTLFrameRegistry()
