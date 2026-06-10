from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Awaitable, Callable

import httpx

from common.config import settings
from common.erasure import ErasureCoder, Fragment
from common.events import Event, EventType
from common.models import FileStatus, NodeStatus, RepairState, RepairTask, ShardRole
from coordinator.metadata import MetadataStore

logger = logging.getLogger(__name__)


class RepairEngine:
    def __init__(
        self,
        metadata: MetadataStore,
        term_manager=None,
        broadcast: Callable[[Event], Awaitable[Any]] | None = None,
        http_transport=None,
    ):
        self.metadata = metadata
        self.term_manager = term_manager
        self.broadcast = broadcast or self._noop_broadcast
        self.http_transport = http_transport
        self._active_tasks: dict[str, RepairTask] = {}
        self._semaphore = asyncio.Semaphore(settings.REPAIR_CONCURRENCY)
        self._coder = ErasureCoder(k=settings.RS_K, m=settings.RS_M)

    @staticmethod
    async def _noop_broadcast(event: Event):
        pass

    @property
    def is_active(self) -> bool:
        return len(self._active_tasks) > 0

    @asynccontextmanager
    async def _get_client(self):
        if self.http_transport:
            async with httpx.AsyncClient(transport=self.http_transport, timeout=30.0) as client:
                yield client
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                yield client

    async def on_node_failed(self, node_id: str):
        shards_on_node = self.metadata.get_shards_on_node(node_id)
        if not shards_on_node:
            logger.info(f"No shards on failed node {node_id}")
            return

        affected_files = set(file_id for file_id, _ in shards_on_node)
        logger.warning(f"Node {node_id} failed, {len(affected_files)} files affected")

        await self.broadcast(Event(
            type=EventType.REPAIR_STARTED,
            payload={"node_id": node_id, "affected_files": len(affected_files)},
        ))

        tasks = [self._repair_file(file_id, node_id) for file_id in affected_files]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _repair_file(self, file_id: str, dead_node_id: str, retry_count: int = 0):
        file_meta = self.metadata.get_file(file_id)
        if not file_meta:
            return

        missing_indices = [
            s.shard_index for s in file_meta.shards if s.node_id == dead_node_id
        ]
        if not missing_indices:
            return

        self.metadata.update_file_status(file_id, FileStatus.REPAIRING)

        surviving_shards = [s for s in file_meta.shards if s.node_id != dead_node_id]
        if len(surviving_shards) < settings.RS_K:
            self.metadata.update_file_status(file_id, FileStatus.LOST)
            await self.broadcast(Event(
                type=EventType.REPAIR_FAILED,
                payload={"file_id": file_id, "reason": "insufficient_shards"},
            ))
            return

        nodes_holding_shards = {s.node_id for s in file_meta.shards}
        target_node = self.metadata.get_node_with_least_shards(
            exclude=nodes_holding_shards | {dead_node_id}
        )
        if not target_node:
            target_node = self.metadata.get_node_with_least_shards(exclude={dead_node_id})
        if not target_node:
            self.metadata.update_file_status(file_id, FileStatus.DEGRADED)
            return

        task_id = str(uuid.uuid4())
        repair_task = RepairTask(
            task_id=task_id,
            file_id=file_id,
            missing_shard_indices=missing_indices,
            target_node_id=target_node.node_id,
            state=RepairState.RECONSTRUCTING,
            started_at=datetime.utcnow(),
            retry_count=retry_count,
        )
        self._active_tasks[task_id] = repair_task

        try:
            await self._reconstruct_and_write(file_meta, repair_task, surviving_shards)
            repair_task.state = RepairState.COMPLETED
            repair_task.completed_at = datetime.utcnow()
            self.metadata.update_file_status(file_id, FileStatus.HEALTHY)
            await self.broadcast(Event(
                type=EventType.REPAIR_COMPLETED,
                payload={"file_id": file_id, "task_id": task_id},
            ))
        except Exception as e:
            repair_task.state = RepairState.FAILED
            repair_task.error = str(e)
            if repair_task.retry_count < settings.REPAIR_MAX_RETRIES:
                del self._active_tasks[task_id]
                await self._repair_file(file_id, dead_node_id, retry_count=repair_task.retry_count + 1)
                return
            self.metadata.update_file_status(file_id, FileStatus.DEGRADED)
            await self.broadcast(Event(
                type=EventType.REPAIR_FAILED,
                payload={"file_id": file_id, "error": str(e)},
            ))
        finally:
            self._active_tasks.pop(task_id, None)

    async def _reconstruct_and_write(self, file_meta, repair_task: RepairTask, surviving_shards):
        fragments: list[Fragment] = []

        async with self._get_client() as client:
            for shard in surviving_shards:
                if len(fragments) >= file_meta.k:
                    break
                async with self._semaphore:
                    node = self.metadata.get_node(shard.node_id)
                    if not node or node.status != NodeStatus.ONLINE:
                        continue
                    resp = await client.get(f"{node.address}/shards/{shard.shard_id}")
                    if resp.status_code == 200:
                        fragments.append(Fragment(
                            index=shard.shard_index,
                            data=resp.content,
                            checksum=shard.checksum_sha256,
                        ))

            if len(fragments) < file_meta.k:
                raise RuntimeError(
                    f"Could only fetch {len(fragments)}/{file_meta.k} fragments"
                )

            target_node = self.metadata.get_node(repair_task.target_node_id)
            if not target_node:
                raise RuntimeError(f"Target node {repair_task.target_node_id} not found")

            for missing_idx in repair_task.missing_shard_indices:
                reconstructed = self._coder.reconstruct_fragment(fragments, missing_idx)
                shard_id = f"{file_meta.file_id}_{missing_idx}"
                role = "data" if missing_idx < file_meta.k else "parity"

                resp = await client.put(
                    f"{target_node.address}/shards/{shard_id}",
                    content=reconstructed.data,
                    headers={
                        "X-File-Id": file_meta.file_id,
                        "X-Shard-Index": str(missing_idx),
                        "X-Checksum-SHA256": reconstructed.checksum,
                        "X-Reed-Solomon-Role": role,
                    },
                )
                if resp.status_code != 201:
                    raise RuntimeError(
                        f"Failed to write repaired shard to {target_node.node_id}"
                    )

                self.metadata.update_shard_location(
                    file_meta.file_id, missing_idx, target_node.node_id
                )
                target_node.shard_count += 1

                await self.broadcast(Event(
                    type=EventType.REPAIR_PROGRESS,
                    payload={
                        "file_id": file_meta.file_id,
                        "shard_index": missing_idx,
                        "target_node": target_node.node_id,
                    },
                ))

    async def reconcile_node(self, node_id: str):
        shards_on_node = self.metadata.get_shards_on_node(node_id)
        node = self.metadata.get_node(node_id)
        if not node:
            return

        async with self._get_client() as client:
            for file_id, shard in shards_on_node:
                file_meta = self.metadata.get_file(file_id)
                if not file_meta:
                    continue
                current_shard = next(
                    (s for s in file_meta.shards if s.shard_index == shard.shard_index),
                    None,
                )
                if current_shard and current_shard.node_id != node_id:
                    try:
                        await client.delete(
                            f"{node.address}/shards/{shard.shard_id}"
                        )
                    except httpx.RequestError:
                        pass

        await self.broadcast(Event(
            type=EventType.PARTITION_HEALED,
            payload={"node_id": node_id},
        ))
