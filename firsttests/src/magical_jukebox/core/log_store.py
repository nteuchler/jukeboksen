from __future__ import annotations

import logging
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import RLock


@dataclass(slots=True, frozen=True)
class LogEntry:
    sequence: int
    timestamp: str
    level: str
    logger: str
    message: str


class LogStore:
    def __init__(self, max_entries: int = 500) -> None:
        self._entries: deque[LogEntry] = deque(maxlen=max_entries)
        self._lock = RLock()
        self._sequence = 0

    def append(self, *, level: str, logger: str, message: str) -> None:
        with self._lock:
            self._sequence += 1
            self._entries.append(
                LogEntry(
                    sequence=self._sequence,
                    timestamp=datetime.now(UTC).isoformat(),
                    level=level,
                    logger=logger,
                    message=message,
                )
            )

    def read(self, *, after: int = 0, limit: int = 200) -> list[dict[str, object]]:
        with self._lock:
            entries = [entry for entry in self._entries if entry.sequence > after]
            return [asdict(entry) for entry in entries[-limit:]]


class RingBufferLogHandler(logging.Handler):
    def __init__(self, store: LogStore) -> None:
        super().__init__()
        self.store = store

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            self.store.append(
                level=record.levelname,
                logger=record.name,
                message=message,
            )
        except Exception:
            self.handleError(record)
