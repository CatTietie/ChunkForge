from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ShardStorage:
    def __init__(self, base_dir: str = "./data/shards"):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def write_shard(self, file_id: str, shard_id: str, data: bytes) -> int:
        shard_dir = self._base / file_id
        shard_dir.mkdir(parents=True, exist_ok=True)
        path = shard_dir / f"{shard_id}.shard"
        path.write_bytes(data)
        return len(data)

    def read_shard(self, shard_id: str) -> bytes | None:
        for shard_dir in self._base.iterdir():
            if not shard_dir.is_dir():
                continue
            path = shard_dir / f"{shard_id}.shard"
            if path.exists():
                return path.read_bytes()
        return None

    def delete_shard(self, shard_id: str) -> bool:
        for shard_dir in self._base.iterdir():
            if not shard_dir.is_dir():
                continue
            path = shard_dir / f"{shard_id}.shard"
            if path.exists():
                path.unlink()
                if not any(shard_dir.iterdir()):
                    shard_dir.rmdir()
                return True
        return False

    def list_shards(self) -> list[str]:
        shards = []
        for shard_dir in self._base.iterdir():
            if not shard_dir.is_dir():
                continue
            for f in shard_dir.glob("*.shard"):
                shards.append(f.stem)
        return shards

    def get_shard_count(self) -> int:
        return len(self.list_shards())

    def get_disk_usage(self) -> int:
        total = 0
        for shard_dir in self._base.iterdir():
            if not shard_dir.is_dir():
                continue
            for f in shard_dir.glob("*.shard"):
                total += f.stat().st_size
        return total

    def compute_checksum(self, shard_id: str) -> str | None:
        data = self.read_shard(shard_id)
        if data is None:
            return None
        return hashlib.sha256(data).hexdigest()
