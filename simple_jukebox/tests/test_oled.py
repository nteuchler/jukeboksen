import threading

from simple_jukebox.oled import OledService, status_lines


class FakeDisplay:
    width = 128
    height = 64

    def __init__(self):
        self.frames = []
        self.cleaned = False

    def display(self, frame):
        self.frames.append(frame)

    def cleanup(self):
        self.cleaned = True


def test_default_driver_configuration(monkeypatch):
    from luma.core.interface.serial import noop
    from luma.oled.device import ssd1315

    calls = []
    def serial(**kwargs):
        calls.append(kwargs)
        return noop()

    for key in ("JUKEBOX_OLED_DRIVER", "JUKEBOX_OLED_BUS", "JUKEBOX_OLED_ADDRESS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("luma.core.interface.serial.i2c", serial)
    device = OledService._open_device()
    try:
        assert isinstance(device, ssd1315)
        assert (device.width, device.height) == (128, 64)
        assert calls == [{"port": 1, "address": 0x3c}]
    finally:
        device.cleanup()


def test_mode_playback_and_mute_labels():
    assert status_lines({"mode": "idle", "message": "Ready"}) == ["Idle", "Stopped", "", "Ready"]
    assert status_lines({"mode": "bluetooth", "bluetooth_active": True})[1] == "BT ready"
    assert status_lines({"mode": "local_files", "playing": True, "muted": True, "track": "song.mp3"})[:3] == ["Local files", "Playing (muted)", "song.mp3"]


def test_refresh_renders_changes_and_skips_unchanged_frames():
    state = {"mode": "idle", "message": "Ready"}
    device = FakeDisplay()
    service = OledService(lambda: state, lambda: device)
    service._refresh()
    service._refresh()
    assert len(device.frames) == 1
    assert device.frames[0].size == (128, 64)
    assert device.frames[0].getbbox() is not None
    state.update(mode="local_files", playing=True, track="A very long title " * 20 + "🎵.mp3")
    service._refresh()
    assert len(device.frames) == 2
    assert device.frames[0].tobytes() != device.frames[1].tobytes()


def test_background_updates_and_cleanup():
    rendered = threading.Event()
    device = FakeDisplay()
    original_display = device.display

    def display(frame):
        original_display(frame)
        rendered.set()

    device.display = display
    service = OledService(lambda: {"mode": "idle"}, lambda: device)
    service.start()
    try:
        assert rendered.wait(2)
    finally:
        service.stop()
    assert device.cleaned
    assert not service.status()["connected"]


def test_missing_display_is_reported_without_crashing():
    attempted = threading.Event()

    def missing():
        attempted.set()
        raise OSError("No I2C display")

    service = OledService(lambda: {}, missing)
    service.start()
    assert attempted.wait(2)
    service.stop()
    assert service.status() == {"connected": False, "error": "No I2C display"}
