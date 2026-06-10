from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TermManager:
    def __init__(self, persist_path: str | None = None):
        self._term: int = 0
        self._persist_path = Path(persist_path) if persist_path else None
        if self._persist_path:
            self._load()

    @property
    def current_term(self) -> int:
        return self._term

    def increment(self) -> int:
        self._term += 1
        self._persist()
        logger.info(f"Term incremented to {self._term}")
        return self._term

    def _load(self):
        if self._persist_path and self._persist_path.exists():
            try:
                data = json.loads(self._persist_path.read_text())
                self._term = data.get("term", 0)
            except (json.JSONDecodeError, OSError):
                self._term = 0

    def _persist(self):
        if self._persist_path:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(json.dumps({"term": self._term}))
