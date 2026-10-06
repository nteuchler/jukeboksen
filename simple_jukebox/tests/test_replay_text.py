import json
import threading
import wave

import pytest

from simple_jukebox.nfc_actions import NfcSpeech
from simple_jukebox.tests.test_nfc_simulation import setup
from simple_jukebox.text2music import render


def test_replay_requires_history_and_local_file_survives_stop_and_mode_change(setup):
    client, actions = setup
    assert client.post('/api/replay', json={}).status_code == 400
    client.post('/api/mode', json={'mode': 'local_files'})
    assert client.post('/api/play', json={'track': 'song.mp3'}).status_code == 200
    client.post('/api/stop', json={})
    client.post('/api/mode', json={'mode': 'bluetooth'})
    response = client.post('/api/replay', json={})
    assert response.status_code == 200
    assert response.json['status']['mode'] == 'local_files'
    assert response.json['status']['track'] == 'song.mp3'
    assert not response.json['status']['bluetooth_active']


def test_nfc_replay_uses_original_action_after_mapping_edit(setup):
    client, actions = setup
    client.post('/api/nfc/simulate', json={'text': 'hej'})
    actions.path.write_text('{}')
    client.post('/api/stop', json={})
    response = client.post('/api/replay', json={})
    assert response.status_code == 200
    assert response.json['status']['mode'] == 'nfc'
    assert actions.speech.args == ('Hej verden', 'da', 145)
    assert response.json['status']['last_played'] == 'NFC: hej'


@pytest.mark.parametrize('kind', ['tts', 'text2music'])
def test_typed_text_replay_and_mode_cleanup(setup, kind):
    client, actions = setup
    calls = []
    def music(text):
        actions.speech.playing = True
        calls.append(text)
    actions.speech.text2music = music
    response = client.post('/api/text/play', json={'text': 'Blå himmel', 'type': kind})
    assert response.status_code == 200
    assert response.json['status']['playing']
    assert response.json['status']['mode'] == 'local_files'
    if kind == 'tts':
        assert actions.speech.args == ('Blå himmel', 'da', 145)
    client.post('/api/mode', json={'mode': 'idle'})
    assert not actions.speech.playing
    assert client.post('/api/replay', json={}).status_code == 200
    assert actions.speech.playing
    if kind == 'text2music':
        assert calls == ['Blå himmel', 'Blå himmel']
    client.post('/api/stop', json={})
    assert not actions.speech.playing


@pytest.mark.parametrize('data', [[], {}, {'text': '', 'type': 'tts'},
    {'text': ' ', 'type': 'tts'}, {'text': 'hej', 'type': 'invalid'},
    {'text': 'hej', 'type': []}, {'text': 'x' * 10001, 'type': 'tts'}])
def test_invalid_text_does_not_change_mode_or_history(setup, data):
    client, _ = setup
    assert client.post('/api/text/play', json=data).status_code == 400
    status = client.get('/api/status').json
    assert status['mode'] == 'idle' and status['last_played'] is None


def test_text2music_uses_actual_clip_library(tmp_path):
    clip = tmp_path / 'hej.wav'
    with wave.open(str(clip), 'wb') as output:
        output.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\x10\x01' * 2205)
    (tmp_path / 'index.json').write_text(json.dumps({'clips': [
        {'word': 'hej', 'file': 'hej.wav', 'score': 1.0, 'approved': True}]}))
    result = tmp_path / 'result.wav'
    render('hej hej', result, tmp_path)
    with wave.open(str(result)) as audio:
        assert .37 < audio.getnframes() / audio.getframerate() < .39
        assert any(audio.readframes(audio.getnframes()))


def test_text2music_failure_is_visible_and_stop_cancels(monkeypatch):
    speech = NfcSpeech()
    started = threading.Event()
    def fail(command, cancel):
        raise RuntimeError('missing library')
    monkeypatch.setattr(speech, '_run', fail)
    speech.text2music('Hej')
    speech._thread.join(1)
    assert speech.error == 'text2Music: missing library'
    def wait(command, cancel):
        started.set()
        assert cancel.wait(1)
        return False
    monkeypatch.setattr(speech, '_run', wait)
    speech.text2music('Hej')
    assert started.wait(1)
    speech.stop()
    assert not speech.playing and not speech.error
