from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from node.heartbeat import HeartbeatSender
from node.routes import router
from node.storage import ShardStorage


def create_node_app(
    node_id: str | None = None,
    coordinator_url: str | None = None,
    storage_dir: str | None = None,
) -> FastAPI:
    node_id = node_id or os.getenv("NODE_ID", "node-0")
    coordinator_url = coordinator_url or os.getenv("COORDINATOR_URL", "http://localhost:8000")
    storage_dir = storage_dir or os.getenv("SHARD_STORAGE_DIR", "./data/shards")

    storage = ShardStorage(base_dir=storage_dir)
    heartbeat_sender = HeartbeatSender(
        node_id=node_id,
        coordinator_url=coordinator_url,
        storage=storage,
        interval_ms=int(os.getenv("HEARTBEAT_INTERVAL_MS", "1000")),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        heartbeat_sender.start()
        yield
        heartbeat_sender.stop()

    app = FastAPI(title=f"ChunkForge Node ({node_id})", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.storage = storage
    app.state.node_id = node_id
    app.state.heartbeat_sender = heartbeat_sender
    app.include_router(router)

    return app
