import json
from types import SimpleNamespace

import pytest

from simple_jukebox.quiz import BluetoothMedia, QuizBuzzer
from simple_jukebox.services import JukeboxServices
from simple_jukebox.state_machine import StateMachine
from simple_jukebox.tests.test_state_machine import FakeBluetooth, FakePlayer
from simple_jukebox.tests.test_web import FakeVolume


class QuizRgb:
    def __init__(self):
        self.mode = 'flame'

    def set_mode(self, mode):
        self.mode = mode

    def status(self):
        return {'mode': self.mode}


class Media:
    def __init__(self):
        self.state = 'playing'
        self.pauses = 0
        self.fail = False

    def reset(self):
        pass

    def pause(self):
        self.pauses += 1
        if self.fail:
            raise RuntimeError('NotSupported')

    def playback_status(self):
        return self.state


class Buzzer:
    def __init__(self):
        self.plays = 0
        self.stops = 0

    def play(self):
        self.plays += 1

    def stop(self):
        self.stops += 1


def setup_quiz():
    rgb, media, buzzer = QuizRgb(), Media(), Buzzer()
    services = JukeboxServices(FakePlayer(), FakeBluetooth(), FakeVolume(), rgb,
                               quiz_media=media, buzzer=buzzer)
    return StateMachine(services), services


def poll(machine):
    machine._quiz_poll_at = 0
    machine.poll_quiz()


@pytest.mark.parametrize('player,color', [(1, 'red'), (2, 'green')])
def test_first_buzz_wins_and_only_pause_then_resume_rearms(player, color):
    machine, services = setup_quiz()
    machine.arcade_press(player)
    assert machine.quiz_winner is None
    machine.change_mode('music_quiz')
    assert services.bluetooth.active
    assert services.rgb.mode == 'equalizer'
    machine.arcade_press(player)
    machine.arcade_press(3 - player)
    assert services.rgb.mode == color
    assert machine.quiz_winner == player
    assert services.quiz_media.pauses == services.buzzer.plays == 1
    poll(machine)  # Stale playing state after the pause request must not reset.
    assert machine.quiz_winner == player
    services.quiz_media.state = 'paused'
    poll(machine)
    assert services.rgb.mode == color
    services.quiz_media.state = 'playing'
    poll(machine)
    assert machine.quiz_winner is None
    assert services.rgb.mode == 'equalizer'
    machine.arcade_press(3 - player)
    assert machine.quiz_winner == 3 - player
    machine.change_mode('idle')
    assert not services.bluetooth.active
    assert services.rgb.mode == 'flame'
    assert machine.quiz_winner is None
    assert services.buzzer.stops >= 1


def test_failed_pause_preserves_winner_and_allows_manual_pause_resume():
    machine, services = setup_quiz()
    machine.change_mode('music_quiz')
    services.quiz_media.fail = True
    machine.arcade_press(1)
    assert 'NotSupported' in machine.quiz_error
    assert services.rgb.mode == 'red'
    assert services.buzzer.plays == 1
    services.quiz_media.state = 'paused'
    poll(machine)
    services.quiz_media.state = 'playing'
    poll(machine)
    assert machine.quiz_winner is None
    assert machine.quiz_error is None


def test_bluez_pauses_connected_playing_phone_and_reads_status(monkeypatch):
    device = '/org/bluez/hci0/dev_PHONE'
    player = device + '/player0'
    objects = {
        device: {'org.bluez.Device1': {'Connected': {'data': True}}},
        player: {'org.bluez.MediaPlayer1': {'Status': {'data': 'playing'}}},
        '/org/bluez/hci0/dev_OLD/player0': {'org.bluez.MediaPlayer1': {'Status': {'data': 'playing'}}},
    }
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=json.dumps({'data': [objects]})
                               if args[-1] == 'GetManagedObjects' else '')

    monkeypatch.setattr('simple_jukebox.quiz.subprocess.run', run)
    media = BluetoothMedia()
    media.pause()
    assert calls[-1][-3:] == [player, 'org.bluez.MediaPlayer1', 'Pause']
    objects[player]['org.bluez.MediaPlayer1']['Status']['data'] = 'paused'
    assert media.playback_status() == 'paused'
    objects[device]['org.bluez.Device1']['Connected']['data'] = False
    with pytest.raises(RuntimeError, match='No Bluetooth media player'):
        media.playback_status()


def test_buzzer_creates_short_valid_audio_and_cleans_up(monkeypatch):
    import wave
    from pathlib import Path
    paths = []

    def popen(args, **kwargs):
        paths.append(Path(args[1]))
        with wave.open(args[1]) as audio:
            assert audio.getframerate() == 22050
            assert .4 < audio.getnframes() / audio.getframerate() < .5
        return SimpleNamespace(poll=lambda: 0)

    monkeypatch.setattr('simple_jukebox.quiz.subprocess.Popen', popen)
    buzzer = QuizBuzzer()
    buzzer.play()
    buzzer.stop()
    assert not paths[0].exists()


def test_quiz_resumes_without_any_web_requests():
    import time
    from simple_jukebox.engine import CommandEngine, Command, CommandType
    machine, services = setup_quiz()
    engine = CommandEngine(machine, services)
    try:
        engine.submit(Command(CommandType.CHANGE_MODE, 'music_quiz'))
        engine.submit(Command(CommandType.ARCADE_PRESS, 2))
        services.quiz_media.state = 'paused'
        deadline = time.monotonic() + 2
        while not machine._quiz_saw_pause and time.monotonic() < deadline:
            time.sleep(.02)
        assert machine._quiz_saw_pause
        services.quiz_media.state = 'playing'
        deadline = time.monotonic() + 2
        while machine.quiz_winner is not None and time.monotonic() < deadline:
            time.sleep(.02)
        assert machine.quiz_winner is None
        assert services.rgb.mode == 'equalizer'
    finally:
        # The real controller provides close; keep the fake focused on quiz RGB.
        services.rgb.close = lambda: None
        engine.close()


def test_website_can_select_music_quiz():
    from simple_jukebox.app import create_app
    app = create_app(player=FakePlayer(), bluetooth=FakeBluetooth(),
                     volume=FakeVolume(), rgb=QuizRgb(), quiz_media=Media(), buzzer=Buzzer())
    try:
        client = app.test_client()
        response = client.post('/api/mode', json={'mode': 'music_quiz'})
        assert response.status_code == 200
        status = response.get_json()['status']
        assert status['mode'] == 'music_quiz'
        assert status['bluetooth_active']
        assert status['rgb']['mode'] == 'equalizer'
        assert b'Music quiz' in client.get('/').data
    finally:
        app.config['rgb'].close = lambda: None
        app.config['engine'].close()
        app.config['input_service'].stop()
        app.config['oled'].stop()
