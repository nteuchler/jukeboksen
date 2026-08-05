from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from magical_jukebox.core.enums import CommandType, EventType, ModeName, RuntimeState
from magical_jukebox.core.messages import Command, Event, Message
from magical_jukebox.core.mode_registry import ModeRegistry
from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.modes.base import BaseMode, ModeContext
from magical_jukebox.services.interfaces import ServiceBundle

logger = logging.getLogger(__name__)


class StateMachine:
    def __init__(
        self,
        *,
        status_store: StatusStore,
        registry: ModeRegistry,
        services: ServiceBundle,
        inbox: asyncio.Queue[Message],
    ) -> None:
        self.status_store = status_store
        self.registry = registry
        self.services = services
        self.inbox = inbox
        self.current_mode: BaseMode | None = None
        self.current_mode_name: ModeName | None = None
        self._running = False

        self.services.set_event_sink(self.emit_event)

    async def emit_event(self, event: Event) -> None:
        await self.inbox.put(event)

    async def run(self) -> None:
        self._running = True
        logger.info("State machine starting")
        await self._switch_mode(ModeName.IDLE)

        while self._running:
            message = await self.inbox.get()
            try:
                if isinstance(message, Command):
                    await self._handle_command(message)
                else:
                    await self._handle_event(message)
            except Exception as exc:
                logger.exception("Unhandled state-machine error")
                self.status_store.patch(
                    state=RuntimeState.ERROR.value,
                    message="Unhandled state-machine error",
                    last_error=str(exc),
                )
            finally:
                self.inbox.task_done()

        await self._shutdown_current_mode()
        self.status_store.patch(
            state=RuntimeState.STOPPED.value,
            message="Engine stopped",
            expects_input=False,
        )
        logger.info("State machine stopped")

    async def _handle_command(self, command: Command) -> None:
        logger.info("Command received: %s payload=%s", command.type.value, command.payload)

        if command.type is CommandType.SHUTDOWN:
            self._running = False
            return

        if command.type is CommandType.CHANGE_MODE:
            raw_mode = command.payload.get("mode")
            try:
                target = ModeName(str(raw_mode))
            except ValueError:
                self._report_user_error(f"Unknown mode: {raw_mode!r}")
                return
            await self._switch_mode(target)
            return

        if command.type is CommandType.PLAY_AUDIO:
            track = command.payload.get("track")
            if not isinstance(track, str) or not track:
                self._report_user_error("play_audio requires a track")
                return
            await self.services.audio.play(track)
            return

        if command.type is CommandType.STOP_AUDIO:
            await self.services.audio.stop()
            return

        if command.type is CommandType.SIMULATE_BUTTON:
            button_id = command.payload.get("button_id")
            try:
                parsed_button_id = int(button_id)
            except (TypeError, ValueError):
                self._report_user_error("simulate_button requires an integer button_id")
                return
            await self.services.hardware.simulate_button(parsed_button_id)
            return

        if command.type is CommandType.SIMULATE_BLUETOOTH_CONNECT:
            device = str(command.payload.get("device") or "Test phone")
            await self.services.bluetooth.simulate_connected(device)
            return

        if command.type is CommandType.SIMULATE_BLUETOOTH_DISCONNECT:
            await self.services.bluetooth.simulate_disconnected()
            return

        if command.type is CommandType.LIGHTING_SET_PIXEL:
            try:
                pixel_index = int(command.payload.get("pixel_index"))
                red = int(command.payload.get("red"))
                green = int(command.payload.get("green"))
                blue = int(command.payload.get("blue"))
            except (TypeError, ValueError):
                self._report_user_error(
                    "lighting_set_pixel requires integer pixel_index, red, green, and blue"
                )
                return
            await self.services.lighting.set_pixel(pixel_index, red, green, blue)
            return

        if command.type is CommandType.LIGHTING_FILL:
            try:
                red = int(command.payload.get("red"))
                green = int(command.payload.get("green"))
                blue = int(command.payload.get("blue"))
            except (TypeError, ValueError):
                self._report_user_error("lighting_fill requires integer red, green, and blue")
                return
            await self.services.lighting.fill(red, green, blue)
            return

        if command.type is CommandType.LIGHTING_CLEAR:
            await self.services.lighting.clear()
            return

        if self.current_mode is None:
            self._report_user_error("No active mode")
            return

        if command.type is CommandType.RESET_MODE:
            assert self.current_mode_name is not None
            await self._switch_mode(self.current_mode_name, force_restart=True)
            return

        await self.current_mode.handle_command(command)

    async def _handle_event(self, event: Event) -> None:
        logger.info("Event received: %s payload=%s", event.type.value, event.payload)
        if self.current_mode is not None:
            await self.current_mode.handle_event(event)

    async def _switch_mode(self, target: ModeName, *, force_restart: bool = False) -> None:
        if target == self.current_mode_name and not force_restart:
            logger.info("Mode %s is already active", target.value)
            return

        definition = self.registry.get(target)
        if not definition.enabled:
            self._report_user_error(
                f"Mode {definition.label!r} is disabled: {definition.disabled_reason}"
            )
            return

        await self._shutdown_current_mode()

        context = ModeContext(
            status_store=self.status_store,
            services=self.services,
            emit_event=self.emit_event,
        )
        mode = self.registry.create(target, context)
        self.current_mode = mode
        self.current_mode_name = target

        self.status_store.patch(
            mode=target.value,
            mode_label=definition.label,
            state=RuntimeState.STARTING.value,
            message=f"Starting {definition.label}",
            expects_input=False,
            microphone_active=False,
            last_error=None,
        )
        logger.info("Entering mode %s", target.value)
        await mode.enter()

    async def _shutdown_current_mode(self) -> None:
        if self.current_mode is None:
            return
        logger.info("Exiting mode %s", self.current_mode_name.value if self.current_mode_name else "unknown")
        try:
            await self.current_mode.exit()
        finally:
            self.current_mode = None
            self.current_mode_name = None

    def _report_user_error(self, message: str) -> None:
        logger.warning(message)
        self.status_store.patch(message=message, last_error=message)
