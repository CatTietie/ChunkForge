from __future__ import annotations

import asyncio
import hashlib
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from common.config import settings
from common.erasure import ErasureCoder
from common.models import FileMeta, NodeInfo, NodeStatus, ShardLocation, ShardRole
from coordinator.metadata import MetadataStore
from coordinator.repair import RepairEngine
from coordinator.term import TermManager
from gateway.websocket import WebSocketManager


class MockTransport(httpx.AsyncBaseTransport):
    """Mock transport that simulates storage nodes in-memory.

    Shards are keyed by (node_address, shard_id) to correctly model
    separate storage per node.
    """

    def __init__(self):
        self.shards: dict[tuple[str, str], bytes] = {}

    def _node_key(self, url: str, shard_id: str) -> tuple[str, str]:
        # Extract host:port from URL like http://node-0:9000/shards/xxx
        parts = url.split("/shards/")[0]
        return (parts, shard_id)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        host_part = url_str.split("/shards/")[0] if "/shards/" in url_str else url_str

        if request.method == "PUT" and "/shards/" in url_str:
            shard_id = url_str.split("/shards/")[1]
            data = request.content
            if isinstance(data, bytes):
                self.shards[(host_part, shard_id)] = data
            else:
                self.shards[(host_part, shard_id)] = b""
            return httpx.Response(
                201,
                json={"shard_id": shard_id, "stored": True, "checksum_verified": True, "size_bytes": len(self.shards[(host_part, shard_id)])},
            )
        elif request.method == "GET" and "/shards/" in url_str:
            shard_id = url_str.split("/shards/")[1]
            key = (host_part, shard_id)
            if key in self.shards:
                data = self.shards[key]
                import hashlib
                checksum = hashlib.sha256(data).hexdigest()
                return httpx.Response(
                    200,
                    content=data,
                    headers={"X-Checksum-SHA256": checksum, "X-Shard-Size": str(len(data))},
                )
            return httpx.Response(404)
        elif request.method == "DELETE" and "/shards/" in url_str:
            shard_id = url_str.split("/shards/")[1]
            key = (host_part, shard_id)
            if key in self.shards:
                del self.shards[key]
                return httpx.Response(200, json={"shard_id": shard_id, "deleted": True})
            return httpx.Response(404)
        elif request.method == "GET" and "/health" in url_str:
            return httpx.Response(200, json={"status": "online"})

        return httpx.Response(404)


@pytest.fixture
def metadata():
    return MetadataStore(persist_dir=None)


@pytest.fixture
def term_manager():
    return TermManager(persist_path=None)


@pytest.fixture
def mock_transport():
    return MockTransport()


@pytest.fixture
def events_collected():
    return []


@pytest.fixture
def broadcast(events_collected):
    async def _broadcast(event):
        events_collected.append(event)
    return _broadcast


@pytest.fixture
def repair_engine(metadata, term_manager, broadcast, mock_transport):
    return RepairEngine(
        metadata=metadata,
        term_manager=term_manager,
        broadcast=broadcast,
        http_transport=mock_transport,
    )


def make_nodes(metadata: MetadataStore, count: int = 6) -> list[NodeInfo]:
    nodes = []
    for i in range(count):
        node = NodeInfo(
            node_id=f"node-{i}",
            address=f"http://node-{i}:9000",
            status=NodeStatus.ONLINE,
            shard_count=0,
            capacity_bytes=1073741824,
        )
        metadata.register_node(node)
        nodes.append(node)
    return nodes


def upload_file_to_metadata(
    metadata: MetadataStore,
    transport: MockTransport,
    nodes: list[NodeInfo],
    file_name: str = "test.bin",
) -> FileMeta:
    """Simulate uploading a file by encoding and distributing shards."""
    content = uuid.uuid4().bytes * 64  # 1KB random data
    file_id = str(uuid.uuid4())
    checksum = hashlib.sha256(content).hexdigest()

    coder = ErasureCoder(k=settings.RS_K, m=settings.RS_M)
    fragments = coder.encode(content)

    sorted_nodes = sorted(nodes, key=lambda n: n.shard_count)
    shards: list[ShardLocation] = []

    for frag in fragments:
        node = sorted_nodes[frag.index % len(sorted_nodes)]
        shard_id = f"{file_id}_{frag.index}"
        role = ShardRole.DATA if frag.index < settings.RS_K else ShardRole.PARITY

        transport.shards[(node.address, shard_id)] = frag.data
        node.shard_count += 1

        shards.append(ShardLocation(
            shard_index=frag.index,
            node_id=node.node_id,
            shard_id=shard_id,
            checksum_sha256=frag.checksum,
            size_bytes=len(frag.data),
            role=role,
        ))

    file_meta = FileMeta(
        file_id=file_id,
        original_name=file_name,
        original_size=len(content),
        original_checksum=checksum,
        k=settings.RS_K,
        m=settings.RS_M,
        shard_size=len(fragments[0].data),
        shards=shards,
    )
    metadata.add_file(file_meta)
    return file_meta
