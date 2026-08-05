from __future__ import annotations

from magical_jukebox.core.enums import RuntimeState
from magical_jukebox.modes.base import BaseMode


class IdleMode(BaseMode):
    async def enter(self) -> None:
        self.context.status_store.patch(
            state=RuntimeState.IDLE.value,
            message="Jukebox is idle",
            expects_input=False,
            microphone_active=False,
        )

    async def exit(self) -> None:
        return None
