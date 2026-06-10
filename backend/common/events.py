from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    NODE_JOINED = "node_joined"
    NODE_REMOVED = "node_removed"
    NODE_CRASHED = "node_crashed"
    NODE_RESURRECTED = "node_resurrected"
    FILE_UPLOADED = "file_uploaded"
    FILE_DELETED = "file_deleted"
    SHARD_WRITTEN = "shard_written"
    SHARD_DELETED = "shard_deleted"
    REPAIR_STARTED = "repair_started"
    REPAIR_PROGRESS = "repair_progress"
    REPAIR_COMPLETED = "repair_completed"
    REPAIR_FAILED = "repair_failed"
    PARTITION_DETECTED = "partition_detected"
    PARTITION_HEALED = "partition_healed"
    TERM_INCREMENTED = "term_incremented"
    REBALANCE_STARTED = "rebalance_started"
    REBALANCE_PROGRESS = "rebalance_progress"
    REBALANCE_COMPLETED = "rebalance_completed"
    REBALANCE_PAUSED = "rebalance_paused"


class Event(BaseModel):
    type: EventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
