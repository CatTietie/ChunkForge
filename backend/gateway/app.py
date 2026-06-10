from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gateway.routes_cluster import router as cluster_router
from gateway.routes_files import router as files_router


def create_gateway_app() -> FastAPI:
    app = FastAPI(title="ChunkForge Gateway")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(files_router)
    app.include_router(cluster_router)
    return app
