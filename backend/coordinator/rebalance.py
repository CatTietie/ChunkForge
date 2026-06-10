from __future__ import annotations

import asyncio
import hashlib
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable

import httpx

from common.config import settings
from common.events import Event, EventType
from common.models import NodeStatus
from coordinator.metadata import MetadataStore
from coordinator.repair import RepairEngine

logger = logging.getLogger(__name__)


class RebalanceState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass
class MigrationPlan:
    file_id: str
    shard_index: int
    shard_id: str
    source_node_id: str
    target_node_id: str
    checksum: str


class RebalanceEngine:
    def __init__(
        self,
        metadata: MetadataStore,
        repair_engine: RepairEngine,
        broadcast: Callable[[Event], Awaitable[Any]] | None = None,
        http_transport=None,
        max_migrations_per_round: int = 4,
        deviation_threshold: int = 2,
        periodic_interval_s: float = 60.0,
        max_concurrency: int = 4,
    ):
        self.metadata = metadata
        self.repair_engine = repair_engine
        self.broadcast = broadcast or self._noop_broadcast
        self.http_transport = http_transport
        self.max_migrations_per_round = max_migrations_per_round
        self.deviation_threshold = deviation_threshold
        self.periodic_interval_s = periodic_interval_s
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._state = RebalanceState.IDLE
        self._task: asyncio.Task | None = None
        self._running = False
        self._trigger_event = asyncio.Event()

    @staticmethod
    async def _noop_broadcast(event: Event):
        pass

    @property
    def state(self) -> RebalanceState:
        return self._state

    @asynccontextmanager
    async def _get_client(self):
        if self.http_transport:
            async with httpx.AsyncClient(transport=self.http_transport, timeout=30.0) as client:
                yield client
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                yield client

    def start(self):
        self._running = True
        self._task = asyncio.create_task(self._rebalance_loop())
        logger.info("RebalanceEngine started")

    def stop(self):
        self._running = False
        self._trigger_event.set()
        if self._task:
            self._task.cancel()

    def trigger(self, reason: str):
        logger.info(f"Rebalance triggered: {reason}")
        self._trigger_event.set()

    def get_status(self) -> dict[str, Any]:
        online = self.metadata.get_online_nodes()
        counts = {n.node_id: n.shard_count for n in online} if online else {}
        deviation = (max(counts.values()) - min(counts.values())) if counts else 0
        return {
            "state": self._state.value,
            "deviation": deviation,
            "threshold": self.deviation_threshold,
            "node_shard_counts": counts,
        }

    async def _rebalance_loop(self):
        while self._running:
            try:
                await asyncio.wait_for(
                    self._trigger_event.wait(),
                    timeout=self.periodic_interval_s,
                )
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                return

            self._trigger_event.clear()

            if not self._running:
                return

            if self._should_pause():
                if self._state != RebalanceState.PAUSED:
                    self._state = RebalanceState.PAUSED
                    await self.broadcast(Event(
                        type=EventType.REBALANCE_PAUSED,
                        payload={"reason": "repair_active_or_cluster_unstable"},
                    ))
                continue

            if not self._is_imbalanced():
                if self._state == RebalanceState.PAUSED:
                    self._state = RebalanceState.IDLE
                continue

            await self._run_round()

    def _should_pause(self) -> bool:
        if self.repair_engine.is_active:
            return True
        online_count = len(self.metadata.get_online_nodes())
        if online_count < settings.RS_K + settings.RS_M:
            return True
        return False

    def _is_imbalanced(self) -> bool:
        online = self.metadata.get_online_nodes()
        if len(online) < 2:
            return False
        counts = [n.shard_count for n in online]
        return max(counts) - min(counts) > self.deviation_threshold

    def _plan_migrations(self) -> list[MigrationPlan]:
        online = self.metadata.get_online_nodes()
        if len(online) < 2:
            return []

        counts = {n.node_id: n.shard_count for n in online}
        total = sum(counts.values())
        n_nodes = len(counts)
        if total == 0:
            return []

        floor_avg = total // n_nodes
        ceil_avg = floor_avg + (1 if total % n_nodes else 0)
        n_ceil = total - floor_avg * n_nodes

        # Assign each node a target: n_ceil nodes get ceil_avg, rest get floor_avg
        # Nodes already at or above ceil keep their excess as "donor budget"
        sorted_by_count = sorted(counts.items(), key=lambda x: -x[1])
        target_for: dict[str, int] = {}
        ceil_slots = n_ceil
        for nid, c in sorted_by_count:
            if ceil_slots > 0 and c >= ceil_avg:
                target_for[nid] = ceil_avg
                ceil_slots -= 1
            elif ceil_slots > 0 and c > floor_avg:
                target_for[nid] = ceil_avg
                ceil_slots -= 1
            else:
                target_for[nid] = floor_avg
        # Fill remaining ceil slots for underloaded nodes
        if ceil_slots > 0:
            for nid, c in sorted(counts.items(), key=lambda x: x[1]):
                if target_for.get(nid) == floor_avg and ceil_slots > 0:
                    target_for[nid] = ceil_avg
                    ceil_slots -= 1

        donors = sorted(
            [(nid, c - target_for[nid]) for nid, c in counts.items() if c > target_for[nid]],
            key=lambda x: -x[1],
        )
        receivers = sorted(
            [(nid, target_for[nid] - c) for nid, c in counts.items() if c < target_for[nid]],
            key=lambda x: -x[1],
        )

        if not donors or not receivers:
            return []

        plans: list[MigrationPlan] = []
        donor_budget = {nid: excess for nid, excess in donors}
        receiver_budget = {nid: deficit for nid, deficit in receivers}
        planned_shards: set[str] = set()

        for receiver_id, _ in receivers:
            if receiver_budget[receiver_id] <= 0:
                continue
            if len(plans) >= self.max_migrations_per_round:
                break

            for donor_id, _ in donors:
                if donor_budget[donor_id] <= 0:
                    continue
                if receiver_budget[receiver_id] <= 0:
                    break
                if len(plans) >= self.max_migrations_per_round:
                    break

                shards_on_donor = self.metadata.get_shards_on_node(donor_id)
                for file_id, shard in shards_on_donor:
                    if shard.shard_id in planned_shards:
                        continue
                    if donor_budget[donor_id] <= 0:
                        break
                    if receiver_budget[receiver_id] <= 0:
                        break
                    if len(plans) >= self.max_migrations_per_round:
                        break

                    file_meta = self.metadata.get_file(file_id)
                    if file_meta is None:
                        continue

                    nodes_holding_file = {s.node_id for s in file_meta.shards}
                    if receiver_id in nodes_holding_file:
                        continue

                    plans.append(MigrationPlan(
                        file_id=file_id,
                        shard_index=shard.shard_index,
                        shard_id=shard.shard_id,
                        source_node_id=donor_id,
                        target_node_id=receiver_id,
                        checksum=shard.checksum_sha256,
                    ))
                    planned_shards.add(shard.shard_id)
                    donor_budget[donor_id] -= 1
                    receiver_budget[receiver_id] -= 1
                    break

        return plans

    async def _run_round(self):
        self._state = RebalanceState.RUNNING
        plans = self._plan_migrations()
        if not plans:
            self._state = RebalanceState.IDLE
            return

        await self.broadcast(Event(
            type=EventType.REBALANCE_STARTED,
            payload={"migrations_planned": len(plans)},
        ))

        results = await asyncio.gather(
            *[self._execute_migration(p) for p in plans],
            return_exceptions=True,
        )

        succeeded = sum(1 for r in results if r is True)
        failed = len(results) - succeeded

        self._state = RebalanceState.IDLE

        await self.broadcast(Event(
            type=EventType.REBALANCE_COMPLETED,
            payload={"succeeded": succeeded, "failed": failed},
        ))

        logger.info(f"Rebalance round done: {succeeded} succeeded, {failed} failed")

    async def _execute_migration(self, plan: MigrationPlan) -> bool:
        async with self._semaphore:
            if self._should_pause():
                return False

            try:
                async with self._get_client() as client:
                    source_node = self.metadata.get_node(plan.source_node_id)
                    if not source_node or source_node.status != NodeStatus.ONLINE:
                        logger.warning(
                            f"Source node {plan.source_node_id} unavailable, skipping"
                        )
                        return False

                    resp = await client.get(
                        f"{source_node.address}/shards/{plan.shard_id}"
                    )
                    if resp.status_code != 200:
                        logger.warning(
                            f"Failed to read shard {plan.shard_id} from "
                            f"{plan.source_node_id}: {resp.status_code}"
                        )
                        return False

                    shard_data = resp.content
                    actual_checksum = hashlib.sha256(shard_data).hexdigest()
                    if actual_checksum != plan.checksum:
                        logger.warning(
                            f"Checksum mismatch for {plan.shard_id} on "
                            f"{plan.source_node_id}"
                        )
                        return False

                    target_node = self.metadata.get_node(plan.target_node_id)
                    if not target_node or target_node.status != NodeStatus.ONLINE:
                        logger.warning(
                            f"Target node {plan.target_node_id} unavailable, skipping"
                        )
                        return False

                    # Step 1: Write to target
                    resp = await client.put(
                        f"{target_node.address}/shards/{plan.shard_id}",
                        content=shard_data,
                        headers={
                            "X-File-Id": plan.file_id,
                            "X-Shard-Index": str(plan.shard_index),
                            "X-Checksum-SHA256": plan.checksum,
                        },
                    )
                    if resp.status_code != 201:
                        logger.warning(
                            f"Failed to write shard {plan.shard_id} to "
                            f"{plan.target_node_id}: {resp.status_code}"
                        )
                        return False

                    # Step 2: Delete from source (shard now on both nodes)
                    del_resp = await client.delete(
                        f"{source_node.address}/shards/{plan.shard_id}"
                    )
                    if del_resp.status_code != 200:
                        # Rollback: remove from target to avoid orphan
                        await client.delete(
                            f"{target_node.address}/shards/{plan.shard_id}"
                        )
                        logger.warning(
                            f"Delete from source failed for {plan.shard_id}, "
                            f"rolled back target write"
                        )
                        return False

                    # Step 3: Both I/O confirmed — now update metadata
                    self.metadata.update_shard_location(
                        plan.file_id, plan.shard_index, plan.target_node_id
                    )
                    source_node.shard_count = max(0, source_node.shard_count - 1)
                    target_node.shard_count += 1

                    await self.broadcast(Event(
                        type=EventType.REBALANCE_PROGRESS,
                        payload={
                            "file_id": plan.file_id,
                            "shard_index": plan.shard_index,
                            "from_node": plan.source_node_id,
                            "to_node": plan.target_node_id,
                        },
                    ))

                    logger.info(
                        f"Migrated shard {plan.shard_id}: "
                        f"{plan.source_node_id} -> {plan.target_node_id}"
                    )
                    return True

            except httpx.RequestError as e:
                logger.warning(f"Migration failed for {plan.shard_id}: {e}")
                return False
