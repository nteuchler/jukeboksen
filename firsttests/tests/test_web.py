import pytest

pytest.importorskip("flask")

from magical_jukebox.app import create_app


def test_status_and_modes_endpoints(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "START_ENGINE": False,
            "MEDIA_DIR": tmp_path,
        }
    )
    client = app.test_client()

    status_response = client.get("/api/status")
    assert status_response.status_code == 200
    assert status_response.get_json()["engine_running"] is False

    modes_response = client.get("/api/modes")
    assert modes_response.status_code == 200
    assert len(modes_response.get_json()["modes"]) == 6


def test_command_returns_service_unavailable_when_engine_is_off(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "START_ENGINE": False,
            "MEDIA_DIR": tmp_path,
        }
    )
    client = app.test_client()

    response = client.post("/api/force-next")
    assert response.status_code == 503
