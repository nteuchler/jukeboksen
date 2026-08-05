from magical_jukebox.core.enums import ModeName
from magical_jukebox.core.mode_registry import build_mode_registry


def test_only_first_version_modes_are_enabled():
    registry = build_mode_registry()
    public = {item["name"]: item for item in registry.public_list()}

    assert public[ModeName.IDLE.value]["enabled"] is True
    assert public[ModeName.PLACEHOLDER.value]["enabled"] is True
    assert public[ModeName.BLUETOOTH_SPEAKER.value]["enabled"] is True
    assert public[ModeName.MUSIC_QUIZ.value]["enabled"] is False
    assert public[ModeName.ACTIVITY_N.value]["enabled"] is False
    assert public[ModeName.UPDATE.value]["enabled"] is False
