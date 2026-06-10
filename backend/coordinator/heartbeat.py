from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable

from common.config import settings
from common.models import NodeStatus
from coordinator.metadata import MetadataStore
from coordinator.term import TermManager

logger = logging.getLogger(__name__)


class HeartbeatMonitor:
    def __init__(
        self,
        metadata: MetadataStore,
        term_manager: TermManager,
        on_node_dead: Callable[[str], Awaitable] | None = None,
    ):
        self.metadata = metadata
        self.term_manager = term_manager
        self.on_node_dead = on_node_dead
        self._timeout_s = settings.HEARTBEAT_TIMEOUT_MS / 1000.0
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self):
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("HeartbeatMonitor started")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _monitor_loop(self):
        check_interval = self._timeout_s / 2
        while self._running:
            try:
                await asyncio.sleep(check_interval)
                await self._check_nodes()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"HeartbeatMonitor error: {e}")

    async def _check_nodes(self):
        now = datetime.utcnow()
        for node in self.metadata.get_all_nodes():
            if node.status != NodeStatus.ONLINE:
                continue
            if not node.last_heartbeat:
                continue
            elapsed = (now - node.last_heartbeat).total_seconds()
            if elapsed > self._timeout_s:
                logger.warning(
                    f"Node {node.node_id} heartbeat timeout "
                    f"({elapsed:.1f}s > {self._timeout_s}s)"
                )
                self.metadata.update_node_status(node.node_id, NodeStatus.CRASHED)
                self.term_manager.increment()
                if self.on_node_dead:
                    await self.on_node_dead(node.node_id)
