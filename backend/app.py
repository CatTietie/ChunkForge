"""ChunkForge unified backend - combines Gateway + Coordinator in one process.

This ensures metadata consistency: one MetadataStore instance shared by file
upload/download routes, cluster management, heartbeat monitor, and repair engine.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from common.config import settings
from coordinator.heartbeat import HeartbeatMonitor
from coordinator.metadata import MetadataStore
from coordinator.rebalance import RebalanceEngine
from coordinator.repair import RepairEngine
from coordinator.routes import router as coordinator_router
from coordinator.term import TermManager
from gateway.routes_cluster import router as cluster_router
from gateway.routes_files import router as files_router
from gateway.websocket import WebSocketManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def create_unified_app() -> FastAPI:
    metadata = MetadataStore(persist_dir=settings.PERSIST_DIR)
    term_manager = TermManager(persist_path=f"{settings.PERSIST_DIR}/term.json")
    ws_manager = WebSocketManager()

    repair_engine = RepairEngine(
        metadata=metadata,
        term_manager=term_manager,
        broadcast=ws_manager.broadcast,
    )

    rebalance_engine = RebalanceEngine(
        metadata=metadata,
        repair_engine=repair_engine,
        broadcast=ws_manager.broadcast,
        max_migrations_per_round=settings.REBALANCE_MAX_MIGRATIONS,
        deviation_threshold=settings.REBALANCE_DEVIATION_THRESHOLD,
        periodic_interval_s=settings.REBALANCE_INTERVAL_S,
        max_concurrency=settings.REBALANCE_CONCURRENCY,
    )

    async def on_node_dead(node_id: str):
        logger.warning(f"Node {node_id} declared dead, triggering repair")
        await repair_engine.on_node_failed(node_id)

    heartbeat_monitor = HeartbeatMonitor(
        metadata=metadata,
        term_manager=term_manager,
        on_node_dead=on_node_dead,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        heartbeat_monitor.start()
        if settings.REBALANCE_ENABLED:
            rebalance_engine.start()
            logger.info("Rebalance engine enabled and started")
        yield
        heartbeat_monitor.stop()
        rebalance_engine.stop()

    app = FastAPI(title="ChunkForge", lifespan=lifespan)

    app.state.metadata = metadata
    app.state.term_manager = term_manager
    app.state.ws_manager = ws_manager
    app.state.repair_engine = repair_engine
    app.state.rebalance_engine = rebalance_engine

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(files_router)
    app.include_router(cluster_router)
    app.include_router(coordinator_router)

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket):
        await ws_manager.connect(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            await ws_manager.disconnect(ws)

    return app


app = create_unified_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.GATEWAY_PORT)
