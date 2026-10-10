"""Scheduled morning alarm, spoken greeting, and internet radio."""
import math
import time
import subprocess
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from simple_jukebox.controllers import VlcPlayer
from simple_jukebox.nfc_actions import NfcSpeech


P8_JAZZ_URL = 'https://live-icy.dr.dk/A/A22H.mp3'
ALARM_FILE = Path(__file__).with_name('assets') / 'AlarmApple.mp3'
ALARM_START_GAIN = 0.5
ALARM_RAMP_SECONDS = 120
GREETING_DELAY_SECONDS = 5


class RisingAlarm:
    """Loop and ramp samples before PulseAudio, without changing output volume."""
    def __init__(self):
        self.decoder = None
        self.player = None

    def start(self):
        self.stop()
        try:
            self.decoder = subprocess.Popen([
                'ffmpeg', '-nostdin', '-loglevel', 'error', '-re', '-stream_loop', '-1',
                '-i', str(ALARM_FILE), '-af',
                f"volume='min(1,{ALARM_START_GAIN}+t*{1 - ALARM_START_GAIN}/{ALARM_RAMP_SECONDS})':eval=frame",
                '-f', 's16le', '-ar', '44100', '-ac', '2', 'pipe:1',
            ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.player = subprocess.Popen([
                'paplay', '--raw', '--rate=44100', '--channels=2', '--format=s16le',
                '--client-name=jukebox-sleep-alarm',
            ], stdin=self.decoder.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.decoder.stdout.close()
        except Exception:
            self.stop()
            raise

    @property
    def playing(self):
        return bool(self.decoder and self.player and
                    self.decoder.poll() is None and self.player.poll() is None)

    def stop(self):
        for process in (self.player, self.decoder):
            if process and process.poll() is None:
                process.terminate()
        for process in (self.player, self.decoder):
            if process:
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
        self.player = self.decoder = None


class SleepingMode:
    def __init__(self, audio=None, speech=None, clock=time.monotonic, alarm=None,
                 wall_clock=time.time):
        self.audio = audio if audio is not None else VlcPlayer(ALARM_FILE.parent)
        self.speech = speech if speech is not None else NfcSpeech()
        self.clock = clock
        self.wall_clock = wall_clock
        self.timezone = ZoneInfo('Europe/Copenhagen')
        self.alarm = alarm if alarm is not None else RisingAlarm()
        self.alarm_time = '08:00'
        self.phase = 'inactive'
        self.deadline = None
        self.error = None
        self.alarm_started = None
        self._volume = None
        self.greeting_at = None

    def configure(self, alarm_time):
        if not isinstance(alarm_time, str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', alarm_time):
            raise ValueError('Enter an alarm time in 24-hour HH:MM format, for example 08:00')
        self.alarm_time = alarm_time
        if self.phase != 'inactive':
            self.start()

    def start(self):
        if not ALARM_FILE.is_file():
            raise FileNotFoundError(f'Alarm file is missing: {ALARM_FILE}')
        self.stop()
        self.error = None
        now = self.wall_clock()
        local = datetime.fromtimestamp(now, self.timezone)
        hour, minute = map(int, self.alarm_time.split(':'))
        target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target.timestamp() <= now:
            target += timedelta(days=1)
        self.deadline = target.timestamp()
        self.phase = 'waiting'

    def stop(self):
        self.alarm.stop()
        self.audio.stop()
        self.speech.stop()
        self.phase = 'inactive'
        self.deadline = None
        self.alarm_started = None
        self._volume = None
        self.greeting_at = None

    def press(self):
        if self.phase == 'alarm':
            self.alarm.stop()
            self.phase = 'greeting_delay'
            self.greeting_at = self.clock() + GREETING_DELAY_SECONDS
        elif self.phase in {'greeting_delay', 'greeting', 'radio'}:
            self.stop()
            self.phase = 'stopped'

    def poll(self):
        try:
            now = self.clock()
            if self.phase == 'waiting' and self.wall_clock() >= self.deadline:
                self.alarm.start()
                self.alarm_started = now
                self._volume = round(ALARM_START_GAIN * 256)
                self.phase = 'alarm'
            elif self.phase == 'alarm':
                if not self.alarm.playing:
                    raise RuntimeError('Alarm playback stopped unexpectedly')
                volume = round(min(1, ALARM_START_GAIN +
                                   (now - self.alarm_started) * (1 - ALARM_START_GAIN) /
                                   ALARM_RAMP_SECONDS) * 256)
                if volume != self._volume:
                    self._volume = volume
            elif self.phase == 'greeting_delay' and now >= self.greeting_at:
                self.speech.speak('Godmorgen gruppe 5', 'da', 145)
                self.phase = 'greeting'
                self.greeting_at = None
            elif self.phase == 'greeting' and not self.speech.playing:
                if self.speech.error:
                    raise RuntimeError(self.speech.error)
                self.audio.play_source(P8_JAZZ_URL, 'P8 Jazz')
                self.phase = 'radio'
            elif self.phase == 'radio' and not self.audio.playing:
                raise RuntimeError('P8 Jazz playback stopped; check the internet connection')
        except Exception as error:
            self.error = str(error)
            self.stop()
            self.phase = 'error'

    def status(self):
        return {'phase': self.phase, 'alarm_time': self.alarm_time,
                'alarm_at': datetime.fromtimestamp(self.deadline, self.timezone).isoformat()
                if self.deadline is not None else None,
                'timezone': self.timezone.key,
                'remaining_seconds': max(0, math.ceil(self.deadline - self.wall_clock()))
                if self.phase == 'waiting' else 0,
                'alarm_volume_percent': round((self._volume or 0) / 256 * 100),
                'error': self.error}
