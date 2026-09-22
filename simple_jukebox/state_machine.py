from __future__ import annotations

import threading
import time
from enum import Enum

from simple_jukebox.services import JukeboxServices


class Mode(str, Enum):
    IDLE = "idle"
    LOCAL_FILES = "local_files"
    BLUETOOTH = "bluetooth"
    NFC = "nfc"
    MUSIC_QUIZ = "music_quiz"


class StateMachine:
    """The single place that owns and changes the jukebox mode."""

    def __init__(self, services: JukeboxServices) -> None:
        self.services = services
        self.mode = Mode.IDLE
        self.message = "Ready"
        self._lock = threading.RLock()
        self.quiz_winner = None
        self.quiz_error = None
        self._quiz_saw_pause = False
        self._quiz_poll_at = 0.0
        self._quiz_buzz_at = 0.0
        self._previous_rgb = "off"

    def change_mode(self, new_mode: str) -> None:
        try:
            target = Mode(new_mode)
        except ValueError as error:
            raise ValueError(f"Unknown mode: {new_mode}") from error

        with self._lock:
            if target == self.mode:
                return
            if target is Mode.NFC and self.services.nfc is None:
                raise RuntimeError("NFC reader is not configured")
            if target is Mode.MUSIC_QUIZ and self.services.quiz_media is None:
                raise RuntimeError("Quiz Bluetooth controls are not configured")
            self._leave_current_mode()
            self.mode = Mode.IDLE
            self.message = "Ready"
            if target in {Mode.BLUETOOTH, Mode.MUSIC_QUIZ}:
                self.services.bluetooth.start()
                self.message = "Bluetooth is discoverable as Jukeboks"
                if target is Mode.MUSIC_QUIZ:
                    self._previous_rgb = self.services.rgb.status()["mode"]
                    self.services.quiz_media.reset()
                    self._reset_quiz()
            elif target is Mode.NFC:
                self.services.nfc.start()
                self.message = "Present an NFC tag"
            elif target is Mode.LOCAL_FILES:
                self.message = "Choose a local audio file"
            else:
                self.message = "Ready"
            self.mode = target

    def _reset_quiz(self):
        self.quiz_winner = None
        self.quiz_error = None
        self._quiz_saw_pause = False
        self.services.rgb.set_mode("equalizer")
        self.message = "Music quiz: play music from your phone, then buzz in"

    def arcade_press(self, player: int) -> None:
        with self._lock:
            if self.mode is not Mode.MUSIC_QUIZ or self.quiz_winner is not None:
                return
            if player not in (1, 2):
                raise ValueError("Unknown quiz player")
            self.quiz_winner = player
            self._quiz_buzz_at = time.monotonic()
            self._quiz_poll_at = 0.0
            self.services.rgb.set_mode("red" if player == 1 else "green")
            self.message = f"Player {player} buzzed in! Resume music on your phone for the next round"
            try:
                self.services.quiz_media.pause()
                self._quiz_saw_pause = self.services.quiz_media.playback_status() in {"paused", "stopped"}
            except Exception as error:
                self.quiz_error = f"Bluetooth pause unavailable: {error}. Pause and resume on your phone"
            if self.services.buzzer is not None:
                try:
                    self.services.buzzer.play()
                except Exception as error:
                    self.quiz_error = f"{self.quiz_error + '; ' if self.quiz_error else ''}Buzzer unavailable: {error}"

    def poll_quiz(self) -> None:
        """Called by the command worker, independently of the website."""
        with self._lock:
            if self.mode is not Mode.MUSIC_QUIZ or self.quiz_winner is None:
                return
            now = time.monotonic()
            if now < self._quiz_poll_at:
                return
            self._quiz_poll_at = now + 0.3
            try:
                status = self.services.quiz_media.playback_status()
            except Exception as error:
                self.quiz_error = f"Cannot read phone playback: {error}"
                return
            if status in {"paused", "stopped"}:
                self._quiz_saw_pause = True
            elif status == "playing" and self._quiz_saw_pause:
                if self.services.buzzer is not None:
                    self.services.buzzer.stop()
                self._reset_quiz()
            elif now - self._quiz_buzz_at > 3 and not self._quiz_saw_pause:
                self.quiz_error = "Phone has not confirmed pause. Pause and resume music on your phone"

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
                "nfc": self.services.nfc.status() if self.services.nfc else None,
                "bluetooth_active": self.services.bluetooth.active,
                "quiz": {"winner": self.quiz_winner, "error": self.quiz_error},
            }

    def close(self) -> None:
        with self._lock:
            self._leave_current_mode()
            self.mode = Mode.IDLE
            self.message = "Ready"

    def _leave_current_mode(self) -> None:
        if self.mode is Mode.LOCAL_FILES:
            self.services.audio.stop()
        if self.mode in {Mode.BLUETOOTH, Mode.MUSIC_QUIZ}:
            self.services.bluetooth.stop()
        if self.mode is Mode.MUSIC_QUIZ:
            if self.services.buzzer is not None:
                self.services.buzzer.stop()
            self.services.quiz_media.reset()
            self.services.rgb.set_mode(self._previous_rgb)
            self.quiz_winner = None
            self.quiz_error = None
            self._quiz_saw_pause = False
        if self.mode is Mode.NFC and self.services.nfc is not None:
            self.services.nfc.stop()
