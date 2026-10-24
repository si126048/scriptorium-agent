from __future__ import annotations

import json
from pathlib import Path

from ..models import PerspectiveConfig

_BUILTINS_DIR = Path(__file__).parent
_registry: dict[str, PerspectiveConfig] | None = None


class PerspectiveRegistry:
    def __init__(self):
        self._perspectives: dict[str, PerspectiveConfig] = {}
        self._load_builtins()

    def _load_builtins(self) -> None:
        for path in sorted(_BUILTINS_DIR.glob('*.json')):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                config = PerspectiveConfig.model_validate(data)
                self._perspectives[config.id] = config
            except Exception:
                pass

    def register(self, config: PerspectiveConfig) -> None:
        self._perspectives[config.id] = config

    def get(self, perspective_id: str) -> PerspectiveConfig | None:
        return self._perspectives.get(perspective_id)

    def list_all(self) -> list[PerspectiveConfig]:
        return list(self._perspectives.values())

    def load_many(self, ids: list[str]) -> list[PerspectiveConfig]:
        result = []
        for pid in ids:
            config = self.get(pid)
            if config is None:
                raise KeyError(f'unknown perspective: {pid}')
            result.append(config)
        return result


def _default_registry() -> PerspectiveRegistry:
    global _registry
    if _registry is None:
        _registry = PerspectiveRegistry()
    return _registry


def get_perspective(perspective_id: str) -> PerspectiveConfig | None:
    return _default_registry().get(perspective_id)


def list_perspectives() -> list[PerspectiveConfig]:
    return _default_registry().list_all()
