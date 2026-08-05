from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class StatusStore:
    """Thread-safe shared status exposed to Flask as immutable snapshots."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._data: dict[str, Any] = {
            "mode": "idle",
            "mode_label": "Idle",
            "state": "stopped",
            "message": "Engine has not started",
            "expects_input": False,
            "microphone_active": False,
            "audio": {
                "playing": False,
                "track": None,
            },
            "bluetooth": {
                "enabled": False,
                "pairing": False,
                "connected": False,
                "device": None,
                "remembered_devices": 0,
            },
            "system": {
                "internet": True,
                "battery_percent": None,
                "service_profile": "mock",
            },
            "lighting": {
                "available": False,
                "enabled": False,
                "pixel_count": 0,
                "last_color": [0, 0, 0],
            },
            "last_error": None,
            "updated_at": _utc_now(),
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._data)

    def patch(self, **changes: Any) -> dict[str, Any]:
        with self._lock:
            for key, value in changes.items():
                self._data[key] = deepcopy(value)
            self._data["updated_at"] = _utc_now()
            return deepcopy(self._data)

    def patch_section(self, section: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            current = self._data.setdefault(section, {})
            if not isinstance(current, dict):
                raise TypeError(f"Status section {section!r} is not a dictionary")
            current.update(deepcopy(changes))
            self._data["updated_at"] = _utc_now()
            return deepcopy(self._data)
