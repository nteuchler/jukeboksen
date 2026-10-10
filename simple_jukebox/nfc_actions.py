"""Editable NFC text mappings and cancellable offline speech."""
import json
import sys
import tempfile
import threading
from pathlib import Path

from simple_jukebox.survival_audio import SurvivalAudio
from simple_jukebox.participant_jingles import sentence_parts


class NfcSpeech(SurvivalAudio):
    @property
    def playing(self):
        return self._thread is not None and self._thread.is_alive()

    def speak(self, text, voice='da', rate=145):
        self.stop()
        self.error = None
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._speak, args=(text, voice, rate, self._cancel),
                                        name='nfc-speech', daemon=True)
        self._thread.start()

    def _speak(self, text, voice, rate, cancel):
        try:
            with tempfile.TemporaryDirectory(prefix='jukebox-nfc-') as directory:
                text_path = Path(directory) / 'text.txt'
                wav_path = Path(directory) / 'speech.wav'
                for part, jingle in sentence_parts(text):
                    if cancel.is_set():
                        return
                    if jingle is not None:
                        ready = self._run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
                                           '-i', str(jingle), str(wav_path)], cancel)
                    elif any(character.isalnum() for character in part):
                        text_path.write_text(part, encoding='utf-8')
                        ready = self._run(['espeak-ng', '-v', voice, '-s', str(rate), '-w',
                                           str(wav_path), '-f', str(text_path)], cancel)
                    else:
                        continue
                    if not ready or not self._run(['paplay', str(wav_path)], cancel):
                        return
        except Exception as error:
            if not cancel.is_set():
                self.error = str(error)

    def text2music(self, text):
        self.stop()
        self.error = None
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._music, args=(text, self._cancel),
                                        name='text2music', daemon=True)
        self._thread.start()

    def _music(self, text, cancel):
        try:
            with tempfile.TemporaryDirectory(prefix='jukebox-text2music-') as directory:
                folder = Path(directory)
                text_path, wav_path, error_path = (folder / name for name in ('text.txt', 'music.wav', 'error.txt'))
                text_path.write_text(text, encoding='utf-8')
                library = Path(__file__).resolve().parent.parent / 'Text2Speech' / 'output'
                try:
                    ready = self._run([sys.executable, '-m', 'simple_jukebox.text2music',
                                       str(text_path), str(wav_path), str(library), str(error_path)], cancel)
                except Exception:
                    if error_path.exists():
                        raise RuntimeError(error_path.read_text(encoding='utf-8')) from None
                    raise
                if ready:
                    self._run(['paplay', str(wav_path)], cancel)
        except Exception as error:
            if not cancel.is_set():
                self.error = f'text2Music: {error}'


class NfcActions:
    def __init__(self, audio, path=None, speech=None):
        self.audio = audio
        self.path = Path(path) if path else Path(__file__).with_name('nfc_actions.json')
        self.speech = speech if speech is not None else NfcSpeech()
        self.match = None
        self.error = None
        self.selected_action = None

    def status(self):
        return {'match': self.match, 'error': self.error or self.speech.error,
                'speaking': self.speech.playing}

    def stop(self):
        self.speech.stop()
        self.audio.stop()
        self.error = None
        self.speech.error = None

    def mappings(self):
        mappings = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(mappings, dict):
            raise ValueError('NFC mapping must be a JSON object')
        return mappings

    def choices(self):
        choices = []
        for text, action in self.mappings().items():
            if not isinstance(action, dict) or action.get('type') not in ('file', 'tts', 'text2music'):
                raise ValueError(f'Invalid NFC action for {text!r}')
            kind = action['type']
            choices.append({'text': text, 'type': kind,
                            'description': str(action.get('file' if kind == 'file' else 'text', ''))})
        return choices

    def trigger(self, texts):
        self.match = None
        self.error = None
        try:
            mappings = self.mappings()
            for text in texts:
                if text not in mappings:
                    continue
                action = mappings[text]
                if not isinstance(action, dict):
                    raise ValueError(f'Invalid action for {text!r}')
                kind = action.get('type')
                self.play_action(action)
                self.match = text
                return f'NFC: {text} — ' + (f"Playing {action['file']}" if kind == 'file' else 'Playing text2Music' if kind == 'text2music' else 'Speaking')
            return 'No mapped NFC text record' if texts else 'Tag has no NDEF Text records'
        except Exception as error:
            self.error = str(error)
            return f'NFC playback error: {error}'

    def play_action(self, action):
        kind = action.get('type')
        if kind == 'file':
            track = action.get('file')
            if not isinstance(track, str) or Path(track).name != track or track not in self.audio.tracks():
                raise ValueError('NFC file must name an available file in simple_jukebox/media')
            self.stop()
            self.speech.error = None
            self.audio.play(track)
        elif kind in {'tts', 'text2music'}:
            speech = action.get('text')
            voice = action.get('voice', 'da')
            rate = action.get('rate', 145)
            if not isinstance(speech, str) or not speech.strip() or len(speech) > 10000:
                raise ValueError('TTS text must contain 1–10000 characters')
            if not isinstance(voice, str) or not voice or voice.startswith('-'):
                raise ValueError('TTS voice must be an espeak-ng voice name')
            if type(rate) is not int or not 80 <= rate <= 450:
                raise ValueError('TTS rate must be an integer between 80 and 450')
            self.stop()
            if kind == 'text2music':
                self.speech.text2music(speech)
            else:
                self.speech.speak(speech, voice, rate)
        else:
            raise ValueError(f'Unknown NFC action type: {kind!r}')
        self.error = None
        self.selected_action = dict(action)
