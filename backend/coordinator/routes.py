from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Request

from common.events import Event, EventType
from common.models import HeartbeatRequest, HeartbeatResponse, NodeInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal")


@router.post("/heartbeat")
async def receive_heartbeat(request: Request, hb: HeartbeatRequest) -> HeartbeatResponse:
    metadata = request.app.state.metadata
    term_manager = request.app.state.term_manager

    node = metadata.get_node(hb.node_id)
    if not node:
        return HeartbeatResponse(ack=False, current_term=term_manager.current_term)

    metadata.update_node_heartbeat(hb.node_id, hb.shard_count, hb.disk_usage_bytes)
    return HeartbeatResponse(ack=True, current_term=term_manager.current_term)


@router.post("/nodes/register")
async def register_node(request: Request, node: NodeInfo):
    metadata = request.app.state.metadata
    broadcast = request.app.state.ws_manager.broadcast

    node.last_heartbeat = datetime.utcnow()
    metadata.register_node(node)

    await broadcast(Event(
        type=EventType.NODE_JOINED,
        payload={"node_id": node.node_id, "address": node.address},
    ))

    rebalance = getattr(request.app.state, "rebalance_engine", None)
    if rebalance:
        rebalance.trigger("node_joined")

    return {"registered": True, "node_id": node.node_id}
