from __future__ import annotations

from magical_jukebox.services.interfaces import EventSink


class BaseEventService:
    def __init__(self) -> None:
        self._event_sink: EventSink | None = None

    def set_event_sink(self, sink: EventSink) -> None:
        self._event_sink = sink
