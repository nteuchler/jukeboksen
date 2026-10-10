import json
import threading
import wave

from simple_jukebox import participant_jingles
from simple_jukebox.nfc_actions import NfcSpeech
from simple_jukebox.participant_jingles import sentence_parts
from simple_jukebox.text2music import render


def write_clip(path):
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\x10\x01' * 2205)


def test_names_boundaries_phrases_repeats_and_alias(tmp_path):
    for name in ['Carl Christian.mp3', 'Carl.mp3', 'Eskilds Jingle.mp3', 'Lea.mp3']:
        (tmp_path / name).touch()
    parts = sentence_parts('Hej CARL CHRISTIAN, Eskild og Lea! Leander Lea.', tmp_path)
    assert ''.join(text for text, _ in parts) == 'Hej CARL CHRISTIAN, Eskild og Lea! Leander Lea.'
    assert [clip.name for _, clip in parts if clip] == [
        'Carl Christian.mp3', 'Eskilds Jingle.mp3', 'Lea.mp3', 'Lea.mp3']
    assert sentence_parts('Hej verden', tmp_path) == [('Hej verden', None)]


def test_tts_plays_jingle_between_speech_and_can_cancel(tmp_path, monkeypatch):
    (tmp_path / 'Lea.mp3').touch()
    monkeypatch.setattr(participant_jingles, 'JINGLE_DIR', tmp_path)
    commands = []
    cancel = threading.Event()
    speech = NfcSpeech()
    def run(command, event):
        commands.append(command[0])
        return True
    monkeypatch.setattr(speech, '_run', run)
    speech._speak('Hej Lea farvel', 'da', 145, cancel)
    assert commands == ['espeak-ng', 'paplay', 'ffmpeg', 'paplay', 'espeak-ng', 'paplay']
    commands.clear()
    def stop_on_jingle(command, event):
        commands.append(command[0])
        if command[0] == 'ffmpeg':
            event.set()
            return False
        return True
    monkeypatch.setattr(speech, '_run', stop_on_jingle)
    speech._speak('Hej Lea farvel', 'da', 145, cancel)
    assert commands == ['espeak-ng', 'paplay', 'ffmpeg']


def test_music_inserts_complete_jingle_and_supports_names_only(tmp_path):
    jingles = tmp_path / 'jingles'
    jingles.mkdir()
    write_clip(jingles / 'Lea.wav')
    write_clip(tmp_path / 'hej.wav')
    (tmp_path / 'index.json').write_text(json.dumps({'clips': [
        {'word': 'hej', 'file': 'hej.wav', 'score': 1.0, 'approved': True}]}))
    destination = tmp_path / 'result.wav'
    render('hej Lea hej', destination, tmp_path, jingles)
    with wave.open(str(destination)) as audio:
        assert .65 < audio.getnframes() / audio.getframerate() < .67
    render('Lea', destination, tmp_path / 'missing-library', jingles)
    with wave.open(str(destination)) as audio:
        assert audio.getnframes() / audio.getframerate() == .1
