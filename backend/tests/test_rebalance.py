from __future__ import annotations

import asyncio

import httpx
import pytest

from common.config import settings
from common.events import EventType
from common.models import NodeStatus
from coordinator.metadata import MetadataStore
from coordinator.rebalance import RebalanceEngine, RebalanceState
from coordinator.repair import RepairEngine
from tests.conftest import MockTransport, make_nodes, upload_file_to_metadata


@pytest.fixture
def cluster_6_nodes():
    metadata = MetadataStore(persist_dir=None)
    transport = MockTransport()
    nodes = make_nodes(metadata, 6)
    return metadata, transport, nodes


@pytest.fixture
def cluster_with_files(cluster_6_nodes):
    metadata, transport, nodes = cluster_6_nodes
    files = []
    for i in range(10):
        fm = upload_file_to_metadata(metadata, transport, nodes, f"file-{i}.bin")
        files.append(fm)
    return metadata, transport, nodes, files


class TestRebalanceImbalanceDetection:
    def test_balanced_cluster_not_imbalanced(self, cluster_6_nodes):
        metadata, transport, nodes = cluster_6_nodes
        # All nodes have 0 shards
        repair = RepairEngine(metadata=metadata, broadcast=None, http_transport=transport)
        engine = RebalanceEngine(metadata=metadata, repair_engine=repair, deviation_threshold=2)
        assert not engine._is_imbalanced()

    def test_imbalanced_cluster_detected(self, cluster_with_files):
        metadata, transport, nodes, files = cluster_with_files
        # After uploading 10 files with 6 shards each to 6 nodes, distribution
        # depends on the least-shards algorithm. Force imbalance:
        nodes[0].shard_count = 20
        nodes[5].shard_count = 0
        repair = RepairEngine(metadata=metadata, broadcast=None, http_transport=transport)
        engine = RebalanceEngine(metadata=metadata, repair_engine=repair, deviation_threshold=2)
        assert engine._is_imbalanced()

    def test_threshold_boundary(self, cluster_6_nodes):
        metadata, transport, nodes = cluster_6_nodes
        # Set all nodes to same base, then adjust two
        for n in nodes:
            n.shard_count = 5
        nodes[0].shard_count = 7
        nodes[5].shard_count = 5
        # deviation = 2, threshold = 2, not > 2
        repair = RepairEngine(metadata=metadata, broadcast=None, http_transport=transport)
        engine = RebalanceEngine(metadata=metadata, repair_engine=repair, deviation_threshold=2)
        assert not engine._is_imbalanced()

        nodes[0].shard_count = 8
        # deviation = 3, > 2
        assert engine._is_imbalanced()


class TestRebalancePause:
    def test_pause_when_repair_active(self, cluster_6_nodes):
        metadata, transport, nodes = cluster_6_nodes
        repair = RepairEngine(metadata=metadata, broadcast=None, http_transport=transport)
        engine = RebalanceEngine(metadata=metadata, repair_engine=repair)
        # Simulate active repair
        repair._active_tasks["fake"] = None
        assert engine._should_pause()

    def test_pause_when_insufficient_nodes(self, cluster_6_nodes):
        metadata, transport, nodes = cluster_6_nodes
        repair = RepairEngine(metadata=metadata, broadcast=None, http_transport=transport)
        engine = RebalanceEngine(metadata=metadata, repair_engine=repair)
        # Take nodes offline until < k+m
        for node in nodes[:2]:
            metadata.update_node_status(node.node_id, NodeStatus.CRASHED)
        assert engine._should_pause()

    def test_no_pause_when_healthy(self, cluster_6_nodes):
        metadata, transport, nodes = cluster_6_nodes
        repair = RepairEngine(metadata=metadata, broadcast=None, http_transport=transport)
        engine = RebalanceEngine(metadata=metadata, repair_engine=repair)
        assert not engine._should_pause()


class TestMigrationPlanning:
    def test_plan_respects_max_migrations(self, cluster_with_files):
        metadata, transport, nodes, files = cluster_with_files
        # Force extreme imbalance
        nodes[0].shard_count = 30
        nodes[5].shard_count = 0
        repair = RepairEngine(metadata=metadata, broadcast=None, http_transport=transport)
        engine = RebalanceEngine(
            metadata=metadata, repair_engine=repair, max_migrations_per_round=3
        )
        plans = engine._plan_migrations()
        assert len(plans) <= 3

    def test_plan_avoids_same_file_on_same_node(self, cluster_with_files):
        metadata, transport, nodes, files = cluster_with_files
        repair = RepairEngine(metadata=metadata, broadcast=None, http_transport=transport)
        engine = RebalanceEngine(metadata=metadata, repair_engine=repair)
        plans = engine._plan_migrations()
        for plan in plans:
            fm = metadata.get_file(plan.file_id)
            other_nodes = {s.node_id for s in fm.shards if s.shard_index != plan.shard_index}
            assert plan.target_node_id not in other_nodes

    def test_empty_plan_when_balanced(self, cluster_6_nodes):
        metadata, transport, nodes = cluster_6_nodes
        repair = RepairEngine(metadata=metadata, broadcast=None, http_transport=transport)
        engine = RebalanceEngine(metadata=metadata, repair_engine=repair)
        plans = engine._plan_migrations()
        assert len(plans) == 0


class TestMigrationExecution:
    @pytest.mark.asyncio
    async def test_successful_migration(self, cluster_with_files):
        metadata, transport, nodes, files = cluster_with_files
        # Add 2 new empty nodes
        for i in range(6, 8):
            from common.models import NodeInfo
            new_node = NodeInfo(
                node_id=f"node-{i}",
                address=f"http://node-{i}:9000",
                status=NodeStatus.ONLINE,
                shard_count=0,
                capacity_bytes=1073741824,
            )
            metadata.register_node(new_node)

        events = []
        async def collect(event):
            events.append(event)

        repair = RepairEngine(metadata=metadata, broadcast=collect, http_transport=transport)
        engine = RebalanceEngine(
            metadata=metadata,
            repair_engine=repair,
            broadcast=collect,
            http_transport=transport,
            max_migrations_per_round=4,
            deviation_threshold=2,
        )

        await engine._run_round()

        progress_events = [e for e in events if e.type == EventType.REBALANCE_PROGRESS]
        assert len(progress_events) > 0

        completed = [e for e in events if e.type == EventType.REBALANCE_COMPLETED]
        assert len(completed) == 1
        assert completed[0].payload["succeeded"] > 0

    @pytest.mark.asyncio
    async def test_full_rebalance_acceptance(self):
        """Acceptance test: 8 nodes, upload 10 files to 6 → add 2 → deviation ≤ 2.

        Uses 8 initial nodes with 2 starting offline to simulate the spec scenario.
        With 8 nodes and 6 shards/file, deviation ≤ 2 is achievable when files can
        spread across enough targets.
        """
        metadata = MetadataStore(persist_dir=None)
        transport = MockTransport()
        # Start with 8 nodes but only 6 online during uploads
        nodes = make_nodes(metadata, 8)
        metadata.update_node_status("node-6", NodeStatus.OFFLINE)
        metadata.update_node_status("node-7", NodeStatus.OFFLINE)

        for i in range(10):
            upload_file_to_metadata(metadata, transport, nodes[:6], f"file-{i}.bin")

        # Bring new nodes online (simulating adding nodes)
        metadata.update_node_status("node-6", NodeStatus.ONLINE)
        metadata.update_node_status("node-7", NodeStatus.ONLINE)
        nodes[6].shard_count = 0
        nodes[7].shard_count = 0

        events = []
        async def collect(event):
            events.append(event)

        repair = RepairEngine(metadata=metadata, broadcast=collect, http_transport=transport)
        engine = RebalanceEngine(
            metadata=metadata,
            repair_engine=repair,
            broadcast=collect,
            http_transport=transport,
            max_migrations_per_round=10,
            deviation_threshold=2,
        )

        # Run multiple rounds until balanced
        for _ in range(30):
            if not engine._is_imbalanced():
                break
            await engine._run_round()

        online = metadata.get_online_nodes()
        counts = [n.shard_count for n in online]
        deviation = max(counts) - min(counts)
        assert deviation <= 2, f"Deviation {deviation} exceeds threshold. Counts: {counts}"

        # Verify no data loss: all 60 shards still exist in transport
        total_shards = sum(len(f.shards) for f in metadata.get_all_files())
        assert total_shards == 60

    @pytest.mark.asyncio
    async def test_source_node_crash_skips_shard(self, cluster_with_files):
        metadata, transport, nodes, files = cluster_with_files

        # Add new node
        from common.models import NodeInfo
        new_node = NodeInfo(
            node_id="node-6",
            address="http://node-6:9000",
            status=NodeStatus.ONLINE,
            shard_count=0,
            capacity_bytes=1073741824,
        )
        metadata.register_node(new_node)

        events = []
        async def collect(event):
            events.append(event)

        repair = RepairEngine(metadata=metadata, broadcast=collect, http_transport=transport)
        engine = RebalanceEngine(
            metadata=metadata,
            repair_engine=repair,
            broadcast=collect,
            http_transport=transport,
        )

        plans = engine._plan_migrations()
        if plans:
            # Crash the source node before migration
            metadata.update_node_status(plans[0].source_node_id, NodeStatus.CRASHED)
            result = await engine._execute_migration(plans[0])
            assert result is False

    @pytest.mark.asyncio
    async def test_delete_failure_rolls_back_no_orphan(self, cluster_with_files):
        """When source delete fails, target write must be rolled back."""
        metadata, transport, nodes, files = cluster_with_files

        from common.models import NodeInfo
        new_node = NodeInfo(
            node_id="node-6",
            address="http://node-6:9000",
            status=NodeStatus.ONLINE,
            shard_count=0,
            capacity_bytes=1073741824,
        )
        metadata.register_node(new_node)

        events = []
        async def collect(event):
            events.append(event)

        repair = RepairEngine(metadata=metadata, broadcast=collect, http_transport=transport)
        engine = RebalanceEngine(
            metadata=metadata,
            repair_engine=repair,
            broadcast=collect,
            http_transport=transport,
        )

        plans = engine._plan_migrations()
        assert len(plans) > 0
        plan = plans[0]

        # Remove shard from source in transport so DELETE returns 404
        source_node = metadata.get_node(plan.source_node_id)
        source_key = (source_node.address, plan.shard_id)
        shard_data = transport.shards.pop(source_key)

        # But keep it readable by re-adding for the GET (simulate: shard readable
        # but un-deletable, e.g. permission issue). We use a custom transport.
        class DeleteFailTransport(MockTransport):
            async def handle_async_request(self, request):
                url_str = str(request.url)
                if request.method == "DELETE" and plan.shard_id in url_str and source_node.address in url_str:
                    return httpx.Response(500)
                return await super().handle_async_request(request)

        fail_transport = DeleteFailTransport()
        fail_transport.shards = dict(transport.shards)
        fail_transport.shards[source_key] = shard_data

        engine_fail = RebalanceEngine(
            metadata=metadata,
            repair_engine=repair,
            broadcast=collect,
            http_transport=fail_transport,
        )

        result = await engine_fail._execute_migration(plan)
        assert result is False

        # Verify: no orphan on target (target shard rolled back)
        target_node = metadata.get_node(plan.target_node_id)
        target_key = (target_node.address, plan.shard_id)
        assert target_key not in fail_transport.shards

        # Verify: metadata unchanged (still points to source)
        file_meta = metadata.get_file(plan.file_id)
        shard_loc = next(s for s in file_meta.shards if s.shard_index == plan.shard_index)
        assert shard_loc.node_id == plan.source_node_id


class TestRebalanceGetStatus:
    def test_status_format(self, cluster_with_files):
        metadata, transport, nodes, files = cluster_with_files
        repair = RepairEngine(metadata=metadata, broadcast=None, http_transport=transport)
        engine = RebalanceEngine(metadata=metadata, repair_engine=repair)
        status = engine.get_status()
        assert "state" in status
        assert "deviation" in status
        assert "threshold" in status
        assert "node_shard_counts" in status
        assert status["state"] == "idle"


class TestRebalanceTrigger:
    def test_trigger_sets_event(self):
        metadata = MetadataStore(persist_dir=None)
        make_nodes(metadata, 6)
        repair = RepairEngine(metadata=metadata, broadcast=None)
        engine = RebalanceEngine(metadata=metadata, repair_engine=repair)
        assert not engine._trigger_event.is_set()
        engine.trigger("test")
        assert engine._trigger_event.is_set()
