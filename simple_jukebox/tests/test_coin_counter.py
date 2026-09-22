from simple_jukebox.input_service import InputService
from simple_jukebox.tests.test_input_service import FakeGPIO
from simple_jukebox.tests.test_web import make_app


def test_coin_count_ignores_bounce_and_held_signal():
    gpio = FakeGPIO()
    gpio.values[12] = True
    service = InputService(gpio=gpio, max_events=1)
    service._use_gpio = True
    service._configured_inputs = {"COIN"}
    service._armed["COIN"] = True

    gpio.values[12] = False
    service._poll_once(1.0)
    gpio.values[12] = True
    service._poll_once(1.01)
    assert service.status()["coin_count"] == 0

    for start in (2.0, 4.0):
        gpio.values[12] = False
        service._poll_once(start)
        service._poll_once(start + 0.03)
        service._poll_once(start + 0.5)
        gpio.values[12] = True
        service._poll_once(start + 1)
        service._poll_once(start + 1.03)

    assert service.status()["coin_count"] == 2
    assert len(service.get_events_since()) == 1


def test_coin_total_is_shared_across_web_requests(monkeypatch):
    monkeypatch.setattr(InputService, "start", lambda self: None)
    app = make_app()
    service = app.config["input_service"]
    try:
        client = app.test_client()
        assert client.get("/api/inputs").get_json()["status"]["coin_count"] == 0
        service.simulate_event("COIN")
        service.simulate_event("ARCADE_1")
        service.simulate_event("COIN")
        assert client.get("/api/inputs").get_json()["status"]["coin_count"] == 2
        assert b'id="coin-count"' in client.get("/").data
        assert app.test_client().get("/api/inputs").get_json()["status"]["coin_count"] == 2
    finally:
        app.config["engine"].close()
        app.config["oled"].stop()
        service.stop()
