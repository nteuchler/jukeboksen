from __future__ import annotations

from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.base import BaseEventService


class MockConnectivityService(BaseEventService):
    def __init__(self, status_store: StatusStore, *, profile: str = "mock") -> None:
        super().__init__()
        self.status_store = status_store
        self.profile = profile

    async def refresh(self) -> None:
        self.status_store.patch_section(
            "system",
            internet=True,
            battery_percent=None,
            service_profile=self.profile,
        )
