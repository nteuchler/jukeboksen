from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from magical_jukebox.core.enums import ModeName
from magical_jukebox.modes.base import BaseMode, ModeContext
from magical_jukebox.modes.bluetooth_speaker import BluetoothSpeakerMode
from magical_jukebox.modes.idle import IdleMode
from magical_jukebox.modes.placeholder import PlaceholderMode

ModeFactory = Callable[[ModeContext], BaseMode]


@dataclass(slots=True, frozen=True)
class ModeDefinition:
    name: ModeName
    label: str
    description: str
    enabled: bool
    factory: ModeFactory | None = None
    disabled_reason: str | None = None

    def public_dict(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("factory", None)
        data["name"] = self.name.value
        return data


class ModeRegistry:
    def __init__(self, definitions: list[ModeDefinition]) -> None:
        self._definitions = {definition.name: definition for definition in definitions}

    def get(self, mode_name: ModeName) -> ModeDefinition:
        return self._definitions[mode_name]

    def create(self, mode_name: ModeName, context: ModeContext) -> BaseMode:
        definition = self.get(mode_name)
        if not definition.enabled or definition.factory is None:
            reason = definition.disabled_reason or "Mode is not implemented"
            raise ValueError(f"Mode {mode_name.value!r} is disabled: {reason}")
        return definition.factory(context)

    def public_list(self) -> list[dict[str, object]]:
        return [definition.public_dict() for definition in self._definitions.values()]


def build_mode_registry() -> ModeRegistry:
    return ModeRegistry(
        [
            ModeDefinition(
                name=ModeName.IDLE,
                label="Idle",
                description="Safe waiting mode.",
                enabled=True,
                factory=IdleMode,
            ),
            ModeDefinition(
                name=ModeName.PLACEHOLDER,
                label="Placeholder activity",
                description="Test flow for state transitions and virtual buttons.",
                enabled=True,
                factory=PlaceholderMode,
            ),
            ModeDefinition(
                name=ModeName.BLUETOOTH_SPEAKER,
                label="Bluetooth speaker",
                description="Bluetooth speaker flow using the simulated service on PC.",
                enabled=True,
                factory=BluetoothSpeakerMode,
            ),
            ModeDefinition(
                name=ModeName.MUSIC_QUIZ,
                label="Music quiz",
                description="Future quiz mode with Bluetooth audio and arcade buttons.",
                enabled=False,
                disabled_reason="Scaffold only; quiz rules are not defined yet.",
            ),
            ModeDefinition(
                name=ModeName.ACTIVITY_N,
                label="Activity N",
                description="Template for future activities.",
                enabled=False,
                disabled_reason="Scaffold only; activity flow is not defined yet.",
            ),
            ModeDefinition(
                name=ModeName.UPDATE,
                label="Awaiting update",
                description="Future maintenance/update mode.",
                enabled=False,
                disabled_reason="Scaffold only; update strategy is not defined yet.",
            ),
        ]
    )
