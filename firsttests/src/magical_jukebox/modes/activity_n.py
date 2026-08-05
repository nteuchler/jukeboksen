from __future__ import annotations

from magical_jukebox.modes.base import BaseMode


class ActivityNMode(BaseMode):
    """Disabled scaffold for future activities."""

    async def enter(self) -> None:
        raise NotImplementedError("Activity N mode is not implemented")

    async def exit(self) -> None:
        return None
