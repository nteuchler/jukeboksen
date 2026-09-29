from pathlib import Path

from simple_jukebox.app import create_app
from simple_jukebox.tests.test_state_machine import FakeBluetooth, FakePlayer


class FakeVolume:
    def __init__(self):
        self.value = 40
        self.muted = False

    def is_muted(self):
        return self.muted

    def toggle_mute(self):
        self.muted = not self.muted

    def get(self):
        return self.value

    def set(self, value):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError("bad volume")
        self.value = value


class FakeRgb:
    def __init__(self):
        self.mode = "off"

    def status(self):
        return {"mode": self.mode, "error": None}

    def set_mode(self, mode):
        if mode not in {"off", "flame", "party", "equalizer"}:
            raise ValueError("bad RGB mode")
        self.mode = mode

    def close(self):
        self.mode = "off"


def make_app():
    return create_app(
        player=FakePlayer(), bluetooth=FakeBluetooth(),
        volume=FakeVolume(), rgb=FakeRgb(),
    )


def test_web_changes_mode_and_returns_status():
    app = make_app()
    client = app.test_client()

    assert client.get("/").status_code == 200
    response = client.post("/api/mode", json={"mode": "local_files"})
    assert response.status_code == 200
    assert response.get_json()["status"]["mode"] == "local_files"


def test_website_can_enable_and_disable_encoder_button(monkeypatch):
    from simple_jukebox.input_service import InputService
    from simple_jukebox.oled import OledService

    monkeypatch.setattr(InputService, "start", lambda self: None)
    monkeypatch.setattr(OledService, "start", lambda self: None)
    app = make_app()
    try:
        service = app.config["input_service"]
        client = app.test_client()
        assert b'id="encoder-button-toggle"' in client.get("/").data
        for enabled in (False, True, False):
            response = client.post("/api/inputs/encoder", json={"enabled": enabled})
            assert response.status_code == 200
            assert response.get_json()["status"]["encoder_button_disabled"] is not enabled
            assert client.get("/api/inputs").get_json()["status"]["encoder_button_disabled"] is not enabled
        for data in ({}, {"enabled": "false"}, {"enabled": 0}, []):
            assert client.post("/api/inputs/encoder", json=data).status_code == 400
        assert service.status()["encoder_button_disabled"] is True
    finally:
        app.config["engine"].close()
        app.config["oled"].stop()
        app.config["input_service"].stop()


def test_web_rejects_unknown_mode():
    app = make_app()
    response = app.test_client().post("/api/mode", json={"mode": "unknown"})
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_web_controls_volume_and_rgb_mode():
    app = make_app()
    client = app.test_client()

    assert client.post("/api/volume", json={"volume": 72}).status_code == 200
    assert client.post("/api/rgb", json={"mode": "party"}).status_code == 200
    status = client.get("/api/status").get_json()
    assert status["volume"] == 72
    assert status["rgb"]["mode"] == "party"


def test_web_rejects_invalid_volume_and_rgb_mode():
    app = make_app()
    client = app.test_client()

    assert client.post("/api/volume", json={"volume": 101}).status_code == 400
    assert client.post("/api/rgb", json={"mode": "rainbow"}).status_code == 400


def test_default_media_folder_is_dedicated_to_user_audio():
    app = create_app(
        bluetooth=FakeBluetooth(), volume=FakeVolume(), rgb=FakeRgb(),
    )

    expected = Path(__file__).resolve().parents[1] / "media"
    assert app.config["player"].media_folder == expected


def test_encoder_mute_is_reflected_in_web_status_and_preserves_volume():
    from simple_jukebox.engine import Command, CommandType

    app = make_app()
    client = app.test_client()
    engine = app.config['engine']
    try:
        for source, muted in [('encoder', True), ('website', False),
                              ('website', True), ('encoder', False)]:
            if source == 'encoder':
                engine.submit(Command(CommandType.TOGGLE_OUTPUT_MUTE))
            else:
                response = client.post('/api/mute', json={})
                assert response.status_code == 200
                assert response.get_json()['status']['output_muted'] is muted
            status = client.get('/api/status').get_json()
            assert status['output_muted'] is muted
            assert status['volume'] == 40
    finally:
        engine.close()
