from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from magical_jukebox.core.messages import Event

EventSink = Callable[[Event], Awaitable[None]]


class EventSource(Protocol):
    def set_event_sink(self, sink: EventSink) -> None: ...


class BluetoothService(Protocol):
    def set_event_sink(self, sink: EventSink) -> None: ...
    async def forget_all_pairings(self) -> None: ...
    async def start_pairing(self) -> None: ...
    async def stop(self) -> None: ...
    async def simulate_connected(self, device: str) -> None: ...
    async def simulate_disconnected(self) -> None: ...


class AudioService(Protocol):
    def set_event_sink(self, sink: EventSink) -> None: ...
    async def play(self, track: str) -> None: ...
    async def stop(self) -> None: ...
    def list_media(self) -> list[str]: ...


class HardwareService(Protocol):
    def set_event_sink(self, sink: EventSink) -> None: ...
    async def simulate_button(self, button_id: int) -> None: ...


class ConnectivityService(Protocol):
    def set_event_sink(self, sink: EventSink) -> None: ...
    async def refresh(self) -> None: ...


class LightingService(Protocol):
    def set_event_sink(self, sink: EventSink) -> None: ...
    async def set_pixel(self, pixel_index: int, red: int, green: int, blue: int) -> None: ...
    async def fill(self, red: int, green: int, blue: int) -> None: ...
    async def clear(self) -> None: ...


@dataclass(slots=True)
class ServiceBundle:
    bluetooth: BluetoothService
    audio: AudioService
    hardware: HardwareService
    connectivity: ConnectivityService
    lighting: LightingService
    media_dir: Path

    def set_event_sink(self, sink: EventSink) -> None:
        self.bluetooth.set_event_sink(sink)
        self.audio.set_event_sink(sink)
        self.hardware.set_event_sink(sink)
        self.connectivity.set_event_sink(sink)
        self.lighting.set_event_sink(sink)
