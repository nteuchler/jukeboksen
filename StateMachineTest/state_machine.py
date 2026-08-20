"""Small, hardware-independent state machine for the jukebox."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum


class Mode(str, Enum):
    IDLE = "idle"
    BLUETOOTH = "bluetooth"
    ACTIVITY = "activity"


class CommandType(str, Enum):
    SWITCH_MODE = "switch_mode"
    NEXT = "next"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class Command:
    type: CommandType
    value: str | None = None


class StateMachine:
    """Owns the current mode and handles commands one at a time."""

    def __init__(self) -> None:
        self.mode = Mode.IDLE
        self.step = 0
        self.running = False
        self.commands: asyncio.Queue[Command] = asyncio.Queue()

    def status(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "step": self.step,
            "running": self.running,
        }

    async def send(self, command: Command) -> None:
        """Place a command in the queue without changing state directly."""
        await self.commands.put(command)

    async def handle(self, command: Command) -> None:
        """Apply one command. Kept public so it is easy to unit-test."""
        if command.type is CommandType.SWITCH_MODE:
            if command.value is None:
                raise ValueError("switch_mode requires a mode")
            try:
                self.mode = Mode(command.value)
            except ValueError as error:
                valid = ", ".join(mode.value for mode in Mode)
                raise ValueError(f"Unknown mode '{command.value}'. Use: {valid}") from error
            self.step = 0

        elif command.type is CommandType.NEXT:
            self.step += 1

        elif command.type is CommandType.SHUTDOWN:
            self.running = False

    async def run(self) -> None:
        """Wait for and process commands until shutdown is requested."""
        self.running = True
        while self.running:
            command = await self.commands.get()
            try:
                await self.handle(command)
            finally:
                self.commands.task_done()

