from __future__ import annotations

import asyncio
import logging

from magical_jukebox.core.enums import EventType
from magical_jukebox.core.messages import Event
from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.base import BaseEventService

logger = logging.getLogger(__name__)


class MockBluetoothService(BaseEventService):
    def __init__(self, status_store: StatusStore) -> None:
        super().__init__()
        self.status_store = status_store

    async def forget_all_pairings(self) -> None:
        await asyncio.sleep(0.05)
        self.status_store.patch_section(
            "bluetooth",
            connected=False,
            device=None,
            remembered_devices=0,
        )
        logger.info("Mock Bluetooth pairings cleared")

    async def start_pairing(self) -> None:
        await asyncio.sleep(0.05)
        self.status_store.patch_section(
            "bluetooth",
            enabled=True,
            pairing=True,
            connected=False,
            device=None,
        )
        logger.info("Mock Bluetooth pairing enabled")

    async def stop(self) -> None:
        self.status_store.patch_section(
            "bluetooth",
            enabled=False,
            pairing=False,
            connected=False,
            device=None,
        )

    async def simulate_connected(self, device: str) -> None:
        self.status_store.patch_section(
            "bluetooth",
            enabled=True,
            pairing=False,
            connected=True,
            device=device,
            remembered_devices=1,
        )
        if self._event_sink:
            await self._event_sink(
                Event(
                    type=EventType.BLUETOOTH_CONNECTED,
                    payload={"device": device},
                    source="mock_bluetooth",
                )
            )

    async def simulate_disconnected(self) -> None:
        self.status_store.patch_section(
            "bluetooth",
            pairing=False,
            connected=False,
            device=None,
        )
        if self._event_sink:
            await self._event_sink(
                Event(
                    type=EventType.BLUETOOTH_DISCONNECTED,
                    source="mock_bluetooth",
                )
            )
