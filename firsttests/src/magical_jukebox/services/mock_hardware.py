from __future__ import annotations

from magical_jukebox.core.enums import EventType
from magical_jukebox.core.messages import Event
from magical_jukebox.services.base import BaseEventService


class MockHardwareService(BaseEventService):
    async def simulate_button(self, button_id: int) -> None:
        if button_id < 1 or button_id > 8:
            raise ValueError("button_id must be between 1 and 8")
        if self._event_sink:
            await self._event_sink(
                Event(
                    type=EventType.BUTTON_PRESSED,
                    payload={"button_id": button_id},
                    source="mock_hardware",
                )
            )
