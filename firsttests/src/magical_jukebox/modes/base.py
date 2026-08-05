from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from magical_jukebox.core.messages import Command, Event
from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.interfaces import ServiceBundle


@dataclass(slots=True)
class ModeContext:
    status_store: StatusStore
    services: ServiceBundle
    emit_event: Callable[[Event], Awaitable[None]]


class BaseMode(ABC):
    def __init__(self, context: ModeContext) -> None:
        self.context = context

    @abstractmethod
    async def enter(self) -> None:
        raise NotImplementedError

    async def handle_command(self, command: Command) -> None:
        return None

    async def handle_event(self, event: Event) -> None:
        return None

    @abstractmethod
    async def exit(self) -> None:
        raise NotImplementedError
