from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from common.models import FileMeta, FileStatus, NodeInfo, NodeStatus, ShardLocation

logger = logging.getLogger(__name__)


class MetadataStore:
    def __init__(self, persist_dir: str | None = None):
        self._files: dict[str, FileMeta] = {}
        self._nodes: dict[str, NodeInfo] = {}
        self._persist_dir: Path | None = Path(persist_dir) if persist_dir else None
        if self._persist_dir:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    # --- Node operations ---

    def register_node(self, node: NodeInfo) -> None:
        self._nodes[node.node_id] = node
        self._persist()

    def remove_node(self, node_id: str) -> Optional[NodeInfo]:
        node = self._nodes.pop(node_id, None)
        if node:
            self._persist()
        return node

    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> list[NodeInfo]:
        return list(self._nodes.values())

    def get_online_nodes(self) -> list[NodeInfo]:
        return [n for n in self._nodes.values() if n.status == NodeStatus.ONLINE]

    def update_node_status(self, node_id: str, status: NodeStatus) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.status = status
            self._persist()

    def update_node_heartbeat(self, node_id: str, shard_count: int, disk_usage: int) -> None:
        from datetime import datetime
        node = self._nodes.get(node_id)
        if node:
            node.last_heartbeat = datetime.utcnow()
            node.shard_count = shard_count
            node.used_bytes = disk_usage
            self._persist()

    def get_node_with_least_shards(self, exclude: set[str] | None = None) -> Optional[NodeInfo]:
        exclude = exclude or set()
        candidates = [
            n for n in self._nodes.values()
            if n.status == NodeStatus.ONLINE and n.node_id not in exclude
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda n: n.shard_count)

    # --- File operations ---

    def add_file(self, file_meta: FileMeta) -> None:
        self._files[file_meta.file_id] = file_meta
        self._persist()

    def get_file(self, file_id: str) -> Optional[FileMeta]:
        return self._files.get(file_id)

    def get_all_files(self) -> list[FileMeta]:
        return list(self._files.values())

    def delete_file(self, file_id: str) -> Optional[FileMeta]:
        fm = self._files.pop(file_id, None)
        if fm:
            self._persist()
        return fm

    def update_file_status(self, file_id: str, status: FileStatus) -> None:
        fm = self._files.get(file_id)
        if fm:
            fm.status = status
            self._persist()

    def update_shard_location(self, file_id: str, shard_index: int, new_node_id: str) -> None:
        fm = self._files.get(file_id)
        if fm:
            for shard in fm.shards:
                if shard.shard_index == shard_index:
                    shard.node_id = new_node_id
                    break
            self._persist()

    # --- Query operations ---

    def get_shards_on_node(self, node_id: str) -> list[tuple[str, ShardLocation]]:
        result: list[tuple[str, ShardLocation]] = []
        for fm in self._files.values():
            for shard in fm.shards:
                if shard.node_id == node_id:
                    result.append((fm.file_id, shard))
        return result

    # --- Persistence ---

    def _load(self):
        if not self._persist_dir:
            return
        files_path = self._persist_dir / "files.json"
        nodes_path = self._persist_dir / "nodes.json"

        if files_path.exists():
            try:
                data = json.loads(files_path.read_text())
                for item in data:
                    fm = FileMeta.model_validate(item)
                    self._files[fm.file_id] = fm
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load files metadata: {e}")

        if nodes_path.exists():
            try:
                data = json.loads(nodes_path.read_text())
                for item in data:
                    node = NodeInfo.model_validate(item)
                    self._nodes[node.node_id] = node
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load nodes metadata: {e}")

    def _persist(self):
        if not self._persist_dir:
            return
        files_path = self._persist_dir / "files.json"
        nodes_path = self._persist_dir / "nodes.json"

        try:
            files_data = [fm.model_dump(mode="json") for fm in self._files.values()]
            files_path.write_text(json.dumps(files_data, default=str))

            nodes_data = [n.model_dump(mode="json") for n in self._nodes.values()]
            nodes_path.write_text(json.dumps(nodes_data, default=str))
        except OSError as e:
            logger.error(f"Failed to persist metadata: {e}")
