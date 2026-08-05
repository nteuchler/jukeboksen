from __future__ import annotations

from enum import StrEnum


class ModeName(StrEnum):
    IDLE = "idle"
    PLACEHOLDER = "placeholder"
    BLUETOOTH_SPEAKER = "bluetooth_speaker"
    MUSIC_QUIZ = "music_quiz"
    ACTIVITY_N = "activity_n"
    UPDATE = "update"


class RuntimeState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    IDLE = "idle"
    PREPARING = "preparing"
    WAITING = "waiting"
    PAIRING = "pairing"
    CONNECTED = "connected"
    PLAYING = "playing"
    COMPLETED = "completed"
    STOPPING = "stopping"
    ERROR = "error"
    DISABLED = "disabled"


class CommandType(StrEnum):
    CHANGE_MODE = "change_mode"
    FORCE_NEXT = "force_next"
    RESET_MODE = "reset_mode"
    SIMULATE_BUTTON = "simulate_button"
    SIMULATE_BLUETOOTH_CONNECT = "simulate_bluetooth_connect"
    SIMULATE_BLUETOOTH_DISCONNECT = "simulate_bluetooth_disconnect"
    LIGHTING_SET_PIXEL = "lighting_set_pixel"
    LIGHTING_FILL = "lighting_fill"
    LIGHTING_CLEAR = "lighting_clear"
    PLAY_AUDIO = "play_audio"
    STOP_AUDIO = "stop_audio"
    SHUTDOWN = "shutdown"


class EventType(StrEnum):
    BUTTON_PRESSED = "button_pressed"
    BLUETOOTH_CONNECTED = "bluetooth_connected"
    BLUETOOTH_DISCONNECTED = "bluetooth_disconnected"
    AUDIO_STARTED = "audio_started"
    AUDIO_FINISHED = "audio_finished"
    SERVICE_ERROR = "service_error"
