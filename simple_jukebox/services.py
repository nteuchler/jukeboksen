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
    def is_muted(self) -> bool: ...

    def toggle_mute(self) -> None: ...

    def get(self) -> int: ...

    def set(self, volume: int) -> None: ...


class RgbService(Protocol):
    def status(self) -> dict[str, str | None]: ...

    def set_mode(self, mode: str) -> None: ...

    def set_countdown(self, fraction: float) -> None: ...

    def close(self) -> None: ...


class NfcService(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def status(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class JukeboxServices:
    """All side-effecting adapters available to the application core."""

    audio: AudioService
    bluetooth: BluetoothService
    volume: VolumeService
    rgb: RgbService
    nfc: NfcService | None = None
    quiz_media: QuizMediaService | None = None
    buzzer: BuzzerService | None = None
    survival_audio: SurvivalAudioService | None = None


class QuizMediaService(Protocol):
    def reset(self) -> None: ...
    def pause(self) -> None: ...
    def playback_status(self) -> str | None: ...


class BuzzerService(Protocol):
    def play(self) -> None: ...
    def stop(self) -> None: ...


class SurvivalAudioService(Protocol):
    error: str | None
    def play(self, cue: str) -> None: ...
    def stop(self) -> None: ...
