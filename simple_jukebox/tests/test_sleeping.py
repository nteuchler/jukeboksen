from types import SimpleNamespace
import struct
import subprocess
import wave
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from simple_jukebox.sleeping import SleepingMode, P8_JAZZ_URL, RisingAlarm
from simple_jukebox.oled import status_lines
from simple_jukebox.state_machine import StateMachine
from simple_jukebox.services import JukeboxServices
from simple_jukebox.tests.test_state_machine import FakePlayer, FakeBluetooth
from simple_jukebox.tests.test_web import FakeVolume, FakeRgb


class SleepAudio(FakePlayer):
    def __init__(self):
        super().__init__()
        self.sources = []

    def play_source(self, source, label, **options):
        self.sources.append((source, label, options))
        self.play(label)

def sleeping_fixture():
    now = [0]
    audio = SleepAudio()
    spoken = []
    speech = SimpleNamespace(playing=False, error=None)
    def speak(*args):
        spoken.append(args)
        speech.playing = True
    speech.speak = speak
    speech.stop = lambda: setattr(speech, 'playing', False)
    alarm = SimpleNamespace(playing=False)
    alarm.start = lambda: setattr(alarm, 'playing', True)
    alarm.stop = lambda: setattr(alarm, 'playing', False)
    start = datetime(2026, 10, 10, 7, 59, tzinfo=ZoneInfo('Europe/Copenhagen')).timestamp()
    return SleepingMode(audio, speech, lambda: now[0], alarm,
                        wall_clock=lambda: start + now[0]), now, spoken


def test_scheduled_alarm_ramp_greeting_radio_and_second_press():
    sleep, now, spoken = sleeping_fixture()
    sleep.configure('08:00')
    sleep.start()
    sleep.press()  # Early presses do not skip the timer.
    now[0] = 59
    sleep.poll()
    assert sleep.phase == 'waiting' and sleep.status()['remaining_seconds'] == 1
    now[0] = 60
    sleep.poll()
    assert sleep.phase == 'alarm'
    assert sleep.alarm.playing and sleep.status()['alarm_volume_percent'] == 50
    now[0] = 120
    sleep.poll()
    assert sleep.status()['alarm_volume_percent'] == 75
    now[0] = 190
    sleep.poll()
    assert sleep.status()['alarm_volume_percent'] == 100
    sleep.press()
    assert not sleep.alarm.playing
    assert sleep.phase == 'greeting_delay' and spoken == []
    now[0] += 4.99
    sleep.poll()
    assert spoken == [] and sleep.audio.sources == []
    now[0] += .01
    sleep.poll()
    assert spoken == [('Godmorgen gruppe 5', 'da', 145)]
    sleep.poll()
    assert sleep.phase == 'greeting'  # Wait until speech finishes.
    sleep.speech.playing = False
    sleep.poll()
    assert sleep.phase == 'radio'
    assert sleep.audio.sources[-1][:2] == (P8_JAZZ_URL, 'P8 Jazz')
    sleep.press()
    sleep.poll()
    assert sleep.phase == 'stopped' and not sleep.audio.playing


@pytest.mark.parametrize('button', [1, 2])
def test_machine_arcade_stop_and_mode_cleanup(button):
    services = JukeboxServices(FakePlayer(), FakeBluetooth(), FakeVolume(), FakeRgb())
    machine = StateMachine(services)
    machine.sleeping, now, _ = sleeping_fixture()
    machine.configure_sleeping('08:00')
    machine.change_mode('sleeping')
    now[0] = 60
    machine.poll_sleeping()
    assert machine.status()['playing'] and machine.status()['track'] == 'AlarmApple'
    machine.arcade_press(button)
    assert machine.sleeping.phase == 'greeting_delay'
    machine.arcade_press(button)
    assert machine.sleeping.phase == 'stopped'
    now[0] += 10
    machine.poll_sleeping()
    assert not machine.sleeping.speech.playing and machine.sleeping.audio.sources == []
    machine.configure_sleeping('08:02')
    assert machine.sleeping.status()['remaining_seconds'] == 110
    assert status_lines(machine.status())[0] == 'Sleeping'
    machine.change_mode('idle')
    assert machine.sleeping.phase == 'inactive'
    assert not machine.sleeping.speech.playing


@pytest.mark.parametrize('alarm_time', [None, True, 0, 1.5, '30', '8:00', '24:00', '08:60', '08:00:00', ' 08:00', '08:00\n'])
def test_invalid_alarm_time_does_not_reschedule(alarm_time):
    sleep, now, _ = sleeping_fixture()
    sleep.start()
    deadline = sleep.deadline
    with pytest.raises(ValueError):
        sleep.configure(alarm_time)
    assert sleep.deadline == deadline


def test_cancel_during_greeting_and_radio_failure():
    sleep, now, _ = sleeping_fixture()
    sleep.start()
    now[0] = 1800
    sleep.poll()
    sleep.press()
    sleep.stop()
    now[0] += 10
    sleep.poll()
    assert len(sleep.audio.sources) == 0 and not sleep.speech.playing
    sleep.phase = 'greeting'
    sleep.poll()
    sleep.audio.playing = False
    sleep.poll()
    assert sleep.phase == 'error' and 'internet connection' in sleep.error


def test_alarm_samples_rise_across_repeats_and_cap_at_full_volume(tmp_path, monkeypatch):
    from simple_jukebox import sleeping
    clip = tmp_path / 'alarm.wav'
    with wave.open(str(clip), 'wb') as output:
        output.setparams((2, 2, 22050, 0, 'NONE', 'constant signal'))
        output.writeframes(struct.pack('<hh', 10000, 10000) * 2205)
    monkeypatch.setattr(sleeping, 'ALARM_FILE', clip)
    commands = []
    class Process:
        stdout = SimpleNamespace(close=lambda: None)
        def poll(self):
            return None
        def terminate(self):
            pass
        def wait(self, timeout):
            return 0
    real_run = subprocess.run
    monkeypatch.setattr(sleeping.subprocess, 'Popen', lambda command, **kwargs:
                        commands.append(command) or Process())
    alarm = RisingAlarm()
    alarm.start()
    alarm.stop()
    command = commands[0]
    command.remove('-re')  # Render quickly; the production stream runs in real time.
    command[-1:-1] = ['-t', '122']
    monkeypatch.undo()
    samples = real_run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
    def amplitude(second):
        return struct.unpack_from('<h', samples, int(second * 44100) * 4)[0]
    assert 4900 < amplitude(.1) < 5100
    assert 7400 < amplitude(60) < 7600
    assert amplitude(121) == 10000


def test_sleeping_api_controls_and_status(monkeypatch):
    from simple_jukebox.app import create_app
    from simple_jukebox.input_service import InputService
    from simple_jukebox.oled import OledService
    monkeypatch.setattr(InputService, 'start', lambda self: None)
    monkeypatch.setattr(OledService, 'start', lambda self: None)
    app = create_app(player=FakePlayer(), bluetooth=FakeBluetooth(), volume=FakeVolume(), rgb=FakeRgb())
    app.config['machine'].sleeping, _, _ = sleeping_fixture()
    client = app.test_client()
    try:
        assert b'data-mode="sleeping"' in client.get('/').data
        for data in ([], {}, {'alarm_time': False}, {'alarm_time': '24:00'}, {'minutes': 5}):
            assert client.post('/api/sleeping', json=data).status_code == 400
        assert client.post('/api/sleeping', json={'alarm_time': '08:04'}).status_code == 200
        result = client.post('/api/mode', json={'mode': 'sleeping'})
        assert result.status_code == 200
        assert result.json['status']['sleeping']['remaining_seconds'] == 300
        assert result.json['status']['sleeping']['alarm_time'] == '08:04'
        assert client.post('/api/stop', json={}).json['status']['sleeping']['phase'] == 'stopped'
        assert client.post('/api/mode', json={'mode': 'idle'}).status_code == 200
    finally:
        app.config['engine'].close()


@pytest.mark.parametrize('local_now,alarm_time,expected', [
    ('2026-10-10T07:00:00', '08:00', '2026-10-10T08:00:00+02:00'),
    ('2026-10-10T09:00:00', '08:00', '2026-10-11T08:00:00+02:00'),
    ('2026-10-10T08:00:00', '08:00', '2026-10-11T08:00:00+02:00'),
    ('2026-10-10T23:59:00', '00:00', '2026-10-11T00:00:00+02:00'),
    ('2026-10-24T09:00:00', '08:00', '2026-10-25T08:00:00+01:00'),
    ('2026-03-28T09:00:00', '08:00', '2026-03-29T08:00:00+02:00'),
])
def test_schedule_uses_next_local_occurrence_including_daylight_saving(local_now, alarm_time, expected):
    sleep, _, _ = sleeping_fixture()
    timestamp = datetime.fromisoformat(local_now).replace(tzinfo=ZoneInfo('Europe/Copenhagen')).timestamp()
    sleep.wall_clock = lambda: timestamp
    sleep.configure(alarm_time)
    sleep.start()
    assert sleep.status()['alarm_at'] == expected


def test_alarm_follows_wall_clock_while_volume_ramp_uses_monotonic_time():
    sleep, now, _ = sleeping_fixture()
    sleep.start()
    now[0] = 10
    sleep.wall_clock = lambda: sleep.deadline + 1
    sleep.poll()
    assert sleep.phase == 'alarm'
    sleep.wall_clock = lambda: sleep.deadline - 3600
    now[0] = 70
    sleep.poll()
    assert sleep.status()['alarm_volume_percent'] == 75
