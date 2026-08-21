"""Async command queue bridging Flask requests to the jukebox state machine."""

from __future__ import annotations

import asyncio
import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from enum import Enum
from typing import Any

from simple_jukebox.services import JukeboxServices


class CommandType(str, Enum):
    CHANGE_MODE = "change_mode"
    PLAY = "play"
    STOP = "stop"
    TOGGLE_MUTE = "toggle_mute"
    SET_VOLUME = "set_volume"
    SET_RGB = "set_rgb"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class Command:
    type: CommandType
    value: Any = None


@dataclass
class _QueuedCommand:
    command: Command
    result: Future


class CommandEngine:
    """Process every state-changing command sequentially on one async queue."""

    def __init__(self, machine: Any, services: JukeboxServices) -> None:
        self.machine = machine
        self.services = services
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[_QueuedCommand] | None = None
        self._incoming: queue.Queue[_QueuedCommand] = queue.Queue()
        self._ready = threading.Event()
        self._closed = False
        self._thread = threading.Thread(
            target=self._thread_main,
            name="jukebox-command-engine",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("Jukebox command engine did not start")

    def submit(self, command: Command, timeout: float = 10.0) -> Any:
        """Thread-safely enqueue a command and wait for its handled result."""
        if self._closed:
            raise RuntimeError("Jukebox command engine is closed")
        if self._loop is None or self._queue is None:
            raise RuntimeError("Jukebox command engine is unavailable")
        result: Future = Future()
        queued = _QueuedCommand(command, result)
        self._incoming.put(queued)
        return result.result(timeout=timeout)

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.submit(Command(CommandType.SHUTDOWN))
        finally:
            self._closed = True
            if threading.current_thread() is not self._thread:
                self._thread.join(timeout=5)

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._ready.set()
        running = True
        while running:
            while True:
                try:
                    self._queue.put_nowait(self._incoming.get_nowait())
                except queue.Empty:
                    break
            if self._queue.empty():
                await asyncio.sleep(0.01)
                continue
            queued = self._queue.get_nowait()
            try:
                running = queued.command.type is not CommandType.SHUTDOWN
                value = self._handle(queued.command)
            except Exception as error:
                queued.result.set_exception(error)
            else:
                queued.result.set_result(value)
            finally:
                self._queue.task_done()

    def _handle(self, command: Command) -> Any:
        if command.type is CommandType.CHANGE_MODE:
            return self.machine.change_mode(command.value)
        if command.type is CommandType.PLAY:
            return self.machine.play(command.value)
        if command.type is CommandType.STOP:
            return self.machine.stop_audio()
        if command.type is CommandType.TOGGLE_MUTE:
            return self.machine.toggle_mute()
        if command.type is CommandType.SET_VOLUME:
            return self.services.volume.set(command.value)
        if command.type is CommandType.SET_RGB:
            return self.services.rgb.set_mode(command.value)
        if command.type is CommandType.SHUTDOWN:
            self.machine.close()
            self.services.rgb.close()
            return None
        raise ValueError(f"Unknown command type: {command.type}")
