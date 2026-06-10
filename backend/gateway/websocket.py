from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect

from common.events import Event

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.info(f"WebSocket connected, total: {len(self._connections)}")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections = [c for c in self._connections if c is not ws]

    async def broadcast(self, event: Event):
        message = event.model_dump_json()
        dead: list[WebSocket] = []
        async with self._lock:
            for conn in self._connections:
                try:
                    await conn.send_text(message)
                except Exception:
                    dead.append(conn)
            for d in dead:
                self._connections = [c for c in self._connections if c is not d]

    async def broadcast_dict(self, data: dict):
        import json
        message = json.dumps(data, default=str)
        dead: list[WebSocket] = []
        async with self._lock:
            for conn in self._connections:
                try:
                    await conn.send_text(message)
                except Exception:
                    dead.append(conn)
            for d in dead:
                self._connections = [c for c in self._connections if c is not d]
