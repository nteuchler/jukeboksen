from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from magical_jukebox.core.enums import CommandType, EventType


@dataclass(slots=True, frozen=True)
class Command:
    type: CommandType
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "web"
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(slots=True, frozen=True)
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "service"
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


Message = Command | Event
