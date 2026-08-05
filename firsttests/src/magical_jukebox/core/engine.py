from __future__ import annotations

import asyncio
import logging
from threading import Event as ThreadEvent
from threading import Lock, Thread

from magical_jukebox.core.enums import CommandType
from magical_jukebox.core.messages import Command, Message
from magical_jukebox.core.mode_registry import ModeRegistry
from magical_jukebox.core.state_machine import StateMachine
from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.interfaces import ServiceBundle

logger = logging.getLogger(__name__)


class Engine:
    """Runs the asyncio state machine in a dedicated daemon thread."""

    def __init__(
        self,
        *,
        status_store: StatusStore,
        registry: ModeRegistry,
        services: ServiceBundle,
    ) -> None:
        self.status_store = status_store
        self.registry = registry
        self.services = services
        self._thread: Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._inbox: asyncio.Queue[Message] | None = None
        self._ready = ThreadEvent()
        self._start_stop_lock = Lock()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._loop)

    def start(self) -> None:
        with self._start_stop_lock:
            if self.running:
                return
            self._ready.clear()
            self._thread = Thread(target=self._thread_main, name="jukebox-engine", daemon=True)
            self._thread.start()

        if not self._ready.wait(timeout=5):
            raise RuntimeError("Jukebox engine did not start")

    def submit(self, command: Command) -> None:
        if not self.running or self._loop is None or self._inbox is None:
            raise RuntimeError("Jukebox engine is not running")
        self._loop.call_soon_threadsafe(self._inbox.put_nowait, command)

    def stop(self) -> None:
        with self._start_stop_lock:
            if not self.running:
                return
            try:
                self.submit(Command(type=CommandType.SHUTDOWN, source="engine"))
            except RuntimeError:
                return
            thread = self._thread

        if thread:
            thread.join(timeout=3)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        inbox: asyncio.Queue[Message] = asyncio.Queue()
        self._loop = loop
        self._inbox = inbox

        state_machine = StateMachine(
            status_store=self.status_store,
            registry=self.registry,
            services=self.services,
            inbox=inbox,
        )
        self._ready.set()

        try:
            loop.run_until_complete(state_machine.run())
        except Exception:
            logger.exception("Engine thread crashed")
            self.status_store.patch(
                state="error",
                message="Engine thread crashed",
            )
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            self._loop = None
            self._inbox = None
            self._ready.clear()
