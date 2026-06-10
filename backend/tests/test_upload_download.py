from __future__ import annotations

import asyncio
import hashlib
import uuid

import pytest

from common.config import settings
from common.erasure import ErasureCoder
from common.events import EventType
from common.models import NodeInfo, NodeStatus, ShardRole
from coordinator.metadata import MetadataStore
from coordinator.repair import RepairEngine
from tests.conftest import MockTransport, make_nodes, upload_file_to_metadata


class TestUploadDownload:
    @pytest.mark.asyncio
    async def test_upload_creates_6_shards(self):
        metadata = MetadataStore(persist_dir=None)
        transport = MockTransport()
        nodes = make_nodes(metadata, 6)

        fm = upload_file_to_metadata(metadata, transport, nodes, "test.bin")
        assert len(fm.shards) == 6
        assert fm.status.value == "healthy"

        data_shards = [s for s in fm.shards if s.role == ShardRole.DATA]
        parity_shards = [s for s in fm.shards if s.role == ShardRole.PARITY]
        assert len(data_shards) == 4
        assert len(parity_shards) == 2

    @pytest.mark.asyncio
    async def test_download_reconstructs_original(self):
        metadata = MetadataStore(persist_dir=None)
        transport = MockTransport()
        nodes = make_nodes(metadata, 6)

        content = b"This is test content for download verification." * 20
        file_id = str(uuid.uuid4())
        checksum = hashlib.sha256(content).hexdigest()

        coder = ErasureCoder(k=4, m=2)
        fragments = coder.encode(content)

        from common.models import FileMeta, ShardLocation
        shards = []
        for frag in fragments:
            node = nodes[frag.index % len(nodes)]
            shard_id = f"{file_id}_{frag.index}"
            transport.shards[shard_id] = frag.data
            shards.append(ShardLocation(
                shard_index=frag.index,
                node_id=node.node_id,
                shard_id=shard_id,
                checksum_sha256=frag.checksum,
                size_bytes=len(frag.data),
                role=ShardRole.DATA if frag.index < 4 else ShardRole.PARITY,
            ))

        fm = FileMeta(
            file_id=file_id,
            original_name="test.bin",
            original_size=len(content),
            original_checksum=checksum,
            shard_size=len(fragments[0].data),
            shards=shards,
        )
        metadata.add_file(fm)

        # Simulate download by reading k fragments and decoding
        from common.erasure import Fragment
        read_fragments = []
        for shard in fm.shards[:4]:
            data = transport.shards[shard.shard_id]
            read_fragments.append(Fragment(index=shard.shard_index, data=data))

        result = coder.decode(read_fragments, fm.original_size)
        assert result == content
