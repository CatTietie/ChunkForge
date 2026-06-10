from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.put("/shards/{shard_id}", status_code=201)
async def write_shard(request: Request, shard_id: str):
    storage = request.app.state.storage
    data = await request.body()

    file_id = request.headers.get("X-File-Id", "")
    expected_checksum = request.headers.get("X-Checksum-SHA256", "")

    actual_checksum = hashlib.sha256(data).hexdigest()
    checksum_verified = actual_checksum == expected_checksum if expected_checksum else True

    size = storage.write_shard(file_id, shard_id, data)

    return {
        "shard_id": shard_id,
        "stored": True,
        "checksum_verified": checksum_verified,
        "size_bytes": size,
    }


@router.get("/shards/{shard_id}")
async def read_shard(request: Request, shard_id: str):
    storage = request.app.state.storage
    data = storage.read_shard(shard_id)
    if data is None:
        return Response(status_code=404, content="Shard not found")

    checksum = hashlib.sha256(data).hexdigest()
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "X-Shard-Id": shard_id,
            "X-Checksum-SHA256": checksum,
            "X-Shard-Size": str(len(data)),
        },
    )


@router.delete("/shards/{shard_id}")
async def delete_shard(request: Request, shard_id: str):
    storage = request.app.state.storage
    deleted = storage.delete_shard(shard_id)
    if not deleted:
        return Response(status_code=404, content="Shard not found")
    return {"shard_id": shard_id, "deleted": True}


@router.get("/health")
async def health(request: Request):
    storage = request.app.state.storage
    node_id = request.app.state.node_id
    shards = storage.list_shards()
    return {
        "node_id": node_id,
        "status": "online",
        "shard_count": len(shards),
        "shards": shards,
        "disk_usage_bytes": storage.get_disk_usage(),
    }
