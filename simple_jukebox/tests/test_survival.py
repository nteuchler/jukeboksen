import threading
import time
import wave

import pytest

from simple_jukebox.app import create_app
from simple_jukebox.engine import Command, CommandType
from simple_jukebox.input_service import InputService
from simple_jukebox.oled import OledService, status_lines
from simple_jukebox.survival import SurvivalTimer
from simple_jukebox.survival_audio import SurvivalAudio, write_effect
from simple_jukebox.tests.test_input_service import FakeGPIO
from simple_jukebox.tests.test_state_machine import FakeBluetooth, FakePlayer
from simple_jukebox.tests.test_web import FakeRgb, FakeVolume


class Sounds:
    error = None

    def __init__(self):
        self.cues = []
        self.stops = 0

    def play(self, cue):
        self.cues.append(cue)

    def stop(self):
        self.stops += 1


def timer_setup():
    now, sounds, rgb = [100.0], Sounds(), FakeRgb()
    return SurvivalTimer(sounds, rgb, clock=lambda: now[0]), now, sounds, rgb


def test_countdown_warnings_expiry_repeat_and_coin_revival():
    timer, now, sounds, rgb = timer_setup()
    timer.start()
    assert timer.status()['remaining_seconds'] == 1800
    for elapsed, expected in [(1200, '600'), (1500, '300'), (1740, '60'),
                              (1770, '30'), (1790, '10'), (1800, 'expired')]:
        now[0] = 100 + elapsed
        timer.poll()
        assert sounds.cues[-1] == expected
        count = len(sounds.cues)
        now[0] += .2
        timer.poll()
        assert len(sounds.cues) == count
    assert timer.status()['expired']
    assert rgb.fraction == 0
    now[0] = 1915
    timer.poll()
    assert sounds.cues[-2:] == ['expired', 'expired']
    timer.coin()
    assert sounds.stops == 2
    assert sounds.cues[-1] == 'coin'
    assert timer.status()['remaining_seconds'] == 1800
    assert not timer.status()['expired']
    assert rgb.fraction == 1
    now[0] += 1200
    timer.poll()
    assert sounds.cues[-1] == '600'
    timer.stop()
    count = len(sounds.cues)
    now[0] += 5000
    timer.poll()
    timer.coin()
    assert not timer.status()['active']
    assert len(sounds.cues) == count


def test_coin_resets_remaining_time_and_duration_change_restarts():
    timer, now, sounds, rgb = timer_setup()
    timer.start()
    now[0] += 900
    timer.poll()
    assert rgb.fraction == .5
    timer.coin()
    assert timer.status()['remaining_seconds'] == 1800  # not 2700
    timer.configure(1)
    assert timer.status()['remaining_seconds'] == 60
    now[0] += 55
    timer.poll()
    assert sounds.cues == ['coin', '10']  # skip obsolete warnings after a delayed tick


@pytest.mark.parametrize('value', [None, True, False, 0, -1, 181, 1.5, '30', [], {}])
def test_invalid_duration_does_not_change_running_timer(value):
    timer, now, sounds, rgb = timer_setup()
    timer.start()
    deadline = timer.deadline
    with pytest.raises(ValueError):
        timer.configure(value)
    assert timer.deadline == deadline
    assert timer.minutes == 30


def test_audio_failure_does_not_prevent_expiry_or_coin_reset():
    timer, now, sounds, rgb = timer_setup()
    sounds.play = lambda cue: (_ for _ in ()).throw(OSError('speaker unavailable'))
    timer.start()
    now[0] += 1800
    timer.poll()
    assert timer.status()['expired']
    assert timer.status()['error'] == 'speaker unavailable'
    timer.coin()
    assert timer.status()['error'] == 'speaker unavailable'
    assert timer.status()['remaining_seconds'] == 1800


def test_failed_leds_do_not_suppress_alarm():
    timer, now, sounds, rgb = timer_setup()
    timer.start()
    rgb.set_countdown = lambda fraction: (_ for _ in ()).throw(OSError('LED unavailable'))
    now[0] += 1800
    timer.poll()
    assert sounds.cues == ['expired']
    assert timer.status()['error'] == 'LED unavailable'


def test_web_configuration_coin_gpio_and_background_expiry(monkeypatch):
    monkeypatch.setattr(InputService, 'start', lambda self: None)
    monkeypatch.setattr(OledService, 'start', lambda self: None)
    sounds, rgb = Sounds(), FakeRgb()
    rgb.set_mode('party')
    app = create_app(player=FakePlayer(), bluetooth=FakeBluetooth(),
                     volume=FakeVolume(), rgb=rgb, survival_audio=sounds)
    engine, machine = app.config['engine'], app.config['machine']
    service = app.config['input_service']
    now = [100.0]
    machine.survival.clock = lambda: now[0]
    gpio = FakeGPIO()
    gpio.values[12] = True
    service._gpio = gpio
    service._use_gpio = True
    service._configured_inputs = {'COIN'}
    service._armed['COIN'] = True
    service._candidate_since['COIN'] = 0
    client = app.test_client()
    try:
        assert b'data-mode="coin_survival"' in client.get('/').data
        for data in ([], {}, {'minutes': False}, {'minutes': 0}, {'minutes': '1'}):
            assert client.post('/api/survival', json=data).status_code == 400
        response = client.post('/api/survival', json={'minutes': 1})
        assert response.status_code == 200
        assert not response.json['status']['survival']['active']
        response = client.post('/api/mode', json={'mode': 'coin_survival'})
        assert response.status_code == 200
        assert response.json['status']['survival']['remaining_seconds'] == 60
        assert client.post('/api/rgb', json={'mode': 'off'}).status_code == 400
        now[0] += 61
        deadline = time.monotonic() + 2
        while not sounds.cues and time.monotonic() < deadline:
            time.sleep(.01)  # expiry must happen without any browser request
        assert sounds.cues == ['expired']
        assert 'Time is up!' in status_lines(machine.status())
        gpio.values[12] = False
        service._poll_once(1)
        service._poll_once(1.01)
        assert service.status()['coin_count'] == 0
        service._poll_once(1.021)
        engine.submit(Command(CommandType.SET_VOLUME, 40))
        assert machine.survival.status()['remaining_seconds'] == 60
        assert service.status()['coin_count'] == 1
        assert sounds.cues == ['expired', 'coin']
        now[0] += 10
        service._poll_once(2)  # held coin contact must not keep refilling
        engine.submit(Command(CommandType.SET_VOLUME, 40))
        assert machine.survival.status()['remaining_seconds'] == 50
        assert sounds.cues == ['expired', 'coin']
        assert client.post('/api/survival', json={'minutes': 2}).json['status']['survival']['remaining_seconds'] == 120
        client.post('/api/mode', json={'mode': 'idle'})
        assert rgb.mode == 'party'
        assert not machine.survival.status()['active']
    finally:
        engine.close()
        service.stop()


def test_countdown_leds_are_symmetric_shrink_and_clear_middle(monkeypatch):
    from simple_jukebox import rgb
    class Strip:
        def __init__(self):
            self.pixels = [None] * rgb.LED_COUNT
        def setPixelColor(self, pixel, color):
            self.pixels[pixel] = color
        def show(self):
            pass
    strip = Strip()
    monkeypatch.setattr(rgb, '_get_strip', lambda: strip)
    monkeypatch.setattr(rgb, 'Color', lambda r, g, b: (r, g, b))
    for fraction in (1, .5, .01, 0):
        rgb.render_countdown(fraction)
        assert strip.pixels == strip.pixels[::-1]
        assert all(pixel == (0, 0, 0) for pixel in strip.pixels[rgb.EQUALIZER_SIDE_LENGTH:-rgb.EQUALIZER_SIDE_LENGTH])
        lit = sum(pixel != (0, 0, 0) for pixel in strip.pixels)
        assert lit == {1: 90, .5: 46, .01: 2, 0: 0}[fraction]


@pytest.mark.parametrize('dying', [False, True])
def test_survival_effect_is_valid_non_silent_audio(tmp_path, dying):
    path = tmp_path / 'sound.wav'
    write_effect(path, dying)
    with wave.open(str(path)) as source:
        assert source.getframerate() == 22050
        assert source.getnchannels() == 1
        assert source.getnframes() == 52920
        assert any(source.readframes(source.getnframes()))


def test_sound_worker_cancels_and_cleans_up_temp_audio(monkeypatch):
    audio = SurvivalAudio()
    entered = threading.Event()
    files = []
    def run(command, cancel):
        from pathlib import Path
        if command[0] == 'espeak-ng':
            files.append(Path(command[4]))
        entered.set()
        cancel.wait(1)
        return False
    monkeypatch.setattr(audio, '_run', run)
    audio.play('600')
    assert entered.wait(1)
    audio.stop()
    assert audio._thread is None
    assert audio.error is None
    assert not files[0].parent.exists()


def test_audio_process_is_terminated_and_reaped_on_cancel(monkeypatch):
    class Process:
        returncode = None
        waited = False
        def poll(self):
            return self.returncode
        def terminate(self):
            self.returncode = -15
        def wait(self, timeout):
            self.waited = True
            return self.returncode
    process = Process()
    cancel = threading.Event()
    def spawn(*args, **kwargs):
        cancel.set()
        return process
    monkeypatch.setattr('simple_jukebox.survival_audio.subprocess.Popen', spawn)
    assert SurvivalAudio._run(['paplay', 'sound.wav'], cancel) is False
    assert process.returncode == -15
    assert process.waited


def test_missing_speech_tool_is_reported_without_crashing(monkeypatch):
    audio = SurvivalAudio()
    def missing(*args, **kwargs):
        raise FileNotFoundError('espeak-ng missing')
    monkeypatch.setattr('simple_jukebox.survival_audio.subprocess.Popen', missing)
    audio.play('600')
    audio._thread.join(timeout=1)
    assert audio.error == 'espeak-ng missing'
    audio.stop()


def test_coin_plays_short_bundled_clip_without_speech(monkeypatch):
    from simple_jukebox.survival_audio import COIN_SOUND_DIR
    clip = COIN_SOUND_DIR / 'coin_moan.wav'
    monkeypatch.setattr('simple_jukebox.survival_audio.random.choice', lambda clips: clips[0])
    with wave.open(str(clip)) as source:
        assert 0 < source.getnframes() / source.getframerate() < 3
        assert any(source.readframes(source.getnframes()))
    commands = []
    audio = SurvivalAudio()
    monkeypatch.setattr(audio, '_run', lambda command, cancel: commands.append(command) or True)
    audio.play('coin')
    audio._thread.join(timeout=1)
    assert commands == [['paplay', str(clip)]]
    assert audio.error is None
    audio.stop()


def test_coin_random_selection_rescans_folder_each_time(monkeypatch, tmp_path):
    monkeypatch.setattr('simple_jukebox.survival_audio.COIN_SOUND_DIR', tmp_path)
    first = tmp_path / 'coin_moan1.wav'
    first.touch()
    (tmp_path / 'unrelated.wav').touch()
    (tmp_path / 'coin_moan_folder.wav').mkdir()
    choices, commands = [], []
    def choose(clips):
        choices.append(clips)
        return clips[-1]
    monkeypatch.setattr('simple_jukebox.survival_audio.random.choice', choose)
    audio = SurvivalAudio()
    monkeypatch.setattr(audio, '_run', lambda command, cancel: commands.append(command) or True)
    audio.play('coin')
    audio._thread.join(timeout=1)
    second = tmp_path / 'coin_moan2.wav'
    second.touch()
    audio.play('coin')
    audio._thread.join(timeout=1)
    assert choices == [[first], [first, second]]
    assert commands == [['paplay', str(first)], ['paplay', str(second)]]
    audio.stop()


def test_empty_coin_sound_folder_reports_error(monkeypatch, tmp_path):
    monkeypatch.setattr('simple_jukebox.survival_audio.COIN_SOUND_DIR', tmp_path)
    audio = SurvivalAudio()
    audio.play('coin')
    audio._thread.join(timeout=1)
    assert 'No coin_moan*.wav sounds found' in audio.error
    audio.stop()
