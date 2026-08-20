"""RGB effects owned by the simple jukebox state-machine application."""

from __future__ import annotations

import math
import os
import random
import select
import subprocess
import threading
import time
from array import array

from rpi_ws281x import Color, PixelStrip


LED_COUNT = 110
LED_PIN = 10
LED_BRIGHTNESS = 50
FRAME_DELAY = 0.03
SIDE_LENGTH = min(30, LED_COUNT // 2)

# Calibrated from the jukebox's AUX monitor, where normal playback measures
# roughly -20 to -13 dB RMS. Keeping that range away from either limit makes
# verses, choruses, and beats visibly grow and shrink instead of saturating.
EQUALIZER_NOISE_FLOOR_DB = -26.0
EQUALIZER_FULL_SCALE_DB = -11.0
EQUALIZER_RESPONSE_CURVE = 0.85

_strip = None
_strip_lock = threading.Lock()


def _get_strip():
    """Initialize the Raspberry Pi hardware only when an effect is selected."""
    global _strip
    with _strip_lock:
        if _strip is None:
            _strip = PixelStrip(LED_COUNT, LED_PIN, brightness=LED_BRIGHTNESS)
            _strip.begin()
        return _strip


def _heat_color(heat: float) -> Color:
    heat = max(0.0, min(1.0, heat))
    if heat < 0.33:
        return Color(int(180 * heat * 3), 0, 0)
    if heat < 0.66:
        level = (heat - 0.33) * 3
        return Color(255, int(120 * level), 0)
    level = (heat - 0.66) * 3
    return Color(255, int(140 + 115 * level), int(40 + 215 * level))


def _render_sides(left: list[float], right: list[float]) -> None:
    strip = _get_strip()
    for offset, heat in enumerate(left):
        strip.setPixelColor(offset, _heat_color(heat))
    for offset, heat in enumerate(right):
        strip.setPixelColor(LED_COUNT - 1 - offset, _heat_color(heat))
    for pixel in range(SIDE_LENGTH, LED_COUNT - SIDE_LENGTH):
        strip.setPixelColor(pixel, Color(0, 0, 0))
    strip.show()


def _step_flame(heat: list[float]) -> None:
    for index in range(len(heat)):
        heat[index] = max(0.0, heat[index] - random.uniform(0.0, 0.03))
    heat[0] = max(heat[0], 0.95 * random.uniform(0.85, 1.0))
    if len(heat) > 1:
        heat[1] = max(heat[1], 0.95 * random.uniform(0.45, 0.8))
    if len(heat) > 2:
        heat[2] = max(heat[2], 0.95 * random.uniform(0.2, 0.5))
    for index in range(len(heat) - 1, 0, -1):
        heat[index] = (
            heat[index] * 0.35
            + heat[index - 1] * 0.45
            + heat[min(index + 1, len(heat) - 1)] * 0.2
        )
    if random.random() < 0.65:
        strength = random.uniform(0.8, 1.0)
        spread = max(4, len(heat) // 3)
        for offset in range(spread):
            heat[offset] = max(
                heat[offset],
                strength * (1.0 - offset / spread) * random.uniform(0.85, 1.0),
            )


def run_flame(stop_event: threading.Event) -> None:
    left = [0.0] * SIDE_LENGTH
    right = [0.0] * SIDE_LENGTH
    while not stop_event.is_set():
        _step_flame(left)
        _step_flame(right)
        _render_sides(left, right)
        stop_event.wait(FRAME_DELAY)


def run_party(stop_event: threading.Event) -> None:
    strip = _get_strip()
    colors = [
        (255, 20, 147), (0, 200, 255), (0, 255, 100),
        (255, 140, 0), (200, 0, 255),
    ]
    phase = 0.0
    while not stop_event.is_set():
        start = random.choice(colors)
        end = random.choice(colors)
        for step in range(10):
            if stop_event.is_set():
                return
            mix = step / 9
            pulse = 0.5 + 0.5 * math.sin(phase)
            color = Color(*(
                int((start[channel] * (1 - mix) + end[channel] * mix) * pulse)
                for channel in range(3)
            ))
            for pixel in range(LED_COUNT):
                strip.setPixelColor(pixel, color)
            strip.show()
            phase += 0.3
            stop_event.wait(FRAME_DELAY)


def _pulse_environments() -> list[dict[str, str]]:
    environment = os.environ.copy()
    sudo_uid = environment.get("SUDO_UID")
    if os.geteuid() != 0 or not sudo_uid:
        return [environment]
    runtime = f"/run/user/{sudo_uid}"
    socket = f"{runtime}/pulse/native"
    if not os.path.exists(socket):
        return [environment]
    user_environment = environment.copy()
    user_environment["XDG_RUNTIME_DIR"] = runtime
    user_environment["PULSE_SERVER"] = f"unix:{socket}"
    sudo_user = environment.get("SUDO_USER")
    if sudo_user:
        cookie = f"/home/{sudo_user}/.config/pulse/cookie"
        if os.path.exists(cookie):
            user_environment["PULSE_COOKIE"] = cookie
    return [user_environment]


def _pactl(environment: dict[str, str], *arguments: str) -> str:
    result = subprocess.run(
        ["pactl", *arguments], capture_output=True, text=True, timeout=2,
        env=environment, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _capture_device(environments):
    """Select AUX for local/looped-back audio, or direct Bluetooth audio."""
    for environment in environments:
        default_sink = _pactl(environment, "get-default-sink")
        sources = [
            fields[1]
            for line in _pactl(environment, "list", "short", "sources").splitlines()
            if len(fields := line.split()) >= 2
        ]
        monitor = f"{default_sink}.monitor" if default_sink else ""
        sink_indexes = {
            fields[1]: fields[0]
            for line in _pactl(environment, "list", "short", "sinks").splitlines()
            if len(fields := line.split()) >= 2
        }
        default_index = sink_indexes.get(default_sink)
        sink_inputs = [
            fields
            for line in _pactl(environment, "list", "short", "sink-inputs").splitlines()
            if len(fields := line.split()) >= 2
        ]
        if monitor in sources and default_index is not None and any(
            fields[1] == default_index for fields in sink_inputs
        ):
            return environment, monitor
        bluetooth = [
            name for name in sources
            if name.startswith("bluez_source")
            or (name.startswith("bluez_sink") and name.endswith(".monitor"))
        ]
        if bluetooth:
            return environment, bluetooth[0]
        if monitor in sources:
            return environment, monitor
    return environments[0], "@DEFAULT_MONITOR@"


def _levels(stop_event: threading.Event, rate: int = 22050, chunk: int = 1024):
    environments = _pulse_environments()
    process = None
    device = None
    server = None
    buffer = bytearray()
    discover_at = 0.0
    try:
        while not stop_event.is_set():
            now = time.monotonic()
            if now >= discover_at:
                environment, found = _capture_device(environments)
                found_server = environment.get("PULSE_SERVER", "session default")
                discover_at = now + 1.0
                if found != device or found_server != server:
                    if process is not None:
                        process.terminate()
                        process.wait(timeout=1)
                    device, server = found, found_server
                    buffer.clear()
                    process = subprocess.Popen(
                        ["parec", f"--device={device}", "--format=float32le",
                         f"--rate={rate}", "--channels=1", "--raw"],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        env=environment,
                    )
            if process is None or process.stdout is None:
                yield 0.0
                continue
            readable, _, _ = select.select([process.stdout], [], [], FRAME_DELAY)
            if not readable:
                yield 0.0
                continue
            raw = os.read(process.stdout.fileno(), chunk * 4 - len(buffer))
            if not raw:
                process.wait(timeout=1)
                process = None
                device = None
                discover_at = 0.0
                yield 0.0
                continue
            buffer.extend(raw)
            if len(buffer) < chunk * 4:
                yield 0.0
                continue
            samples = array("f")
            samples.frombytes(buffer)
            buffer.clear()
            yield math.sqrt(sum(value * value for value in samples) / len(samples))
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()


def level_to_height(level: float) -> int:
    if level <= 0.0:
        return 0
    decibels = 20.0 * math.log10(level)
    span = EQUALIZER_FULL_SCALE_DB - EQUALIZER_NOISE_FLOOR_DB
    normalized = (decibels - EQUALIZER_NOISE_FLOOR_DB) / span
    normalized = max(0.0, min(1.0, normalized)) ** EQUALIZER_RESPONSE_CURVE
    return round(normalized * SIDE_LENGTH)


def run_equalizer(stop_event: threading.Event) -> None:
    left = [0.0] * SIDE_LENGTH
    right = [0.0] * SIDE_LENGTH
    smoothed = 0.0
    for level in _levels(stop_event):
        if stop_event.is_set():
            break
        smoothed = level if level > smoothed else smoothed * 0.82 + level * 0.18
        height = level_to_height(smoothed)
        for index in range(SIDE_LENGTH):
            target = 1.0 if index < height else 0.0
            left[index] = max(target, left[index] * 0.88)
            right[index] = max(target, right[index] * 0.88)
        _render_sides(left, right)
        stop_event.wait(FRAME_DELAY)


def clear_strip() -> None:
    strip = _get_strip()
    for pixel in range(LED_COUNT):
        strip.setPixelColor(pixel, Color(0, 0, 0))
    strip.show()
