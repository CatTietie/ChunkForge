from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


class HeartbeatSender:
    def __init__(
        self,
        node_id: str,
        coordinator_url: str,
        storage,
        interval_ms: int = 1000,
    ):
        self.node_id = node_id
        self.coordinator_url = coordinator_url
        self.storage = storage
        self._interval_s = interval_ms / 1000.0
        self._task: asyncio.Task | None = None
        self._running = False
        self.current_term = 0

    def start(self):
        self._running = True
        self._task = asyncio.create_task(self._send_loop())
        logger.info(f"HeartbeatSender started for {self.node_id}")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _send_loop(self):
        while self._running:
            try:
                await self._send_heartbeat()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
                await asyncio.sleep(5)
                continue
            await asyncio.sleep(self._interval_s)

    async def _send_heartbeat(self):
        payload = {
            "node_id": self.node_id,
            "term": self.current_term,
            "shard_count": self.storage.get_shard_count(),
            "disk_usage_bytes": self.storage.get_disk_usage(),
            "timestamp": datetime.utcnow().isoformat(),
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{self.coordinator_url}/internal/heartbeat",
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                server_term = data.get("current_term", 0)
                if server_term > self.current_term:
                    self.current_term = server_term
                    logger.info(f"Updated local term to {self.current_term}")
