from __future__ import annotations

import threading
from enum import Enum

from simple_jukebox.services import JukeboxServices


class Mode(str, Enum):
    IDLE = "idle"
    LOCAL_FILES = "local_files"
    BLUETOOTH = "bluetooth"


class StateMachine:
    """The single place that owns and changes the jukebox mode."""

    def __init__(self, services: JukeboxServices) -> None:
        self.services = services
        self.mode = Mode.IDLE
        self.message = "Ready"
        self._lock = threading.RLock()

    def change_mode(self, new_mode: str) -> None:
        try:
            target = Mode(new_mode)
        except ValueError as error:
            raise ValueError(f"Unknown mode: {new_mode}") from error

        with self._lock:
            if target == self.mode:
                return
            self._leave_current_mode()
            if target is Mode.BLUETOOTH:
                self.services.bluetooth.start()
                self.message = "Bluetooth is discoverable as Jukeboks"
            elif target is Mode.LOCAL_FILES:
                self.message = "Choose a local audio file"
            else:
                self.message = "Ready"
            self.mode = target

    def play(self, track: str) -> None:
        with self._lock:
            if self.mode is not Mode.LOCAL_FILES:
                raise RuntimeError("Switch to Local files mode first")
            self.services.audio.play(track)
            self.message = f"Playing {track}"

    def stop_audio(self) -> None:
        with self._lock:
            self.services.audio.stop()
            self.message = "Playback stopped"

    def toggle_mute(self) -> bool:
        with self._lock:
            muted = self.services.audio.toggle_mute()
            self.message = "Muted" if muted else "Sound on"
            return muted

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "mode": self.mode.value,
                "message": self.message,
                "playing": self.services.audio.playing,
                "track": self.services.audio.current_track,
                "muted": self.services.audio.muted,
                "bluetooth_active": self.services.bluetooth.active,
            }

    def close(self) -> None:
        with self._lock:
            self._leave_current_mode()

    def _leave_current_mode(self) -> None:
        if self.mode is Mode.LOCAL_FILES:
            self.services.audio.stop()
        if self.mode is Mode.BLUETOOTH:
            self.services.bluetooth.stop()
