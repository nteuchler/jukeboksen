import json
from types import SimpleNamespace

import pytest

from simple_jukebox.app import create_app
from simple_jukebox.input_service import InputService
from simple_jukebox.oled import OledService
from simple_jukebox.tests.test_nfc_text import Speech
from simple_jukebox.tests.test_state_machine import FakePlayer, FakeBluetooth
from simple_jukebox.tests.test_web import FakeRgb, FakeVolume


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(InputService, 'start', lambda self: None)
    monkeypatch.setattr(OledService, 'start', lambda self: None)
    player = FakePlayer()
    player.tracks = lambda: ['song.mp3']
    reader = SimpleNamespace(start=lambda: None, stop=lambda: None,
                             status=lambda: {'detections': 0}, drain_events=lambda: [])
    app = create_app(player=player, bluetooth=FakeBluetooth(), volume=FakeVolume(),
                     rgb=FakeRgb(), nfc=reader)
    actions = app.config['services'].nfc_actions
    actions.speech = Speech()
    actions.path = tmp_path / 'nfc.json'
    actions.path.write_text(json.dumps({'music': {'type': 'file', 'file': 'song.mp3'},
                                       'hej': {'type': 'tts', 'text': 'Hej verden'}}))
    yield app.test_client(), actions
    app.config['engine'].close()
    app.config['input_service'].stop()
    app.config['oled'].stop()


def test_choices_reload_and_page_controls(setup):
    client, actions = setup
    assert client.get('/api/nfc/actions').json['actions'] == [
        {'text': 'music', 'type': 'file', 'description': 'song.mp3'},
        {'text': 'hej', 'type': 'tts', 'description': 'Hej verden'}]
    page = client.get('/').data
    assert b'id="nfc-actions"' in page and b'id="nfc-play"' in page
    actions.path.write_text('{}')
    assert client.get('/api/nfc/actions').json == {'actions': []}
    actions.path.write_text('{')
    assert client.get('/api/nfc/actions').status_code == 400


def test_simulation_switches_mode_replays_replaces_and_stops(setup):
    client, actions = setup
    client.post('/api/mode', json={'mode': 'bluetooth'})
    for _ in range(2):
        response = client.post('/api/nfc/simulate', json={'text': 'hej'})
        assert response.status_code == 200
        status = response.json['status']
        assert status['mode'] == 'nfc'
        assert not status['bluetooth_active']
        assert status['nfc']['detections'] == 0
        assert status['nfc_action']['match'] == 'hej'
        assert actions.speech.args == ('Hej verden', 'da', 145)
    response = client.post('/api/nfc/simulate', json={'text': 'music'})
    assert response.json['status']['track'] == 'song.mp3'
    assert not actions.speech.playing
    assert client.post('/api/stop', json={}).status_code == 200
    assert not actions.audio.playing


@pytest.mark.parametrize('data', [{}, [], {'text': 1}, {'text': 'unknown'}])
def test_invalid_selection_does_not_switch_mode(setup, data):
    client, actions = setup
    assert client.post('/api/nfc/simulate', json=data).status_code == 400
    assert client.get('/api/status').json['mode'] == 'idle'
    assert not actions.audio.playing and not actions.speech.playing


def test_missing_file_is_reported_to_browser(setup):
    client, actions = setup
    actions.path.write_text('{"missing": {"type":"file", "file":"absent.mp3"}}')
    response = client.post('/api/nfc/simulate', json={'text': 'missing'})
    assert response.status_code == 400
    assert 'available file' in response.json['error']
