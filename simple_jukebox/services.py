"""Hardware-independent service contracts used by the jukebox core."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class AudioService(Protocol):
    media_folder: Path
    current_track: str | None
    muted: bool

    @property
    def playing(self) -> bool: ...

    def tracks(self) -> list[str]: ...

    def play(self, track: str) -> None: ...

    def stop(self) -> None: ...

    def toggle_mute(self) -> bool: ...


class BluetoothService(Protocol):
    @property
    def active(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


class VolumeService(Protocol):
    def get(self) -> int: ...

    def set(self, volume: int) -> None: ...


class RgbService(Protocol):
    def status(self) -> dict[str, str | None]: ...

    def set_mode(self, mode: str) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class JukeboxServices:
    """All side-effecting adapters available to the application core."""

    audio: AudioService
    bluetooth: BluetoothService
    volume: VolumeService
    rgb: RgbService
