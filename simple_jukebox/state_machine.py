from __future__ import annotations

import threading
from enum import Enum
from typing import Any


class Mode(str, Enum):
    IDLE = "idle"
    LOCAL_FILES = "local_files"
    BLUETOOTH = "bluetooth"


class StateMachine:
    """The single place that owns and changes the jukebox mode."""

    def __init__(self, player: Any, bluetooth: Any) -> None:
        self.player = player
        self.bluetooth = bluetooth
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
                self.bluetooth.start()
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
            self.player.play(track)
            self.message = f"Playing {track}"

    def stop_audio(self) -> None:
        with self._lock:
            self.player.stop()
            self.message = "Playback stopped"

    def toggle_mute(self) -> bool:
        with self._lock:
            muted = self.player.toggle_mute()
            self.message = "Muted" if muted else "Sound on"
            return muted

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "mode": self.mode.value,
                "message": self.message,
                "playing": self.player.playing,
                "track": self.player.current_track,
                "muted": self.player.muted,
                "bluetooth_active": self.bluetooth.active,
            }

    def close(self) -> None:
        with self._lock:
            self._leave_current_mode()

    def _leave_current_mode(self) -> None:
        if self.mode is Mode.LOCAL_FILES:
            self.player.stop()
        if self.mode is Mode.BLUETOOTH:
            self.bluetooth.stop()
