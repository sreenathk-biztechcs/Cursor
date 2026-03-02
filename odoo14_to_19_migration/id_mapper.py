"""
Persistent ID-mapping store.

Keeps a JSON file that maps (model, source_id) → target_id so migrations
can be resumed without duplicating records.
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class IDMapper:
    def __init__(self, filepath: str = "id_mapping.json"):
        self.filepath = filepath
        self._map: dict[str, dict[str, int]] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, "r") as fh:
                self._map = json.load(fh)
            logger.info("Loaded %d model mappings from %s", len(self._map), self.filepath)

    def save(self):
        with open(self.filepath, "w") as fh:
            json.dump(self._map, fh, indent=2)

    def set(self, model: str, source_id: int, target_id: int):
        self._map.setdefault(model, {})[str(source_id)] = target_id

    def get(self, model: str, source_id: int) -> Optional[int]:
        return self._map.get(model, {}).get(str(source_id))

    def get_all(self, model: str) -> dict[int, int]:
        """Return {source_id: target_id} for every mapped record in a model."""
        return {int(k): v for k, v in self._map.get(model, {}).items()}

    def has(self, model: str, source_id: int) -> bool:
        return str(source_id) in self._map.get(model, {})

    def count(self, model: str) -> int:
        return len(self._map.get(model, {}))

    def resolve(self, model: str, source_id) -> Optional[int]:
        """Resolve source_id (int or [id, name] tuple from XML-RPC) to target_id."""
        if not source_id:
            return None
        sid = source_id[0] if isinstance(source_id, (list, tuple)) else source_id
        return self.get(model, sid)

    def clear(self):
        """Clear all mappings. Use with --full-refresh for a clean re-run (target DB must be empty)."""
        self._map = {}
        logger.warning("ID mapper cleared — all steps will create records from scratch.")
