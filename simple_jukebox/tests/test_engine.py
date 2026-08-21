import threading

from simple_jukebox.engine import Command, CommandEngine, CommandType
from simple_jukebox.tests.test_state_machine import FakeBluetooth, FakePlayer
from simple_jukebox.state_machine import StateMachine
from simple_jukebox.tests.test_web import FakeRgb, FakeVolume


def test_engine_routes_commands_to_services_on_its_worker_thread():
    player = FakePlayer()
    bluetooth = FakeBluetooth()
    volume = FakeVolume()
    rgb = FakeRgb()
    machine = StateMachine(player, bluetooth)
    engine = CommandEngine(machine, volume, rgb)
    caller_thread = threading.get_ident()
    handled_threads = []
    original_change_mode = machine.change_mode

    def record_change_mode(mode):
        handled_threads.append(threading.get_ident())
        return original_change_mode(mode)

    machine.change_mode = record_change_mode
    try:
        engine.submit(Command(CommandType.CHANGE_MODE, "local_files"))
        engine.submit(Command(CommandType.PLAY, "song.mp3"))
        engine.submit(Command(CommandType.SET_VOLUME, 65))
        engine.submit(Command(CommandType.SET_RGB, "equalizer"))

        assert machine.status()["mode"] == "local_files"
        assert player.current_track == "song.mp3"
        assert volume.value == 65
        assert rgb.mode == "equalizer"
        assert handled_threads[0] != caller_thread
    finally:
        engine.close()
