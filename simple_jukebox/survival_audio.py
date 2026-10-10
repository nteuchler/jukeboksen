"""Cancellable playback of the bundled coin survival recordings."""
from __future__ import annotations

import random
import subprocess
import tempfile
import threading
from pathlib import Path


COIN_SOUND_DIR = Path(__file__).with_name('assets') / 'Coin'
CUE_PATTERNS = {
    'coin': 'Tak_*.mp3',
    '1200': '20min_*.mp3',
    '900': '15min_*.mp3',
    '600': '10min_*.mp3',
    '300': '5min_*.mp3',
    '60': '1min_*.mp3',
    '10': 'Nedtælling.mp3',
    'expired': 'Smerte_*.mp3',
}


class SurvivalAudio:
    """Decode and play recordings off the command thread; stop cancels either process."""

    def __init__(self):
        self.error = None
        self._thread = None
        self._cancel = threading.Event()

    def play(self, cue):
        if cue not in CUE_PATTERNS:
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
            pattern = CUE_PATTERNS[cue]
            clips = sorted(path for path in COIN_SOUND_DIR.glob(pattern) if path.is_file())
            if not clips:
                raise FileNotFoundError(f'No {pattern} sounds found in {COIN_SOUND_DIR}')
            clip = random.choice(clips)
            with tempfile.TemporaryDirectory(prefix='jukebox-survival-') as directory:
                path = Path(directory) / 'cue.wav'
                if self._run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                              '-i', str(clip), str(path)], cancel):
                    self._run(['paplay', str(path)], cancel)
        except Exception as error:
            if not cancel.is_set():
                self.error = str(error)
