from simple_jukebox.app import create_app
from simple_jukebox.tests.test_state_machine import FakeBluetooth, FakePlayer


class FakeVolume:
    def __init__(self):
        self.value = 40

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
