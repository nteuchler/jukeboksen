from types import SimpleNamespace

import pytest

from simple_jukebox.app import create_app
from simple_jukebox.engine import Command, CommandType
from simple_jukebox.input_service import InputService
from simple_jukebox.oled import OledService
from simple_jukebox.tests.test_input_service import FakeGPIO
from simple_jukebox.tests.test_state_machine import FakeBluetooth, FakePlayer
from simple_jukebox.tests.test_web import FakeRgb, FakeVolume


@pytest.mark.parametrize('name,pin,direction', [('NAV_LEFT', 23, -1), ('NAV_RIGHT', 24, 1)])
def test_navigation_debounce_hold_and_disable(name, pin, direction):
    gpio, moves = FakeGPIO(), []
    gpio.values[pin] = True
    service = InputService(gpio=gpio, on_navigation=moves.append)
    service._use_gpio = True
    service._configured_inputs = {name}
    service._armed[name] = True
    service._candidate_since[name] = 0

    def sample(now, pressed):
        gpio.values[pin] = not pressed
        service._poll_once(now)

    sample(1, True)
    sample(1.01, False)  # bounce
    sample(2, True)
    assert moves == []
    sample(2.021, True)
    sample(5, True)  # no repeat while held
    assert moves == [direction]
    sample(6, False)
    sample(6.021, False)
    service.set_navigation_enabled(False)
    sample(7, True)
    sample(7.021, True)
    assert moves == [direction]
    service.set_navigation_enabled(True)
    sample(8, True)
    assert moves == [direction]
    sample(9, False)
    sample(9.021, False)
    sample(10, True)
    # Toggling during debounce must not turn a held button into a new press.
    service.set_navigation_enabled(False)
    service.set_navigation_enabled(True)
    sample(10.021, True)
    assert moves == [direction]
    sample(11, False)
    sample(11.021, False)
    sample(12, True)
    sample(12.021, True)
    assert moves == [direction, direction]


def test_navigation_wiring_wraparound_and_website_disable(monkeypatch):
    monkeypatch.setattr(InputService, 'start', lambda self: None)
    monkeypatch.setattr(OledService, 'start', lambda self: None)
    reader = SimpleNamespace(start=lambda: None, stop=lambda: None,
                             status=lambda: {}, drain_events=lambda: [])
    app = create_app(player=FakePlayer(), bluetooth=FakeBluetooth(),
                     volume=FakeVolume(), rgb=FakeRgb(), nfc=reader)
    engine = app.config['engine']
    service = app.config['input_service']
    client = app.test_client()
    gpio = FakeGPIO()
    gpio.values[24] = True
    service._gpio = gpio
    service._use_gpio = True
    service._configured_inputs = {'NAV_RIGHT'}
    service._armed['NAV_RIGHT'] = True
    service._candidate_since['NAV_RIGHT'] = 0
    try:
        assert b'id="navigation-toggle"' in client.get('/').data
        for direction, expected in [(1, ['local_files', 'bluetooth', 'music_quiz', 'coin_survival', 'sleeping', 'nfc', 'idle']),
                                    (-1, ['nfc', 'sleeping', 'coin_survival', 'music_quiz', 'bluetooth', 'local_files', 'idle'])]:
            futures = [engine.enqueue(Command(CommandType.NAVIGATE_MODE, direction)) for _ in expected]
            for future in futures:
                future.result(timeout=2)
            assert app.config['machine'].mode.value == 'idle'
            for mode in expected:
                service._on_navigation(direction)
                engine.submit(Command(CommandType.SET_VOLUME, 40))  # queue barrier
                assert app.config['machine'].mode.value == mode

        for data in ({}, {'enabled': 'false'}, {'enabled': 0}, []):
            assert client.post('/api/inputs/navigation', json=data).status_code == 400
        for enabled, expected in [(False, 'idle'), (True, 'local_files')]:
            response = client.post('/api/inputs/navigation', json={'enabled': enabled})
            assert response.status_code == 200
            assert response.json['status']['navigation_disabled'] is not enabled
            assert client.get('/api/inputs').json['status']['navigation_disabled'] is not enabled
            gpio.values[24] = False
            service._poll_once(1)
            service._poll_once(1.021)
            engine.submit(Command(CommandType.SET_VOLUME, 40))
            assert app.config['machine'].mode.value == expected
            gpio.values[24] = True
            service._poll_once(2)
            service._poll_once(2.021)
        client.post('/api/inputs/navigation', json={'enabled': False})
        assert client.post('/api/mode', json={'mode': 'bluetooth'}).status_code == 200
        assert app.config['machine'].mode.value == 'bluetooth'
    finally:
        engine.close()
        service.stop()
