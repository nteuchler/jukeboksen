from __future__ import annotations

import asyncio
from pathlib import Path

from magical_jukebox.core.enums import EventType
from magical_jukebox.core.messages import Event
from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.base import BaseEventService


class MockAudioService(BaseEventService):
    SUPPORTED_EXTENSIONS = {".mp3", ".wav"}

    def __init__(self, status_store: StatusStore, media_dir: Path) -> None:
        super().__init__()
        self.status_store = status_store
        self.media_dir = media_dir
        self.media_dir.mkdir(parents=True, exist_ok=True)

    def list_media(self) -> list[str]:
        return sorted(
            path.name
            for path in self.media_dir.iterdir()
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS
        )

    async def play(self, track: str) -> None:
        safe_name = Path(track).name
        if safe_name != track:
            raise ValueError("Track must be a filename, not a path")
        if safe_name not in self.list_media():
            raise FileNotFoundError(f"Media file not found: {safe_name}")
        self.status_store.patch_section("audio", playing=True, track=safe_name)
        if self._event_sink:
            await self._event_sink(
                Event(
                    type=EventType.AUDIO_STARTED,
                    payload={"track": safe_name},
                    source="mock_audio",
                )
            )

    async def stop(self) -> None:
        snapshot = self.status_store.snapshot()
        previous_track = snapshot["audio"]["track"]
        self.status_store.patch_section("audio", playing=False, track=None)
        await asyncio.sleep(0)
        if self._event_sink:
            await self._event_sink(
                Event(
                    type=EventType.AUDIO_FINISHED,
                    payload={"track": previous_track},
                    source="mock_audio",
                )
            )
