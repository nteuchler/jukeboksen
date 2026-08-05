import asyncio

from magical_jukebox.core.enums import CommandType, EventType, RuntimeState
from magical_jukebox.core.messages import Command, Event
from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.modes.base import ModeContext
from magical_jukebox.modes.bluetooth_speaker import BluetoothSpeakerMode
from magical_jukebox.modes.placeholder import PlaceholderMode
from magical_jukebox.services.factory import build_services


def make_context(tmp_path):
    store = StatusStore()
    services = build_services(profile="mock", status_store=store, media_dir=tmp_path)
    events = []

    async def emit(event):
        events.append(event)

    services.set_event_sink(emit)
    return store, services, events, ModeContext(store, services, emit)


def test_placeholder_flow(tmp_path):
    async def scenario():
        store, _, _, context = make_context(tmp_path)
        mode = PlaceholderMode(context)
        await mode.enter()
        assert store.snapshot()["state"] == RuntimeState.WAITING.value
        assert store.snapshot()["expects_input"] is True

        await mode.handle_event(Event(type=EventType.BUTTON_PRESSED, payload={"button_id": 2}))
        assert store.snapshot()["state"] == RuntimeState.PLAYING.value

        await mode.handle_command(Command(type=CommandType.FORCE_NEXT))
        assert store.snapshot()["state"] == RuntimeState.COMPLETED.value

    asyncio.run(scenario())


def test_bluetooth_mode_forgets_pairings_and_accepts_connection(tmp_path):
    async def scenario():
        store, services, _, context = make_context(tmp_path)
        mode = BluetoothSpeakerMode(context)
        await mode.enter()

        status = store.snapshot()
        assert status["state"] == RuntimeState.PAIRING.value
        assert status["bluetooth"]["remembered_devices"] == 0
        assert status["bluetooth"]["pairing"] is True

        await mode.handle_event(
            Event(type=EventType.BLUETOOTH_CONNECTED, payload={"device": "Phone"})
        )
        assert store.snapshot()["state"] == RuntimeState.CONNECTED.value

        await mode.exit()
        status = store.snapshot()
        assert status["bluetooth"]["enabled"] is False
        assert status["bluetooth"]["remembered_devices"] == 0

    asyncio.run(scenario())
