from __future__ import annotations

import asyncio

import pytest

from common.events import EventType
from common.models import FileStatus, NodeStatus
from coordinator.metadata import MetadataStore
from coordinator.repair import RepairEngine
from tests.conftest import MockTransport, make_nodes, upload_file_to_metadata


class TestNodeFailureRepair:
    @pytest.mark.asyncio
    async def test_repair_after_single_node_failure(self):
        metadata = MetadataStore(persist_dir=None)
        transport = MockTransport()
        nodes = make_nodes(metadata, 6)

        fm = upload_file_to_metadata(metadata, transport, nodes, "repair-test.bin")

        events = []
        async def collect(event):
            events.append(event)

        repair = RepairEngine(
            metadata=metadata, broadcast=collect, http_transport=transport
        )

        # Crash node-0
        dead_node = nodes[0]
        metadata.update_node_status(dead_node.node_id, NodeStatus.CRASHED)
        await repair.on_node_failed(dead_node.node_id)

        # File should be healthy again
        updated = metadata.get_file(fm.file_id)
        assert updated.status == FileStatus.HEALTHY

        # Repair events should be emitted
        repair_started = [e for e in events if e.type == EventType.REPAIR_STARTED]
        repair_completed = [e for e in events if e.type == EventType.REPAIR_COMPLETED]
        assert len(repair_started) >= 1
        assert len(repair_completed) >= 1

    @pytest.mark.asyncio
    async def test_repair_impossible_with_too_many_failures(self):
        metadata = MetadataStore(persist_dir=None)
        transport = MockTransport()
        nodes = make_nodes(metadata, 6)

        fm = upload_file_to_metadata(metadata, transport, nodes, "lost-test.bin")

        events = []
        async def collect(event):
            events.append(event)

        repair = RepairEngine(
            metadata=metadata, broadcast=collect, http_transport=transport
        )

        # Crash 3 nodes (exceeds m=2 tolerance)
        for node in nodes[:3]:
            metadata.update_node_status(node.node_id, NodeStatus.CRASHED)
            # Remove shards from transport for crashed nodes
            for file_id, shard in metadata.get_shards_on_node(node.node_id):
                key = (node.address, shard.shard_id)
                transport.shards.pop(key, None)

        await repair.on_node_failed(nodes[0].node_id)

        updated = metadata.get_file(fm.file_id)
        assert updated.status in (FileStatus.LOST, FileStatus.DEGRADED)

    @pytest.mark.asyncio
    async def test_is_active_during_repair(self):
        metadata = MetadataStore(persist_dir=None)
        transport = MockTransport()
        nodes = make_nodes(metadata, 6)

        repair = RepairEngine(
            metadata=metadata, broadcast=None, http_transport=transport
        )
        assert not repair.is_active

        # Simulate active repair
        repair._active_tasks["task-1"] = None
        assert repair.is_active
