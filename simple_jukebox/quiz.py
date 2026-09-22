"""Bluetooth media controls and an original synthesized quiz buzzer."""
from __future__ import annotations

import json
import math
import struct
import subprocess
import tempfile
import wave
from pathlib import Path


class BluetoothMedia:
    def __init__(self):
        self.device = None

    def reset(self):
        self.device = None

    @staticmethod
    def _call(path, interface, method):
        result = subprocess.run(
            ['busctl', '--system', '--timeout=2', '--json=short', 'call',
             'org.bluez', path, interface, method],
            capture_output=True, text=True, timeout=3, check=True,
        )
        return json.loads(result.stdout)['data'][0] if result.stdout.strip() else None

    def _player(self):
        objects = self._call('/', 'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects')
        candidates = []
        for path, interfaces in objects.items():
            props = interfaces.get('org.bluez.MediaPlayer1')
            if props is None:
                continue
            device = props.get('Device', {}).get('data', path.rsplit('/player', 1)[0])
            connected = objects.get(device, {}).get('org.bluez.Device1', {}).get('Connected', {}).get('data')
            if connected and (self.device is None or device == self.device):
                candidates.append((path, props.get('Status', {}).get('data'), device))
        if not candidates:
            raise RuntimeError('No Bluetooth media player available; connect your phone and start music')
        return next((item for item in candidates if item[1] == 'playing'), candidates[0])

    def pause(self):
        path, status, device = self._player()
        self.device = device
        self._call(path, 'org.bluez.MediaPlayer1', 'Pause')

    def playback_status(self):
        return self._player()[1]


class QuizBuzzer:
    """Play a brief two-tone buzz at the current output's volume."""
    def __init__(self):
        self.process = None
        self._directory = None

    def play(self):
        self.stop()
        self._directory = tempfile.TemporaryDirectory(prefix='jukebox-buzzer-')
        path = Path(self._directory.name) / 'buzzer.wav'
        rate, duration = 22050, 0.45
        samples = bytearray()
        for index in range(int(rate * duration)):
            t = index / rate
            envelope = min(1.0, t / .01, (duration - t) / .06)
            tone = math.sin(2 * math.pi * 180 * t) + .45 * math.sin(2 * math.pi * 270 * t)
            samples.extend(struct.pack('<h', int(9000 * envelope * tone)))
        with wave.open(str(path), 'wb') as output:
            output.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            output.writeframes(samples)
        self.process = subprocess.Popen(['paplay', str(path)], stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)

    def stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
            self.process = None
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None
