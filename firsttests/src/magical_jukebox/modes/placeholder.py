from __future__ import annotations

import asyncio
import logging

from magical_jukebox.core.enums import CommandType, EventType, RuntimeState
from magical_jukebox.core.messages import Command, Event
from magical_jukebox.modes.base import BaseMode

logger = logging.getLogger(__name__)


class PlaceholderMode(BaseMode):
    """Small deterministic flow used to test async transitions and fake input."""

    def __init__(self, context):
        super().__init__(context)
        self._step = 0

    async def enter(self) -> None:
        self._step = 0
        await self._advance()

    async def handle_command(self, command: Command) -> None:
        if command.type is CommandType.FORCE_NEXT:
            await self._advance()

    async def handle_event(self, event: Event) -> None:
        if event.type is EventType.BUTTON_PRESSED:
            button_id = event.payload.get("button_id")
            logger.info("Placeholder accepted virtual button %s", button_id)
            await self._advance(button_id=button_id)

    async def exit(self) -> None:
        self.context.status_store.patch(
            expects_input=False,
            microphone_active=False,
        )

    async def _advance(self, button_id: object | None = None) -> None:
        if self._step == 0:
            self.context.status_store.patch(
                state=RuntimeState.PREPARING.value,
                message="Placeholder activity is preparing",
                expects_input=False,
            )
            await asyncio.sleep(0.15)
            self._step = 1
            self.context.status_store.patch(
                state=RuntimeState.WAITING.value,
                message="Waiting for a virtual button or Force next",
                expects_input=True,
            )
            return

        if self._step == 1:
            self._step = 2
            suffix = f" after button {button_id}" if button_id is not None else ""
            self.context.status_store.patch(
                state=RuntimeState.PLAYING.value,
                message=f"Simulating activity feedback{suffix}",
                expects_input=False,
            )
            await asyncio.sleep(0.2)
            return

        if self._step == 2:
            self._step = 3
            self.context.status_store.patch(
                state=RuntimeState.COMPLETED.value,
                message="Placeholder activity completed; Force next restarts it",
                expects_input=False,
            )
            return

        self._step = 0
        await self._advance()
