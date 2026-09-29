"""Offline spoken warnings and original synthesized survival sound effects."""
from __future__ import annotations

import math
import struct
import subprocess
import tempfile
import threading
import wave
from pathlib import Path


COIN_SOUND = Path(__file__).with_name('assets') / 'coin_moan.wav'

WARNINGS = {
    '600': '10 minutes remaining. Insert a coin to survive.',
    '300': '5 minutes remaining. Insert a coin to survive.',
    '60': '1 minute remaining. Insert a coin now.',
    '30': '30 seconds remaining. I am running out of time.',
    '10': '10 seconds remaining. Insert a coin. Help me!',
}


def write_effect(path, dying=False):
    rate, duration = 22050, 2.4
    samples = bytearray()
    phase = 0.0
    for index in range(int(rate * duration)):
        t = index / rate
        frequency = (650 * (1 - t / duration) + 55) if dying else (880 if int(t * 5) % 2 else 550)
        phase += 2 * math.pi * frequency / rate
        envelope = min(1, t / .025, (duration - t) / .15)
        wobble = .65 + .35 * math.sin(2 * math.pi * 11 * t) if dying else 1
        samples.extend(struct.pack('<h', int(11000 * envelope * wobble * math.sin(phase))))
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        output.writeframes(samples)


class SurvivalAudio:
    """Run synthesis/playback off the command thread; stop cancels either process."""

    def __init__(self):
        self.error = None
        self._thread = None
        self._cancel = threading.Event()

    def play(self, cue):
        if cue not in {'expired', 'coin'} and cue not in WARNINGS:
            raise ValueError('Unknown survival sound')
        self.stop()
        self.error = None
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._play, args=(cue, self._cancel),
                                        name='survival-audio', daemon=True)
        self._thread.start()

    def stop(self):
        self._cancel.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                raise RuntimeError('Survival audio did not stop')
            self._thread = None

    @staticmethod
    def _run(command, cancel):
        if cancel.is_set():
            return False
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            while process.poll() is None:
                if cancel.wait(.025):
                    return False
            if process.returncode:
                raise RuntimeError(f'{command[0]} failed (exit {process.returncode})')
            return not cancel.is_set()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=.5)

    def _play(self, cue, cancel):
        try:
            if cue == 'coin':
                self._run(['paplay', str(COIN_SOUND)], cancel)
                return
            with tempfile.TemporaryDirectory(prefix='jukebox-survival-') as directory:
                path = Path(directory) / 'cue.wav'
                if cue == 'expired':
                    for dying in (False, True):
                        if cancel.is_set():
                            return
                        write_effect(path, dying=dying)
                        if not self._run(['paplay', str(path)], cancel):
                            return
                    speech = 'Time is up. Insert a coin to bring me back to life.'
                else:
                    speech = WARNINGS[cue]
                if self._run(['espeak-ng', '-s', '145', '-w', str(path), speech], cancel):
                    self._run(['paplay', str(path)], cancel)
        except Exception as error:
            if not cancel.is_set():
                self.error = str(error)
