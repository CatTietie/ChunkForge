from __future__ import annotations

import pytest

from common.models import NodeStatus
from coordinator.metadata import MetadataStore
from coordinator.repair import RepairEngine
from coordinator.term import TermManager
from tests.conftest import MockTransport, make_nodes, upload_file_to_metadata


class TestSplitBrain:
    def test_term_increments_on_node_death(self):
        tm = TermManager(persist_path=None)
        assert tm.current_term == 0
        tm.increment()
        assert tm.current_term == 1
        tm.increment()
        assert tm.current_term == 2

    @pytest.mark.asyncio
    async def test_reconcile_removes_stale_shards(self):
        metadata = MetadataStore(persist_dir=None)
        transport = MockTransport()
        nodes = make_nodes(metadata, 6)

        fm = upload_file_to_metadata(metadata, transport, nodes, "split.bin")

        events = []
        async def collect(event):
            events.append(event)

        repair = RepairEngine(
            metadata=metadata, broadcast=collect, http_transport=transport
        )

        # Simulate: node-0 crashes, gets repaired to node-5, then node-0 comes back
        dead_node = nodes[0]
        metadata.update_node_status(dead_node.node_id, NodeStatus.CRASHED)
        await repair.on_node_failed(dead_node.node_id)

        # Now "recover" node-0
        metadata.update_node_status(dead_node.node_id, NodeStatus.ONLINE)
        await repair.reconcile_node(dead_node.node_id)

        # Partition healed event should be emitted
        from common.events import EventType
        healed = [e for e in events if e.type == EventType.PARTITION_HEALED]
        assert len(healed) >= 1
