from simple_jukebox.state_machine import StateMachine


class FakePlayer:
    def __init__(self):
        self.playing = False
        self.current_track = None
        self.muted = False

    def play(self, track):
        self.playing = True
        self.current_track = track

    def stop(self):
        self.playing = False
        self.current_track = None
        self.muted = False

    def toggle_mute(self):
        if not self.playing:
            raise RuntimeError("Nothing is playing")
        self.muted = not self.muted
        return self.muted


class FakeBluetooth:
    def __init__(self):
        self.active = False

    def start(self):
        self.active = True

    def stop(self):
        self.active = False


def test_switching_modes_cleans_up_previous_mode():
    player = FakePlayer()
    bluetooth = FakeBluetooth()
    machine = StateMachine(player, bluetooth)

    machine.change_mode("local_files")
    machine.play("song.mp3")
    machine.change_mode("bluetooth")
    assert not player.playing
    assert bluetooth.active

    machine.change_mode("idle")
    assert not bluetooth.active
    assert machine.status()["mode"] == "idle"


def test_audio_requires_local_files_mode():
    machine = StateMachine(FakePlayer(), FakeBluetooth())
    try:
        machine.play("song.mp3")
    except RuntimeError as error:
        assert "Local files" in str(error)
    else:
        raise AssertionError("play should have failed")
