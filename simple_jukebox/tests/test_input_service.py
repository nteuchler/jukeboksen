import time
import pytest

from simple_jukebox.input_service import InputService


@pytest.mark.parametrize("sequence, expected", [
    ([3, 1, 0, 2, 3], [1]),
    ([3, 2, 0, 1, 3], [-1]),
    ([3, 1, 3, 1, 0, 1, 0, 2, 3], [1]),
    ([3, 1, 0, 1, 3], []),
    ([3, 0, 2, 3], []),
])
def test_encoder_direction_bounce_and_invalid_transitions(sequence, expected):
    gpio = FakeGPIO()
    steps = []
    service = InputService(gpio=gpio, on_encoder_step=steps.append)
    service._configured_inputs = {"ENCODER_A", "ENCODER_B"}
    for state in sequence:
        gpio.values[4] = bool(state & 2)
        gpio.values[17] = bool(state & 1)
        service._poll_encoder()
    assert steps == expected
    assert len(service.get_events_since(1)) == len(expected)


class FakeGPIO:
    BCM = "BCM"
    IN = "IN"
    PUD_UP = "PUD_UP"
    def __init__(self):
        self.values = {5: True, 6: True}
        self.setups = []

    def setmode(self, mode):
        assert mode == self.BCM

    def setup(self, pin, direction, pull_up_down):
        self.setups.append((pin, direction, pull_up_down))
        self.values.setdefault(pin, True)

    def input(self, pin):
        return self.values[pin]

    def cleanup(self, pins):
        pass


def test_arcade_buttons_use_documented_bcm_pins_pullups_and_active_low():
    gpio = FakeGPIO()
    service = InputService(gpio=gpio, poll_seconds=10)

    service.start()
    gpio.values[5] = False
    service._poll_once(1.0)
    service._poll_once(1.021)

    assert (5, gpio.IN, gpio.PUD_UP) in gpio.setups
    assert (6, gpio.IN, gpio.PUD_UP) in gpio.setups
    assert service.get_states()["ARCADE_1"] is True
    assert service.get_states()["ARCADE_2"] is False
    assert service.status()["backend"] == "RPi.GPIO"
    service.stop()


def test_arcade_press_is_logged_only_after_it_is_stably_low():
    gpio = FakeGPIO()
    service = InputService(gpio=gpio, poll_seconds=10)
    service.start()

    gpio.values[6] = False
    service._poll_once(2.0)
    gpio.values[6] = True
    service._poll_once(2.02)  # a short low glitch is rejected
    assert service.get_events_since(1) == []

    gpio.values[6] = False
    service._poll_once(3.0)
    service._poll_once(3.019)
    assert service.get_events_since(1) == []
    service._poll_once(3.021)

    assert service.get_events_since(1)[-1]["event"] == "ARCADE_2"
    service.stop()


@pytest.mark.parametrize("name, pin", [("ARCADE_1", 5), ("ENCODER_PRESS", 16)])
def test_release_is_also_debounced_and_does_not_stick_pressed(name, pin):
    gpio = FakeGPIO()
    service = InputService(gpio=gpio, poll_seconds=10)
    service.start()

    assert (pin, gpio.IN, gpio.PUD_UP) in gpio.setups
    gpio.values[pin] = False
    service._poll_once(4.0)
    service._poll_once(4.021)
    assert service.get_states()[name] is True

    gpio.values[pin] = True
    service._poll_once(5.0)
    service._poll_once(5.021)
    assert service.get_states()[name] is False
    service.stop()


@pytest.mark.parametrize("name, pin", [("ARCADE_1", 5), ("ENCODER_PRESS", 16)])
def test_input_held_low_at_start_must_release_before_logging_a_press(name, pin):
    gpio = FakeGPIO()
    gpio.values[pin] = False
    service = InputService(gpio=gpio, poll_seconds=10)
    service.start()

    now = time.monotonic()
    service._poll_once(now + 0.021)
    assert service.get_states()[name] is True
    assert service.get_events_since(1) == []

    gpio.values[pin] = True
    service._poll_once(now + 1.0)
    service._poll_once(now + 1.021)
    gpio.values[pin] = False
    service._poll_once(now + 2.0)
    service._poll_once(now + 2.021)
    assert service.get_events_since(1)[-1]["event"] == name
    service.stop()


def test_encoder_press_toggles_once_per_debounced_press():
    gpio = FakeGPIO()
    presses = []
    service = InputService(gpio=gpio, poll_seconds=10,
                           on_encoder_press=lambda: presses.append(True))
    service.start()
    try:
        for now, high in [(1, False), (1.01, True), (2, False),
                          (2.021, False), (3, False), (4, True),
                          (4.021, True), (5, False), (5.021, False)]:
            gpio.values[16] = high
            service._poll_once(now)
        assert presses == [True, True]
    finally:
        service.stop()


def test_arcade_callback_only_fires_for_debounced_press():
    gpio = FakeGPIO()
    presses = []
    service = InputService(gpio=gpio, poll_seconds=10, on_arcade_press=presses.append)
    service.start()
    try:
        gpio.values[5] = False
        service._poll_once(1)
        gpio.values[5] = True
        service._poll_once(1.01)
        assert presses == []
        for pin, now in [(6, 2), (5, 3)]:
            gpio.values[pin] = False
            service._poll_once(now)
            service._poll_once(now + .021)
            service._poll_once(now + .1)
        assert presses == [2, 1]
    finally:
        service.stop()
