from __future__ import annotations

from magical_jukebox.modes.base import BaseMode


class MusicQuizMode(BaseMode):
    """Disabled scaffold. Define quiz rules before registering this mode."""

    async def enter(self) -> None:
        raise NotImplementedError("Music quiz mode is not implemented")

    async def exit(self) -> None:
        return None
