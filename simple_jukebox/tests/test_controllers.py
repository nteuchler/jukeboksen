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


def test_bluetooth_events_trust_device_address():
    speaker = BluetoothSpeaker()
    process = FakeBluetoothctlProcess()
    process.stdout = StringIO(
        "[CHG] Device 94:45:60:27:63:4D Connected: yes\n"
        "\x1b[0;93m[CHG]\x1b[0m Device 94:45:60:27:63:4D Paired: yes\n"
        "[CHG] Device 94:45:60:27:63:4D Connected: no\n"
        "[CHG] Device invalid Paired: yes\n"
    )
    speaker.process = process

    speaker._read_output()

    assert process.stdin.getvalue().splitlines() == [
        "trust 94:45:60:27:63:4D",
        "trust 94:45:60:27:63:4D",
    ]
