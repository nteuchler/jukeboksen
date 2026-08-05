import time

from magical_jukebox.core.engine import Engine
from magical_jukebox.core.enums import CommandType
from magical_jukebox.core.messages import Command
from magical_jukebox.core.mode_registry import build_mode_registry
from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.factory import build_services


def wait_for(store, predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = store.snapshot()
        if predicate(snapshot):
            return snapshot
        time.sleep(0.02)
    raise AssertionError(f"Condition not met. Last status: {store.snapshot()}")


def test_engine_switches_modes_and_cleans_bluetooth(tmp_path):
    store = StatusStore()
    services = build_services(profile="mock", status_store=store, media_dir=tmp_path)
    engine = Engine(
        status_store=store,
        registry=build_mode_registry(),
        services=services,
    )
    engine.start()

    try:
        wait_for(store, lambda status: status["state"] == "idle")

        engine.submit(
            Command(type=CommandType.CHANGE_MODE, payload={"mode": "placeholder"})
        )
        wait_for(store, lambda status: status["state"] == "waiting")

        engine.submit(
            Command(type=CommandType.SIMULATE_BUTTON, payload={"button_id": 1})
        )
        wait_for(store, lambda status: status["state"] == "playing")

        engine.submit(Command(type=CommandType.FORCE_NEXT))
        wait_for(store, lambda status: status["state"] == "completed")

        engine.submit(
            Command(type=CommandType.CHANGE_MODE, payload={"mode": "bluetooth_speaker"})
        )
        wait_for(store, lambda status: status["state"] == "pairing")

        engine.submit(
            Command(
                type=CommandType.SIMULATE_BLUETOOTH_CONNECT,
                payload={"device": "Test phone"},
            )
        )
        wait_for(store, lambda status: status["state"] == "connected")

        engine.submit(Command(type=CommandType.CHANGE_MODE, payload={"mode": "idle"}))
        status = wait_for(store, lambda snapshot: snapshot["state"] == "idle")
        assert status["bluetooth"]["enabled"] is False
        assert status["bluetooth"]["remembered_devices"] == 0
    finally:
        engine.stop()

    assert engine.running is False


def test_disabled_mode_cannot_replace_active_mode(tmp_path):
    store = StatusStore()
    services = build_services(profile="mock", status_store=store, media_dir=tmp_path)
    engine = Engine(
        status_store=store,
        registry=build_mode_registry(),
        services=services,
    )
    engine.start()

    try:
        wait_for(store, lambda status: status["state"] == "idle")
        engine.submit(
            Command(type=CommandType.CHANGE_MODE, payload={"mode": "music_quiz"})
        )
        status = wait_for(store, lambda snapshot: snapshot["last_error"] is not None)
        assert status["mode"] == "idle"
        assert "disabled" in status["last_error"]
    finally:
        engine.stop()


def test_raspberry_pi_profile_builds_services(tmp_path):
    store = StatusStore()
    services = build_services(
        profile="raspberry_pi",
        status_store=store,
        media_dir=tmp_path,
        led_pixel_count=0,
    )

    snapshot = store.snapshot()
    assert snapshot["system"]["service_profile"] == "raspberry_pi"
    assert services.bluetooth is not None
    assert services.lighting is not None
