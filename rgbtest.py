import random
import time
import math
import os
import select
import subprocess
import threading
from array import array

from rpi_ws281x import PixelStrip, Color

# Configuration
LED_COUNT = 110
LED_PIN = 10
LED_BRIGHTNESS = 50  # 0–255
FRAME_DELAY = 0.03
COOLING = 0.03
SPARK_PROBABILITY = 0.65
SIDE_FLAME_LENGTH = min(30, LED_COUNT // 2)
BASE_HEAT = 0.95
EQUALIZER_NOISE_FLOOR_DB = -55.0
EQUALIZER_FULL_SCALE_DB = -12.0

# Initialize strip
strip = PixelStrip(LED_COUNT, LED_PIN, brightness=LED_BRIGHTNESS)
strip.begin()

# Optional audio capture (falls back to random levels if unavailable)
SD_AVAILABLE = False
try:
    import sounddevice as sd
    import numpy as np

    SD_AVAILABLE = True
except Exception:
    SD_AVAILABLE = False


def heat_to_color(heat: float) -> Color:
    heat = max(0.0, min(1.0, heat))
    if heat < 0.33:
        return Color(int(180 * heat * 3), 0, 0)
    if heat < 0.66:
        level = (heat - 0.33) * 3
        return Color(255, int(120 * level), 0)
    level = (heat - 0.66) * 3
    return Color(255, int(140 + 115 * level), int(40 + 215 * level))


def render_flame_frame(left_heat, right_heat):
    # left side: index 0..n-1, right side: index LED_COUNT-1..LED_COUNT-n
    for offset, heat in enumerate(left_heat):
        strip.setPixelColor(offset, heat_to_color(heat))

    for offset, heat in enumerate(right_heat):
        strip.setPixelColor(LED_COUNT - 1 - offset, heat_to_color(heat))

    # clear middle
    for pixel in range(SIDE_FLAME_LENGTH, LED_COUNT - SIDE_FLAME_LENGTH):
        strip.setPixelColor(pixel, Color(0, 0, 0))

    strip.show()


def step_flame(heat_band):
    # cool
    for i in range(len(heat_band)):
        heat_band[i] = max(0.0, heat_band[i] - random.uniform(0.0, COOLING))

    # inject base
    heat_band[0] = max(heat_band[0], BASE_HEAT * random.uniform(0.85, 1.0))
    if len(heat_band) > 1:
        heat_band[1] = max(heat_band[1], BASE_HEAT * random.uniform(0.45, 0.8))
    if len(heat_band) > 2:
        heat_band[2] = max(heat_band[2], BASE_HEAT * random.uniform(0.2, 0.5))

    # propagate upwards
    for i in range(len(heat_band) - 1, 0, -1):
        heat_band[i] = (
            heat_band[i] * 0.35
            + heat_band[i - 1] * 0.45
            + heat_band[min(i + 1, len(heat_band) - 1)] * 0.2
        )

    # occasional sparks
    if random.random() < SPARK_PROBABILITY:
        spark_strength = random.uniform(0.8, 1.0)
        spread = max(4, len(heat_band) // 3)
        for offset in range(spread):
            falloff = 1.0 - (offset / spread)
            flicker = random.uniform(0.85, 1.0)
            heat_band[offset] = max(heat_band[offset], spark_strength * falloff * flicker)


def run_flame(duration_s: float | None = None, stop_event=None):
    if stop_event is None:
        stop_event = threading.Event()
    left = [0.0 for _ in range(SIDE_FLAME_LENGTH)]
    right = [0.0 for _ in range(SIDE_FLAME_LENGTH)]
    end = None if duration_s is None else time.time() + duration_s
    while not stop_event.is_set() and (end is None or time.time() < end):
        step_flame(left)
        step_flame(right)
        render_flame_frame(left, right)
        stop_event.wait(FRAME_DELAY)


def run_party(duration_s: float | None = None, stop_event=None):
    if stop_event is None:
        stop_event = threading.Event()
    # flashing and fading party colors across whole strip
    colors = [
        (255, 20, 147),
        (0, 200, 255),
        (0, 255, 100),
        (255, 140, 0),
        (200, 0, 255),
    ]
    end = None if duration_s is None else time.time() + duration_s
    t = 0.0
    while not stop_event.is_set() and (end is None or time.time() < end):
        # choose base color and next color
        base = random.choice(colors)
        nxt = random.choice(colors)
        steps = int(max(6, 0.3 / FRAME_DELAY))
        for s in range(steps):
            if stop_event.is_set() or (end is not None and time.time() >= end):
                return
            mix = s / max(1, steps - 1)
            r = int(base[0] * (1 - mix) + nxt[0] * mix)
            g = int(base[1] * (1 - mix) + nxt[1] * mix)
            b = int(base[2] * (1 - mix) + nxt[2] * mix)
            # slight pulse
            pulse = 0.5 + 0.5 * math.sin(t)
            r = int(r * pulse)
            g = int(g * pulse)
            b = int(b * pulse)
            color = Color(r, g, b)
            for i in range(LED_COUNT):
                strip.setPixelColor(i, color)
            strip.show()
            t += 0.3
            stop_event.wait(FRAME_DELAY)


def _pulse_environments():
    """Return usable PulseAudio sessions, preferring the invoking user."""
    base_env = os.environ.copy()
    candidates = []

    sudo_uid = base_env.get("SUDO_UID")
    sudo_user = base_env.get("SUDO_USER")
    if os.geteuid() == 0 and sudo_uid:
        runtime_dir = f"/run/user/{sudo_uid}"
        socket = f"{runtime_dir}/pulse/native"
        if os.path.exists(socket):
            user_env = base_env.copy()
            user_env["XDG_RUNTIME_DIR"] = runtime_dir
            user_env["PULSE_SERVER"] = f"unix:{socket}"
            if sudo_user:
                cookie = f"/home/{sudo_user}/.config/pulse/cookie"
                if os.path.exists(cookie):
                    user_env["PULSE_COOKIE"] = cookie
            candidates.append(user_env)

    lightdm_socket = "/run/user/104/pulse/native"
    lightdm_cookie = "/var/lib/lightdm/.config/pulse/cookie"
    if (
        os.geteuid() == 0
        and os.path.exists(lightdm_socket)
        and os.path.exists(lightdm_cookie)
    ):
        lightdm_env = base_env.copy()
        lightdm_env["XDG_RUNTIME_DIR"] = "/run/user/104"
        lightdm_env["PULSE_SERVER"] = f"unix:{lightdm_socket}"
        lightdm_env["PULSE_COOKIE"] = lightdm_cookie
        candidates.append(lightdm_env)

    if not candidates:
        candidates.append(base_env)
    return candidates


def _find_capture_device(pulse_envs):
    """Find the Bluetooth playback monitor across all audio sessions."""
    fallback = (pulse_envs[0], "@DEFAULT_MONITOR@")
    for pulse_env in pulse_envs:
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True,
                text=True,
                timeout=2,
                env=pulse_env,
                check=False,
            )
            sources = [
                fields[1]
                for line in result.stdout.splitlines()
                if len(fields := line.split()) >= 2
            ]
            # A phone playing to this machine is an A2DP sink. PulseAudio
            # exposes its playback as bluez_sink.<address>.*.monitor.
            bluetooth_monitors = [
                name
                for name in sources
                if name.startswith("bluez_sink") and name.endswith(".monitor")
            ]
            if bluetooth_monitors:
                return pulse_env, bluetooth_monitors[0]

            # Keep support for profiles which expose Bluetooth as an input.
            bluetooth_sources = [
                name for name in sources if name.startswith("bluez_source")
            ]
            if bluetooth_sources:
                return pulse_env, bluetooth_sources[0]
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
    return fallback


def _playback_level_reader(rate, chunk):
    """Yield RMS levels from the audio currently playing on the default sink.

    PipeWire and PulseAudio expose the output mix through @DEFAULT_MONITOR@.
    This includes audio received by the Bluetooth speaker, unlike recording
    from sounddevice's default (usually microphone) input.
    """
    process = None
    try:
        pulse_envs = _pulse_environments()

        device = None
        active_server = None
        next_discovery = 0.0
        raw_buffer = bytearray()
        while True:
            now = time.monotonic()
            if now >= next_discovery:
                pulse_env, discovered_device = _find_capture_device(pulse_envs)
                discovered_server = pulse_env.get("PULSE_SERVER", "session default")
                next_discovery = now + 1.0
                if discovered_device != device or discovered_server != active_server:
                    if process is not None:
                        process.terminate()
                        process.wait(timeout=1)
                    device = discovered_device
                    active_server = discovered_server
                    raw_buffer.clear()
                    print(f"Audio capture server: {active_server}", flush=True)
                    print(f"Audio capture device: {device}", flush=True)
                    process = subprocess.Popen(
                        [
                            "parec",
                            f"--device={device}",
                            "--format=float32le",
                            f"--rate={rate}",
                            "--channels=1",
                            "--raw",
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=pulse_env,
                    )

            readable, _, _ = select.select([process.stdout], [], [], FRAME_DELAY)
            if not readable:
                yield 0.0
                continue

            raw = os.read(process.stdout.fileno(), chunk * 4 - len(raw_buffer))
            if not raw:
                error = process.stderr.read().decode(errors="replace").strip()
                print(f"parec stopped: {error or 'no audio data'}", flush=True)
                process.wait(timeout=1)
                process = None
                device = None
                next_discovery = 0.0
                yield 0.0
                continue
            raw_buffer.extend(raw)
            if len(raw_buffer) < chunk * 4:
                yield 0.0
                continue

            samples = array("f")
            samples.frombytes(raw_buffer)
            raw_buffer.clear()
            yield math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    except (FileNotFoundError, OSError):
        return
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()


def clear_strip():
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def _level_to_height(level):
    """Convert linear RMS to an LED height using a useful audio dB range."""
    if level <= 0.0:
        return 0

    db = 20.0 * math.log10(level)
    span = EQUALIZER_FULL_SCALE_DB - EQUALIZER_NOISE_FLOOR_DB
    normalized = (db - EQUALIZER_NOISE_FLOOR_DB) / span
    normalized = max(0.0, min(1.0, normalized))
    return int(round(normalized * SIDE_FLAME_LENGTH))


def run_equalizer(stop_event=None):
    """Run the playback-reactive LEDs until stopped.

    ``stop_event`` lets another program (such as bluewalla.py) own the
    equalizer lifecycle. Ctrl-C remains supported when run standalone.
    """
    if stop_event is None:
        stop_event = threading.Event()

    # reactive equalizer: map audio RMS to height on each side
    left = [0.0 for _ in range(SIDE_FLAME_LENGTH)]
    right = [0.0 for _ in range(SIDE_FLAME_LENGTH)]
    RATE = 22050
    CHUNK = 1024
    levels = None
    smoothed_level = 0.0
    report_at = time.monotonic() + 2.0
    peak_since_report = 0.0

    try:
        levels = _playback_level_reader(RATE, CHUNK)
        print("Equalizer searching for Bluetooth playback audio", flush=True)
        while not stop_event.is_set():
            try:
                level = next(levels)
            except StopIteration:
                levels = None

            if levels is None and SD_AVAILABLE:
                # Useful fallback on systems without PulseAudio/PipeWire tools.
                data = sd.rec(frames=CHUNK, samplerate=RATE, channels=1, dtype='float32')
                sd.wait()
                level = float(np.sqrt(np.mean(np.square(data))))
            elif levels is None:
                # No capture backend: keep the strip dark instead of pretending
                # random values are music.
                level = 0.0

            # Fast attack and gentle release prevent jitter while retaining beats.
            if level > smoothed_level:
                smoothed_level = level
            else:
                smoothed_level = smoothed_level * 0.82 + level * 0.18
            height = _level_to_height(smoothed_level)
            peak_since_report = max(peak_since_report, level)

            if time.monotonic() >= report_at:
                print(
                    f"Equalizer audio peak RMS={peak_since_report:.6f}, "
                    f"LED height={height}/{SIDE_FLAME_LENGTH}",
                    flush=True,
                )
                peak_since_report = 0.0
                report_at = time.monotonic() + 2.0
            # make a quick peak that decays
            for i in range(SIDE_FLAME_LENGTH):
                target = 1.0 if i < height else 0.0
                left[i] = max(target, left[i] * 0.9)
                right[i] = max(target, right[i] * 0.9)

            render_flame_frame(left, right)
            stop_event.wait(FRAME_DELAY)
    except KeyboardInterrupt:
        return
    finally:
        if levels is not None:
            levels.close()


if __name__ == '__main__':
    try:
        print(f"Starting rgbtest: LED_COUNT={LED_COUNT}, SIDE_FLAME_LENGTH={SIDE_FLAME_LENGTH}")
        print(f"Sounddevice fallback available: {SD_AVAILABLE}")
        # quick startup check: short red flash
        for i in range(LED_COUNT):
            strip.setPixelColor(i, Color(60, 0, 0))
        strip.show()
        time.sleep(0.6)

        # 10s flame
        run_flame(10.0)
        # 8s party
        run_party(8.0)
        # then equalizer until Ctrl-C
        run_equalizer()
    finally:
        clear_strip()
