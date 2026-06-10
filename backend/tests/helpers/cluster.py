from __future__ import annotations

from tests.conftest import MockTransport, make_nodes, upload_file_to_metadata
from common.models import NodeInfo, NodeStatus
from coordinator.metadata import MetadataStore


class InternalTestCluster:
    """Helper that sets up an in-memory cluster for integration tests."""

    def __init__(self, node_count: int = 6):
        self.metadata = MetadataStore(persist_dir=None)
        self.transport = MockTransport()
        self.nodes = make_nodes(self.metadata, node_count)

    def upload_files(self, count: int = 10) -> list:
        files = []
        online = [n for n in self.nodes if n.status == NodeStatus.ONLINE]
        for i in range(count):
            fm = upload_file_to_metadata(
                self.metadata, self.transport, online, f"file-{i}.bin"
            )
            files.append(fm)
        return files

    def add_nodes(self, count: int = 2) -> list[NodeInfo]:
        new_nodes = []
        start = len(self.nodes)
        for i in range(count):
            node = NodeInfo(
                node_id=f"node-{start + i}",
                address=f"http://node-{start + i}:9000",
                status=NodeStatus.ONLINE,
                shard_count=0,
                capacity_bytes=1073741824,
            )
            self.metadata.register_node(node)
            self.nodes.append(node)
            new_nodes.append(node)
        return new_nodes
