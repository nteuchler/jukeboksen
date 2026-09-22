import threading

from simple_jukebox.engine import Command, CommandEngine, CommandType
from simple_jukebox.services import JukeboxServices
from simple_jukebox.tests.test_state_machine import FakeBluetooth, FakePlayer
from simple_jukebox.state_machine import StateMachine
from simple_jukebox.tests.test_web import FakeRgb, FakeVolume


def test_encoder_volume_commands_accumulate_and_clamp():
    volume = FakeVolume()
    services = JukeboxServices(FakePlayer(), FakeBluetooth(), volume, FakeRgb())
    engine = CommandEngine(StateMachine(services), services)
    try:
        futures = [engine.enqueue(Command(CommandType.ADJUST_VOLUME, 5)) for _ in range(3)]
        for future in futures:
            future.result(timeout=2)
        assert volume.value == 55
        engine.submit(Command(CommandType.SET_VOLUME, 98))
        engine.submit(Command(CommandType.ADJUST_VOLUME, 5))
        assert volume.value == 100
        engine.submit(Command(CommandType.SET_VOLUME, 2))
        engine.submit(Command(CommandType.ADJUST_VOLUME, -5))
        assert volume.value == 0
    finally:
        engine.close()


def test_engine_routes_commands_to_services_on_its_worker_thread():
    player = FakePlayer()
    bluetooth = FakeBluetooth()
    volume = FakeVolume()
    rgb = FakeRgb()
    services = JukeboxServices(player, bluetooth, volume, rgb)
    machine = StateMachine(services)
    engine = CommandEngine(machine, services)
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


def test_encoder_mutes_output_in_any_mode_without_changing_volume():
    volume = FakeVolume()
    toggles = []
    volume.toggle_mute = lambda: toggles.append(True)
    services = JukeboxServices(FakePlayer(), FakeBluetooth(), volume, FakeRgb())
    engine = CommandEngine(StateMachine(services), services)
    try:
        engine.submit(Command(CommandType.TOGGLE_OUTPUT_MUTE))
        engine.submit(Command(CommandType.TOGGLE_OUTPUT_MUTE))
        assert toggles == [True, True]
        assert volume.value == 40
    finally:
        engine.close()
