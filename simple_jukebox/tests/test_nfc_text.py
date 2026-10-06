import json
import threading

import pytest

from simple_jukebox.ndef import decode_text_records, read_text_records
from simple_jukebox.nfc import NfcReader
from simple_jukebox.nfc_actions import NfcActions, NfcSpeech
from simple_jukebox.services import JukeboxServices
from simple_jukebox.state_machine import StateMachine
from simple_jukebox.tests.test_state_machine import FakePlayer, FakeBluetooth, UnusedService


def record(text, header=0xd1, encoding='utf-8'):
    payload = bytes([2 | (0x80 if encoding == 'utf-16' else 0)]) + b'en' + text.encode(encoding)
    return bytes([header, 1, len(payload)]) + b'T' + payload


class Tag:
    def __init__(self, message, prefix=b''):
        length = bytes([len(message)]) if len(message) < 255 else b'\xff' + len(message).to_bytes(2, 'big')
        data = prefix + b'\x03' + length + message + b'\xfe'
        self.memory = b'\0' * 12 + bytes([0xe1, 0x10, 109, 0]) + data.ljust(872, b'\0')
        self.pages = []

    def ntag2xx_read_block(self, page):
        self.pages.append(page)
        return self.memory[page * 4:page * 4 + 4]


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16'])
def test_unicode_text(encoding):
    assert read_text_records(Tag(record('Hej æøå 世界', encoding=encoding))) == ['Hej æøå 世界']


def test_multiple_records_and_unrelated_record():
    message = record('first', 0x91) + b'\x11\x01\x02U\x03x' + record('second', 0x51)
    assert read_text_records(Tag(message, b'\0\0')) == ['first', 'second']


def test_extended_lengths_and_id():
    payload = b'\x02en' + b'x' * 300
    message = b'\xc9\x01' + len(payload).to_bytes(4, 'big') + b'\x02Tid' + payload
    assert read_text_records(Tag(message)) == ['x' * 300]


@pytest.mark.parametrize('message', [b'\xd1', b'\xd1\x01\x05T\x02en',
    b'\xd1\x01\x01T\x05', record('x') + b'x', record('x', 0xf1), record('x', 0x91)])
def test_bad_records_are_rejected(message):
    with pytest.raises(ValueError):
        decode_text_records(message)


def test_bounds_and_unsupported_tags():
    tag = Tag(record('hello'))
    tag.memory = tag.memory[:12] + b'\x00\x10\x12\x00' + tag.memory[16:]
    with pytest.raises(ValueError, match='Type 2'):
        read_text_records(tag)
    tag.memory = b'\0' * 12 + b'\xe1\x10\x01\x00\x03\xff\xff\xff'
    with pytest.raises(ValueError, match='capacity'):
        read_text_records(tag)
    assert max(tag.pages) == 4


def test_lock_bytes_outside_ndef_area_and_reserved_bytes_inside():
    # NTAG213: dynamic lock bytes at byte 160, following 144-byte data area.
    tag = Tag(record('hello'), b'\x01\x03\xa0\x0c\x34')
    tag.memory = tag.memory[:14] + b'\x12' + tag.memory[15:]
    assert read_text_records(tag) == ['hello']
    with pytest.raises(ValueError, match='Reserved memory'):
        read_text_records(Tag(record('hello'), b'\x02\x03\x40\x04\x02'))


def test_reader_reads_once_and_preserves_uid_on_text_error():
    reader = NfcReader()
    tag = Tag(record('hello'))
    reader._record(b'1234567', tag)
    reads = len(tag.pages)
    reader._record(b'1234567', tag)
    assert len(tag.pages) == reads
    assert reader.drain_events() == [{'uid': b'1234567'.hex().upper(), 'texts': ['hello'], 'error': None}]
    reader._record(None)
    assert reader.status()['texts'] == []
    assert reader.status()['last_texts'] == ['hello']
    reader._record(b'1234567', tag)
    assert len(reader.drain_events()) == 1
    reader._record(b'7654321', Tag(b'\xd1'))
    assert reader.status()['uid'] == b'7654321'.hex().upper()
    assert reader.status()['text_error']
    assert reader.drain_events()[0]['texts'] == []


class Speech:
    error = None
    playing = False
    def speak(self, text, voice, rate):
        self.playing = True
        self.args = (text, voice, rate)
    def stop(self):
        self.playing = False


def actions(tmp_path):
    player = FakePlayer()
    player.tracks = lambda: ['song.mp3']
    path = tmp_path / 'actions.json'
    path.write_text(json.dumps({'music': {'type': 'file', 'file': 'song.mp3'},
                               'hello': {'type': 'tts', 'text': 'Hej', 'voice': 'da'}}))
    return NfcActions(player, path, Speech())


def test_mapping_reload_first_match_and_audio_replacement(tmp_path):
    action = actions(tmp_path)
    action.trigger(['unknown', 'hello', 'music'])
    assert action.speech.args == ('Hej', 'da', 145)
    assert action.status()['speaking']
    action.trigger(['music'])
    assert action.audio.current_track == 'song.mp3'
    assert not action.speech.playing
    action.path.write_text('{"music": {"type":"tts", "text":"Updated"}}')
    action.trigger(['music'])
    assert action.speech.args == ('Updated', 'da', 145)
    assert not action.audio.playing
    action.stop()
    assert not action.speech.playing


@pytest.mark.parametrize('mapping', ['{', '[]', '{"hello": {"type":"file", "file":"../song.mp3"}}',
    '{"hello": {"type":"tts", "text":"hi", "rate":true}}', '{"hello": {"type":"shell"}}'])
def test_bad_mapping_never_starts_audio(tmp_path, mapping):
    action = actions(tmp_path)
    action.path.write_text(mapping)
    assert 'error' in action.trigger(['hello'])
    assert action.status()['error']
    assert not action.speech.playing and not action.audio.playing


def test_unknown_text_does_not_interrupt_playback(tmp_path):
    action = actions(tmp_path)
    action.trigger(['music'])
    assert action.trigger(['unknown']) == 'No mapped NFC text record'
    assert action.audio.playing


def test_nfc_state_poll_stop_and_mode_exit(tmp_path):
    action = actions(tmp_path)
    reader = NfcReader()
    reader.start = lambda: None
    machine = StateMachine(JukeboxServices(action.audio, FakeBluetooth(), UnusedService(),
                            UnusedService(), reader, nfc_actions=action))
    machine.change_mode('nfc')
    reader._record(b'123', Tag(record('hello')))
    machine.poll_nfc()
    assert machine.mode.value == 'nfc'
    assert machine.status()['playing']
    machine.stop_audio()
    assert not machine.status()['playing']
    reader._record(b'456', Tag(record('music')))
    machine.poll_nfc()
    assert action.audio.playing
    machine.change_mode('idle')
    assert not action.audio.playing


def test_speech_uses_text_file_and_pulse_playback(monkeypatch):
    from pathlib import Path
    speech = NfcSpeech()
    commands = []
    def run(command, cancel):
        commands.append(command)
        if command[0] == 'espeak-ng':
            assert Path(command[-1]).read_text() == '-hello; $(anything)'
        return True
    monkeypatch.setattr(speech, '_run', run)
    speech.speak('-hello; $(anything)', 'da', 160)
    speech._thread.join(1)
    assert [command[0] for command in commands] == ['espeak-ng', 'paplay']
    assert commands[0][1:5] == ['-v', 'da', '-s', '160']
    assert not speech.error
    assert not speech.playing
    assert not Path(commands[0][-1]).exists()


def test_speech_stop_cancels_synthesis_before_playback(monkeypatch):
    speech = NfcSpeech()
    started = threading.Event()
    commands = []
    def run(command, cancel):
        commands.append(command[0])
        started.set()
        assert cancel.wait(1)
        return False
    monkeypatch.setattr(speech, '_run', run)
    speech.speak('Hej')
    assert started.wait(1)
    speech.stop()
    assert commands == ['espeak-ng']
    assert not speech.playing


def test_command_worker_handles_scans_without_browser(tmp_path):
    from simple_jukebox.engine import Command, CommandEngine, CommandType
    from simple_jukebox.tests.test_web import FakeRgb
    action = actions(tmp_path)
    reader = NfcReader()
    reader.start = lambda: None
    services = JukeboxServices(action.audio, FakeBluetooth(), UnusedService(), FakeRgb(),
                               reader, nfc_actions=action)
    machine = StateMachine(services)
    handled = threading.Event()
    original = action.trigger
    def trigger(texts):
        result = original(texts)
        handled.set()
        return result
    action.trigger = trigger
    engine = CommandEngine(machine, services)
    try:
        engine.submit(Command(CommandType.CHANGE_MODE, 'nfc'))
        reader._record(b'123', Tag(record('hello')))
        assert handled.wait(1)
        assert action.speech.playing
        engine.submit(Command(CommandType.CHANGE_MODE, 'idle'))
        assert not action.speech.playing
    finally:
        engine.close()


def test_utf16_without_bom_is_big_endian():
    payload = b'\x82da' + 'Blå'.encode('utf-16-be')
    message = bytes([0xd1, 1, len(payload)]) + b'T' + payload
    assert decode_text_records(message) == ['Blå']
