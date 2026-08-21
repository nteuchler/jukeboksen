from __future__ import annotations

import subprocess
import threading
from pathlib import Path
import re


class VlcPlayer:
    """Control one VLC process at a time."""

    SUPPORTED_FILES = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}

    def __init__(self, media_folder: Path) -> None:
        self.media_folder = media_folder.resolve()
        self.process: subprocess.Popen[str] | None = None
        self.current_track: str | None = None
        self.muted = False

    def tracks(self) -> list[str]:
        return sorted(
            path.name
            for path in self.media_folder.iterdir()
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_FILES
        )

    def play(self, track: str) -> None:
        if Path(track).name != track or track not in self.tracks():
            raise ValueError("Choose a file from the available tracks")
        self.stop()
        self.process = subprocess.Popen(
            ["cvlc", "--intf", "rc", "--play-and-exit", "--quiet", str(self.media_folder / track)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self.current_track = track
        self.muted = False

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process = None
        self.current_track = None
        self.muted = False

    def toggle_mute(self) -> bool:
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("Nothing is playing")
        self.muted = not self.muted
        if not self.process.stdin:
            raise RuntimeError("VLC controls are unavailable")
        self.process.stdin.write("volume 0\n" if self.muted else "volume 256\n")
        self.process.stdin.flush()
        return self.muted

    @property
    def playing(self) -> bool:
        if self.process and self.process.poll() is not None:
            self.process = None
            self.current_track = None
            self.muted = False
        return self.process is not None


class BluetoothSpeaker:
    """Small wrapper around bluetoothctl, based on BluetoohSpeaker.py."""

    def __init__(self, name: str = "Jukeboks") -> None:
        self.name = name
        self.process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None

    def _send(self, command: str) -> None:
        if self.process and self.process.stdin:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()

    def _read_output(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            if "Device " in line and ("Connected: yes" in line or "Paired: yes" in line):
                parts = line.split()
                if len(parts) >= 2:
                    self._send(f"trust {parts[1]}")

    def start(self) -> None:
        if self.active:
            return
        self.process = subprocess.Popen(
            ["bluetoothctl", "--agent", "NoInputNoOutput"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()
        for command in (
            "power on",
            f"system-alias {self.name}",
            "pairable on",
            "discoverable-timeout 0",
            "discoverable on",
        ):
            self._send(command)

    def stop(self) -> None:
        if not self.process:
            return
        if self.process.poll() is None:
            self._send("discoverable off")
            self._send("pairable off")
            # Discovery settings do not stop an existing A2DP connection.
            # Powering the adapter off disconnects the phone and removes its
            # PulseAudio source/loopback before local VLC playback starts.
            self._send("power off")
            self._send("quit")
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=2)
        self.process = None

    @property
    def active(self) -> bool:
        return self.process is not None and self.process.poll() is None


class SystemVolume:
    """Control the volume of PulseAudio's current default output."""

    def get(self) -> int:
        result = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        match = re.search(r"(\d+)%", result.stdout)
        if not match:
            raise RuntimeError("Could not read the output volume")
        return int(match.group(1))

    def set(self, volume: int) -> None:
        if isinstance(volume, bool) or not isinstance(volume, int) or not 0 <= volume <= 100:
            raise ValueError("Volume must be a whole number from 0 to 100")
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )


class RgbController:
    """Own the one active RGB effect thread."""

    MODES = {"off", "flame", "party", "equalizer"}

    def __init__(self) -> None:
        self.mode = "off"
        self.error: str | None = None
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._rgb_module = None

    def set_mode(self, mode: str) -> None:
        if mode not in self.MODES:
            raise ValueError(f"Unknown RGB mode: {mode}")
        with self._lock:
            self._stop_current()
            self.mode = mode
            self.error = None
            if mode == "off":
                if self._rgb_module is not None:
                    self._rgb_module.clear_strip()
                return
            self._stop_event = threading.Event()
            self._thread = threading.Thread(
                target=self._run_mode,
                args=(mode, self._stop_event),
                name=f"rgb-{mode}",
                daemon=True,
            )
            self._thread.start()

    def status(self) -> dict[str, str | None]:
        with self._lock:
            return {"mode": self.mode, "error": self.error}

    def close(self) -> None:
        with self._lock:
            self._stop_current()
            self.mode = "off"
            if self._rgb_module is not None:
                self._rgb_module.clear_strip()

    def _stop_current(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._stop_event = None
        self._thread = None

    def _run_mode(self, mode: str, stop_event: threading.Event) -> None:
        try:
            if self._rgb_module is None:
                from simple_jukebox import rgb

                self._rgb_module = rgb
            runners = {
                "flame": self._rgb_module.run_flame,
                "party": self._rgb_module.run_party,
                "equalizer": self._rgb_module.run_equalizer,
            }
            runners[mode](stop_event=stop_event)
        except Exception as error:
            if self._stop_event is stop_event:
                self.error = str(error)
                self.mode = "off"
        finally:
            # Never leave the last rendered frame looking like a frozen effect
            # when capture exits or an RGB worker fails.
            if self._rgb_module is not None:
                try:
                    self._rgb_module.clear_strip()
                except Exception:
                    pass
