from __future__ import annotations

from http import HTTPStatus
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request

from magical_jukebox.core.engine import Engine
from magical_jukebox.core.enums import CommandType
from magical_jukebox.core.log_store import LogStore
from magical_jukebox.core.messages import Command
from magical_jukebox.core.mode_registry import ModeRegistry
from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.interfaces import ServiceBundle

web_bp = Blueprint("web", __name__)


def _engine() -> Engine:
    return current_app.extensions["jukebox_engine"]


def _status_store() -> StatusStore:
    return current_app.extensions["jukebox_status_store"]


def _log_store() -> LogStore:
    return current_app.extensions["jukebox_log_store"]


def _registry() -> ModeRegistry:
    return current_app.extensions["jukebox_registry"]


def _services() -> ServiceBundle:
    return current_app.extensions["jukebox_services"]


def _submit(command_type: CommandType, payload: dict[str, Any] | None = None):
    command = Command(type=command_type, payload=payload or {}, source="web")
    try:
        _engine().submit(command)
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), HTTPStatus.SERVICE_UNAVAILABLE
    return jsonify({"ok": True, "command_id": command.id}), HTTPStatus.ACCEPTED


@web_bp.get("/")
def index():
    return render_template(
        "index.html",
        poll_interval_ms=int(current_app.config["STATUS_POLL_INTERVAL_MS"]),
    )


@web_bp.get("/api/status")
def api_status():
    status = _status_store().snapshot()
    status["engine_running"] = _engine().running
    return jsonify(status)


@web_bp.get("/api/logs")
def api_logs():
    after = request.args.get("after", default=0, type=int)
    limit = min(request.args.get("limit", default=200, type=int), 500)
    return jsonify({"entries": _log_store().read(after=after, limit=limit)})


@web_bp.get("/api/modes")
def api_modes():
    return jsonify({"modes": _registry().public_list()})


@web_bp.get("/api/media")
def api_media():
    return jsonify({"media": _services().audio.list_media()})


@web_bp.post("/api/commands")
def api_commands():
    data = request.get_json(silent=True) or {}
    raw_type = data.get("type")
    payload = data.get("payload") or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "payload must be an object"}), HTTPStatus.BAD_REQUEST
    try:
        command_type = CommandType(str(raw_type))
    except ValueError:
        return jsonify({"ok": False, "error": f"Unknown command type: {raw_type!r}"}), HTTPStatus.BAD_REQUEST
    return _submit(command_type, payload)


@web_bp.post("/api/mode/<mode_name>")
def api_change_mode(mode_name: str):
    return _submit(CommandType.CHANGE_MODE, {"mode": mode_name})


@web_bp.post("/api/force-next")
def api_force_next():
    return _submit(CommandType.FORCE_NEXT)


@web_bp.post("/api/reset-mode")
def api_reset_mode():
    return _submit(CommandType.RESET_MODE)


@web_bp.post("/api/simulate/button/<int:button_id>")
def api_simulate_button(button_id: int):
    return _submit(CommandType.SIMULATE_BUTTON, {"button_id": button_id})


@web_bp.post("/api/simulate/bluetooth/connect")
def api_simulate_bluetooth_connect():
    data = request.get_json(silent=True) or {}
    return _submit(
        CommandType.SIMULATE_BLUETOOTH_CONNECT,
        {"device": data.get("device") or "Test phone"},
    )


@web_bp.post("/api/simulate/bluetooth/disconnect")
def api_simulate_bluetooth_disconnect():
    return _submit(CommandType.SIMULATE_BLUETOOTH_DISCONNECT)


@web_bp.post("/api/audio/play")
def api_audio_play():
    data = request.get_json(silent=True) or {}
    track = data.get("track")
    if not isinstance(track, str) or not track:
        return jsonify({"ok": False, "error": "track is required"}), HTTPStatus.BAD_REQUEST
    return _submit(CommandType.PLAY_AUDIO, {"track": track})


@web_bp.post("/api/audio/stop")
def api_audio_stop():
    return _submit(CommandType.STOP_AUDIO)


@web_bp.post("/api/lighting/fill")
def api_lighting_fill():
    data = request.get_json(silent=True) or {}
    return _submit(
        CommandType.LIGHTING_FILL,
        {
            "red": data.get("red"),
            "green": data.get("green"),
            "blue": data.get("blue"),
        },
    )


@web_bp.post("/api/lighting/pixel/<int:pixel_index>")
def api_lighting_set_pixel(pixel_index: int):
    data = request.get_json(silent=True) or {}
    return _submit(
        CommandType.LIGHTING_SET_PIXEL,
        {
            "pixel_index": pixel_index,
            "red": data.get("red"),
            "green": data.get("green"),
            "blue": data.get("blue"),
        },
    )


@web_bp.post("/api/lighting/clear")
def api_lighting_clear():
    return _submit(CommandType.LIGHTING_CLEAR)
