from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ShardRole(str, Enum):
    DATA = "data"
    PARITY = "parity"


class NodeStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    CRASHED = "crashed"
    DRAINING = "draining"


class FileStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    REPAIRING = "repairing"
    LOST = "lost"


class RepairState(str, Enum):
    QUEUED = "queued"
    DETECTING = "detecting"
    PLANNING = "planning"
    RECONSTRUCTING = "reconstructing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class ShardLocation(BaseModel):
    shard_index: int
    node_id: str
    shard_id: str
    checksum_sha256: str
    size_bytes: int
    role: ShardRole


class FileMeta(BaseModel):
    file_id: str
    original_name: str
    original_size: int
    original_checksum: str
    upload_time: datetime = Field(default_factory=datetime.utcnow)
    k: int = 4
    m: int = 2
    shard_size: int = 0
    shards: list[ShardLocation] = Field(default_factory=list)
    status: FileStatus = FileStatus.HEALTHY


class NodeInfo(BaseModel):
    node_id: str
    address: str
    status: NodeStatus = NodeStatus.ONLINE
    shard_count: int = 0
    capacity_bytes: int = 0
    used_bytes: int = 0
    last_heartbeat: Optional[datetime] = None
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    term_acknowledged: int = 0


class RepairTask(BaseModel):
    task_id: str
    file_id: str
    missing_shard_indices: list[int] = Field(default_factory=list)
    source_nodes: dict[int, str] = Field(default_factory=dict)
    target_node_id: str = ""
    state: RepairState = RepairState.QUEUED
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    error: Optional[str] = None


class HeartbeatRequest(BaseModel):
    node_id: str
    term: int = 0
    shard_count: int = 0
    disk_usage_bytes: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HeartbeatResponse(BaseModel):
    ack: bool = True
    current_term: int = 0
    commands: list[str] = Field(default_factory=list)
