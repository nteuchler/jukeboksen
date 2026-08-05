from __future__ import annotations

from magical_jukebox.modes.base import BaseMode


class UpdateMode(BaseMode):
    """Disabled scaffold for a future safe update/maintenance flow."""

    async def enter(self) -> None:
        raise NotImplementedError("Update mode is not implemented")

    async def exit(self) -> None:
        return None
