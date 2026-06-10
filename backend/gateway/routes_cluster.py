from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from common.events import Event, EventType
from common.models import NodeInfo, NodeStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cluster")


@router.get("/status")
async def cluster_status(request: Request):
    metadata = request.app.state.metadata
    nodes = metadata.get_all_nodes()
    files = metadata.get_all_files()
    online = [n for n in nodes if n.status == NodeStatus.ONLINE]
    return {
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "files_count": len(files),
        "online_nodes": len(online),
        "total_nodes": len(nodes),
    }


@router.post("/nodes")
async def add_node(request: Request, node: NodeInfo):
    metadata = request.app.state.metadata
    broadcast = request.app.state.ws_manager.broadcast

    node.last_heartbeat = datetime.utcnow()
    node.joined_at = datetime.utcnow()
    metadata.register_node(node)

    await broadcast(Event(
        type=EventType.NODE_JOINED,
        payload={"node_id": node.node_id, "address": node.address},
    ))

    rebalance = getattr(request.app.state, "rebalance_engine", None)
    if rebalance:
        rebalance.trigger("node_joined")

    return {"registered": True, "node_id": node.node_id}


@router.delete("/nodes/{node_id}")
async def remove_node(request: Request, node_id: str):
    metadata = request.app.state.metadata
    broadcast = request.app.state.ws_manager.broadcast

    node = metadata.remove_node(node_id)
    if not node:
        return JSONResponse(status_code=404, content={"error": "Node not found"})

    await broadcast(Event(
        type=EventType.NODE_REMOVED,
        payload={"node_id": node_id},
    ))
    return {"removed": True, "node_id": node_id}


@router.post("/nodes/{node_id}/crash")
async def crash_node(request: Request, node_id: str):
    metadata = request.app.state.metadata
    broadcast = request.app.state.ws_manager.broadcast
    term_manager = request.app.state.term_manager
    repair_engine = request.app.state.repair_engine

    node = metadata.get_node(node_id)
    if not node:
        return JSONResponse(status_code=404, content={"error": "Node not found"})

    metadata.update_node_status(node_id, NodeStatus.CRASHED)
    term_manager.increment()

    await broadcast(Event(
        type=EventType.NODE_CRASHED,
        payload={"node_id": node_id},
    ))

    await repair_engine.on_node_failed(node_id)
    return {"crashed": True, "node_id": node_id}


@router.post("/nodes/{node_id}/recover")
async def recover_node(request: Request, node_id: str):
    metadata = request.app.state.metadata
    broadcast = request.app.state.ws_manager.broadcast
    repair_engine = request.app.state.repair_engine

    node = metadata.get_node(node_id)
    if not node:
        return JSONResponse(status_code=404, content={"error": "Node not found"})

    metadata.update_node_status(node_id, NodeStatus.ONLINE)
    node.last_heartbeat = datetime.utcnow()

    await repair_engine.reconcile_node(node_id)

    await broadcast(Event(
        type=EventType.NODE_RESURRECTED,
        payload={"node_id": node_id},
    ))

    rebalance = getattr(request.app.state, "rebalance_engine", None)
    if rebalance:
        rebalance.trigger("node_recovered")

    return {"recovered": True, "node_id": node_id}


@router.post("/rebalance")
async def trigger_rebalance(request: Request):
    rebalance = getattr(request.app.state, "rebalance_engine", None)
    if not rebalance:
        return JSONResponse(status_code=503, content={"error": "Rebalance engine not available"})
    rebalance.trigger("manual_api")
    return {"triggered": True, "state": rebalance.state.value}


@router.get("/rebalance")
async def rebalance_status(request: Request):
    rebalance = getattr(request.app.state, "rebalance_engine", None)
    if not rebalance:
        return JSONResponse(status_code=503, content={"error": "Rebalance engine not available"})
    return rebalance.get_status()
