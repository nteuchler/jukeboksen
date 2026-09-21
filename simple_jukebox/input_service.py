from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Deque, Dict, List, Tuple

PIN_MAP = {
    "VOLUME_UP": 27,
    "VOLUME_DOWN": 22,
    "NAV_LEFT": 23,
    "NAV_RIGHT": 24,
    "EXTRA_BUTTON": 25,
    "ARCADE_1": 5,
    "ARCADE_2": 6,
    "COIN": 12,
    "ENCODER_A": 4,
    "ENCODER_B": 17,
    "ENCODER_PRESS": 16,
}

LOGGER = logging.getLogger(__name__)


class InputService:
    """Read configured GPIO inputs and keep a recent event log.

    This service uses RPi.GPIO when available, otherwise falls back to a
    no-op mock that keeps an empty log. Events are recorded on falling
    transitions (active LOW buttons) as described in `HARDWARE_PINOUT.md`.
    Button values must remain stable for the debounce interval. Encoder A/B
    use quadrature transition decoding instead so short rotation pulses survive.
    """

    def __init__(
        self,
        max_events: int = 1024,
        gpio=None,
        debounce_seconds: float = 0.02,
        poll_seconds: float = 0.001,
        on_encoder_step: Callable[[int], None] | None = None,
    ) -> None:
        self._max_events = max_events
        self._on_encoder_step = on_encoder_step
        self._encoder_previous: int | None = None
        self._encoder_steps = 0
        self._events: Deque[Tuple[float, str]] = deque(maxlen=max_events)
        self._states: Dict[str, bool] = {name: False for name in PIN_MAP}
        self._lock = threading.RLock()
        self._running = False
        self._use_gpio = False
        self._gpio = gpio
        self._error: str | None = None
        self._configured_inputs: set[str] = set()
        self._debounce_seconds = debounce_seconds
        self._poll_seconds = poll_seconds
        self._candidates: Dict[str, bool] = dict(self._states)
        self._candidate_since: Dict[str, float] = {}
        self._armed: Dict[str, bool] = {name: False for name in PIN_MAP}
        self._poll_thread: threading.Thread | None = None
        self._stop_polling = threading.Event()

    def start(self) -> None:
        self._error = None
        self._encoder_previous = None
        self._encoder_steps = 0
        self._configured_inputs.clear()
        self._stop_polling.clear()
        if self._gpio is None:
            try:
                import RPi.GPIO as GPIO  # type: ignore

                self._gpio = GPIO
            except (ImportError, RuntimeError) as error:
                self._use_gpio = False
                self._error = f"GPIO backend unavailable: {error}"
                LOGGER.warning(self._error)
                self._running = True
                return

        try:
            self._gpio.setmode(self._gpio.BCM)
            self._use_gpio = True
        except Exception as error:
            self._use_gpio = False
            self._error = f"GPIO initialization failed: {error}"
            LOGGER.exception(self._error)
            self._running = True
            return

        if self._use_gpio:
            for name, pin in PIN_MAP.items():
                try:
                    self._gpio.setup(pin, self._gpio.IN, pull_up_down=self._gpio.PUD_UP)
                    pressed = not bool(self._gpio.input(pin))
                    with self._lock:
                        self._candidates[name] = pressed
                        self._candidate_since[name] = time.monotonic()
                        self._armed[name] = not pressed
                    self._configured_inputs.add(name)
                except Exception as error:
                    message = f"Could not configure {name} on BCM GPIO{pin}: {error}"
                    self._error = f"{self._error}; {message}" if self._error else message
                    LOGGER.exception(message)

        self._running = True
        if self._configured_inputs:
            self._poll_thread = threading.Thread(
                target=self._poll_inputs,
                name="jukebox-gpio-inputs",
                daemon=True,
            )
            self._poll_thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_polling.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None
        if self._use_gpio and self._gpio:
            try:
                self._gpio.cleanup(list(PIN_MAP.values()))
            except Exception:
                pass

    def _poll_inputs(self) -> None:
        while self._running:
            self._poll_once(time.monotonic())
            self._stop_polling.wait(self._poll_seconds)

    def _poll_once(self, now: float) -> None:
        if not self._use_gpio or self._gpio is None:
            return
        self._poll_encoder()
        for name in tuple(self._configured_inputs):
            if name in {"ENCODER_A", "ENCODER_B"}:
                continue
            pin = PIN_MAP[name]
            try:
                pressed = not bool(self._gpio.input(pin))
            except Exception as error:
                LOGGER.warning("Could not read %s on BCM GPIO%s: %s", name, pin, error)
                continue
            with self._lock:
                if pressed != self._candidates[name]:
                    self._candidates[name] = pressed
                    self._candidate_since[name] = now
                elif (
                    pressed != self._states[name]
                    and now - self._candidate_since[name] >= self._debounce_seconds
                ):
                    self._states[name] = pressed
                    if pressed:
                        if self._armed[name]:
                            self._events.append((time.time(), name))
                    else:
                        self._armed[name] = True

    def _poll_encoder(self) -> None:
        if not {"ENCODER_A", "ENCODER_B"} <= self._configured_inputs:
            return
        try:
            a = bool(self._gpio.input(PIN_MAP["ENCODER_A"]))
            b = bool(self._gpio.input(PIN_MAP["ENCODER_B"]))
        except Exception as error:
            LOGGER.warning("Could not read encoder: %s", error)
            return
        current = (int(a) << 1) | int(b)
        previous = self._encoder_previous
        self._encoder_previous = current
        with self._lock:
            self._states["ENCODER_A"] = not a
            self._states["ENCODER_B"] = not b
        if previous is None or previous == current:
            return
        # Adjacent quadrature transitions cancel contact bounce. A full cycle
        # returning to both pull-ups HIGH produces one step.
        transitions = {(3, 1): 1, (1, 0): 1, (0, 2): 1, (2, 3): 1,
                       (1, 3): -1, (0, 1): -1, (2, 0): -1, (3, 2): -1}
        delta = transitions.get((previous, current))
        if delta is None:
            self._encoder_steps = 0
            return
        self._encoder_steps += delta
        if current != 3:
            return
        steps = self._encoder_steps
        self._encoder_steps = 0
        if abs(steps) != 4:
            return
        direction = 1 if steps > 0 else -1
        with self._lock:
            self._events.append((time.time(), "ENCODER_RIGHT" if direction > 0 else "ENCODER_LEFT"))
        if self._on_encoder_step is not None:
            try:
                self._on_encoder_step(direction)
            except Exception:
                LOGGER.exception("Encoder volume command failed")

    def get_states(self) -> Dict[str, bool]:
        with self._lock:
            return dict(self._states)

    def status(self) -> Dict[str, object]:
        """Return enough diagnostics to distinguish real GPIO from mock mode."""
        return {
            "running": self._running,
            "backend": "RPi.GPIO" if self._use_gpio else "mock",
            "configured_inputs": sorted(self._configured_inputs),
            "error": self._error,
        }

    def get_events_since(self, seconds: int = 1800) -> List[Dict[str, str]]:
        cutoff = time.time() - seconds
        out: List[Dict[str, str]] = []
        with self._lock:
            for ts, name in list(self._events):
                if ts >= cutoff:
                    out.append({"time": datetime.fromtimestamp(ts, timezone.utc).isoformat(), "event": name})
        return out

    def simulate_event(self, name: str) -> None:
        """Programmatically simulate an input event (useful for testing)."""
        with self._lock:
            ts = time.time()
            self._events.append((ts, name))
            # set simulated transient state
            self._states[name] = True
            # schedule reset shortly after so UI shows transient press
            def _reset():
                time.sleep(0.25)
                with self._lock:
                    self._states[name] = False

            t = threading.Thread(target=_reset, daemon=True)
            t.start()
