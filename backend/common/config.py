from __future__ import annotations

import os


class _Settings:
    GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8000"))
    COORDINATOR_PORT: int = int(os.getenv("COORDINATOR_PORT", "8001"))
    NODE_PORT: int = int(os.getenv("NODE_PORT", "9000"))

    HEARTBEAT_INTERVAL_MS: int = int(os.getenv("HEARTBEAT_INTERVAL_MS", "1000"))
    HEARTBEAT_TIMEOUT_MS: int = int(os.getenv("HEARTBEAT_TIMEOUT_MS", "3000"))

    RS_K: int = int(os.getenv("RS_K", "4"))
    RS_M: int = int(os.getenv("RS_M", "2"))

    REPAIR_CONCURRENCY: int = int(os.getenv("REPAIR_CONCURRENCY", "4"))
    REPAIR_MAX_RETRIES: int = int(os.getenv("REPAIR_MAX_RETRIES", "2"))

    REBALANCE_ENABLED: bool = os.getenv("REBALANCE_ENABLED", "true").lower() == "true"
    REBALANCE_INTERVAL_S: float = float(os.getenv("REBALANCE_INTERVAL_S", "60"))
    REBALANCE_MAX_MIGRATIONS: int = int(os.getenv("REBALANCE_MAX_MIGRATIONS", "4"))
    REBALANCE_DEVIATION_THRESHOLD: int = int(os.getenv("REBALANCE_DEVIATION_THRESHOLD", "2"))
    REBALANCE_CONCURRENCY: int = int(os.getenv("REBALANCE_CONCURRENCY", "4"))

    PERSIST_DIR: str = os.getenv("PERSIST_DIR", "./data/metadata")
    SHARD_STORAGE_DIR: str = os.getenv("SHARD_STORAGE_DIR", "./data/shards")


settings = _Settings()
