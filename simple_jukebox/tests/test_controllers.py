from io import StringIO

from simple_jukebox.controllers import BluetoothSpeaker


class FakeBluetoothctlProcess:
    def __init__(self):
        self.stdin = StringIO()

    def poll(self):
        return None

    def wait(self, timeout):
        return 0


def test_stopping_bluetooth_disconnects_audio_before_quitting():
    speaker = BluetoothSpeaker()
    process = FakeBluetoothctlProcess()
    speaker.process = process

    speaker.stop()

    assert process.stdin.getvalue().splitlines() == [
        "discoverable off",
        "pairable off",
        "power off",
        "quit",
    ]
    assert speaker.process is None
