from __future__ import annotations

from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.base import BaseEventService


class MockLightingService(BaseEventService):
    def __init__(self, status_store: StatusStore) -> None:
        super().__init__()
        self.status_store = status_store
        self.status_store.patch_section(
            "lighting",
            available=False,
            enabled=False,
            pixel_count=0,
            last_color=[0, 0, 0],
        )

    async def set_pixel(self, pixel_index: int, red: int, green: int, blue: int) -> None:
        self.status_store.patch_section(
            "lighting",
            enabled=False,
            last_color=[int(red), int(green), int(blue)],
        )

    async def fill(self, red: int, green: int, blue: int) -> None:
        self.status_store.patch_section(
            "lighting",
            enabled=False,
            last_color=[int(red), int(green), int(blue)],
        )

    async def clear(self) -> None:
        self.status_store.patch_section(
            "lighting",
            enabled=False,
            last_color=[0, 0, 0],
        )
