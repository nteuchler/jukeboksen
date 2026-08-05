from __future__ import annotations

import logging

from magical_jukebox.core.enums import CommandType, EventType, RuntimeState
from magical_jukebox.core.messages import Command, Event
from magical_jukebox.modes.base import BaseMode

logger = logging.getLogger(__name__)


class BluetoothSpeakerMode(BaseMode):
    async def enter(self) -> None:
        profile = self.context.status_store.snapshot()["system"].get("service_profile")
        pairing_message = (
            "Bluetooth pairing is open; connect a phone to the Raspberry Pi"
            if profile == "raspberry_pi"
            else "Bluetooth pairing is open; simulate a phone connection from the web panel"
        )
        self.context.status_store.patch(
            state=RuntimeState.STARTING.value,
            message="Clearing old Bluetooth pairings",
            expects_input=False,
        )
        await self.context.services.bluetooth.forget_all_pairings()
        await self.context.services.bluetooth.start_pairing()
        self.context.status_store.patch(
            state=RuntimeState.PAIRING.value,
            message=pairing_message,
            expects_input=True,
        )

    async def handle_command(self, command: Command) -> None:
        if command.type is CommandType.FORCE_NEXT:
            profile = self.context.status_store.snapshot()["system"].get("service_profile")
            if profile == "raspberry_pi":
                self.context.status_store.patch(
                    message="Waiting for a real Bluetooth device connection",
                )
                return
            snapshot = self.context.status_store.snapshot()
            if snapshot["bluetooth"]["connected"]:
                await self.context.services.bluetooth.simulate_disconnected()
            else:
                await self.context.services.bluetooth.simulate_connected("Forced test phone")

    async def handle_event(self, event: Event) -> None:
        if event.type is EventType.BLUETOOTH_CONNECTED:
            device = event.payload.get("device") or "Unknown phone"
            self.context.status_store.patch(
                state=RuntimeState.CONNECTED.value,
                message=f"Connected to {device}",
                expects_input=False,
            )
            return

        if event.type is EventType.BLUETOOTH_DISCONNECTED:
            await self.context.services.bluetooth.start_pairing()
            self.context.status_store.patch(
                state=RuntimeState.PAIRING.value,
                message="Phone disconnected; pairing is open again",
                expects_input=True,
            )

    async def exit(self) -> None:
        logger.info("Stopping Bluetooth speaker mode")
        await self.context.services.bluetooth.stop()
        await self.context.services.bluetooth.forget_all_pairings()
        self.context.status_store.patch(expects_input=False)
