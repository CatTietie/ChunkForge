from __future__ import annotations

import hashlib
import logging
import uuid

import httpx
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import Response

from common.config import settings
from common.erasure import ErasureCoder
from common.events import Event, EventType
from common.models import FileMeta, FileStatus, ShardLocation, ShardRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files")


@router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    metadata = request.app.state.metadata
    broadcast = request.app.state.ws_manager.broadcast

    content = await file.read()
    file_id = str(uuid.uuid4())
    original_checksum = hashlib.sha256(content).hexdigest()

    coder = ErasureCoder(k=settings.RS_K, m=settings.RS_M)
    fragments = coder.encode(content)

    online_nodes = metadata.get_online_nodes()
    if len(online_nodes) < settings.RS_K + settings.RS_M:
        return Response(status_code=503, content="Not enough online nodes")

    sorted_nodes = sorted(online_nodes, key=lambda n: n.shard_count)

    shards: list[ShardLocation] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for frag in fragments:
            node = sorted_nodes[frag.index % len(sorted_nodes)]
            shard_id = f"{file_id}_{frag.index}"
            role = ShardRole.DATA if frag.index < settings.RS_K else ShardRole.PARITY

            resp = await client.put(
                f"{node.address}/shards/{shard_id}",
                content=frag.data,
                headers={
                    "X-File-Id": file_id,
                    "X-Shard-Index": str(frag.index),
                    "X-Checksum-SHA256": frag.checksum,
                    "X-Reed-Solomon-Role": role.value,
                },
            )
            if resp.status_code != 201:
                logger.error(f"Failed to write shard {shard_id} to {node.node_id}")
                continue

            shards.append(ShardLocation(
                shard_index=frag.index,
                node_id=node.node_id,
                shard_id=shard_id,
                checksum_sha256=frag.checksum,
                size_bytes=len(frag.data),
                role=role,
            ))
            node.shard_count += 1

    file_meta = FileMeta(
        file_id=file_id,
        original_name=file.filename or "unnamed",
        original_size=len(content),
        original_checksum=original_checksum,
        k=settings.RS_K,
        m=settings.RS_M,
        shard_size=len(fragments[0].data) if fragments else 0,
        shards=shards,
    )
    metadata.add_file(file_meta)

    await broadcast(Event(
        type=EventType.FILE_UPLOADED,
        payload={"file_id": file_id, "name": file_meta.original_name, "size": len(content)},
    ))

    return {
        "file_id": file_id,
        "name": file_meta.original_name,
        "size": file_meta.original_size,
        "status": file_meta.status.value,
        "upload_time": file_meta.upload_time.isoformat(),
        "shard_count": len(shards),
        "shards": [s.model_dump() for s in shards],
    }


@router.get("/{file_id}/download")
async def download_file(request: Request, file_id: str):
    metadata = request.app.state.metadata
    file_meta = metadata.get_file(file_id)
    if not file_meta:
        return Response(status_code=404, content="File not found")

    coder = ErasureCoder(k=file_meta.k, m=file_meta.m)
    from common.erasure import Fragment

    fragments = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for shard in file_meta.shards:
            node = metadata.get_node(shard.node_id)
            if not node or node.status != "online":
                continue
            try:
                resp = await client.get(f"{node.address}/shards/{shard.shard_id}")
                if resp.status_code == 200:
                    fragments.append(Fragment(
                        index=shard.shard_index,
                        data=resp.content,
                        checksum=shard.checksum_sha256,
                    ))
            except httpx.RequestError:
                continue
            if len(fragments) >= file_meta.k:
                break

    if len(fragments) < file_meta.k:
        return Response(status_code=503, content="Cannot retrieve enough shards")

    original_data = coder.decode(fragments, file_meta.original_size)
    return Response(
        content=original_data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file_meta.original_name}"'},
    )


@router.delete("/{file_id}")
async def delete_file(request: Request, file_id: str):
    metadata = request.app.state.metadata
    broadcast = request.app.state.ws_manager.broadcast

    file_meta = metadata.delete_file(file_id)
    if not file_meta:
        return Response(status_code=404, content="File not found")

    async with httpx.AsyncClient(timeout=30.0) as client:
        for shard in file_meta.shards:
            node = metadata.get_node(shard.node_id)
            if not node:
                continue
            try:
                await client.delete(f"{node.address}/shards/{shard.shard_id}")
            except httpx.RequestError:
                pass

    await broadcast(Event(
        type=EventType.FILE_DELETED,
        payload={"file_id": file_id, "name": file_meta.original_name},
    ))

    return {"deleted": True, "file_id": file_id}


@router.get("")
async def list_files(request: Request):
    metadata = request.app.state.metadata
    files = metadata.get_all_files()
    return {
        "files": [
            {
                "file_id": f.file_id,
                "name": f.original_name,
                "size": f.original_size,
                "status": f.status.value,
                "upload_time": f.upload_time.isoformat(),
                "shard_count": len(f.shards),
                "shards": [s.model_dump() for s in f.shards],
            }
            for f in files
        ]
    }
