from __future__ import annotations

import atexit
import subprocess
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from simple_jukebox.controllers import BluetoothSpeaker, RgbController, SystemVolume, VlcPlayer
from simple_jukebox.engine import Command, CommandEngine, CommandType
from simple_jukebox.state_machine import StateMachine


def create_app(
    *, player=None, bluetooth=None, volume=None, rgb=None,
    media_folder: Path | None = None,
) -> Flask:
    app_folder = Path(__file__).resolve().parent
    player = player or VlcPlayer(media_folder or app_folder / "media")
    bluetooth = bluetooth or BluetoothSpeaker()
    volume = volume or SystemVolume()
    rgb = rgb or RgbController()
    machine = StateMachine(player, bluetooth)
    engine = CommandEngine(machine, volume, rgb)

    app = Flask(__name__)
    app.config["machine"] = machine
    app.config["player"] = player
    app.config["volume"] = volume
    app.config["rgb"] = rgb
    app.config["engine"] = engine
    atexit.register(engine.close)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        return jsonify(full_status())

    def full_status():
        data = machine.status()
        data["volume"] = volume.get()
        data["rgb"] = rgb.status()
        return data

    @app.get("/api/tracks")
    def tracks():
        return jsonify({"tracks": player.tracks()})

    @app.post("/api/mode")
    def mode():
        data = request.get_json(silent=True) or {}
        return run_command(Command(CommandType.CHANGE_MODE, data.get("mode", "")))

    @app.post("/api/play")
    def play():
        data = request.get_json(silent=True) or {}
        return run_command(Command(CommandType.PLAY, data.get("track", "")))

    @app.post("/api/stop")
    def stop():
        return run_command(Command(CommandType.STOP))

    @app.post("/api/mute")
    def mute():
        return run_command(Command(CommandType.TOGGLE_MUTE))

    @app.post("/api/volume")
    def set_volume():
        data = request.get_json(silent=True) or {}
        return run_command(Command(CommandType.SET_VOLUME, data.get("volume")))

    @app.post("/api/rgb")
    def set_rgb():
        data = request.get_json(silent=True) or {}
        return run_command(Command(CommandType.SET_RGB, data.get("mode", "")))

    def run_command(command):
        try:
            engine.submit(command)
            return jsonify({"ok": True, "status": full_status()})
        except (
            ValueError, RuntimeError, TimeoutError, OSError,
            subprocess.SubprocessError,
        ) as error:
            return jsonify({"ok": False, "error": str(error)}), 400

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=False)
