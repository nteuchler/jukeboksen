from __future__ import annotations

import atexit
import subprocess
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from simple_jukebox.controllers import BluetoothSpeaker, RgbController, SystemVolume, VlcPlayer
from simple_jukebox.engine import Command, CommandEngine, CommandType
from simple_jukebox.services import JukeboxServices
from simple_jukebox.input_service import InputService
from simple_jukebox.oled import OledService
from simple_jukebox.nfc import NfcReader
from simple_jukebox.quiz import BluetoothMedia, QuizBuzzer
from simple_jukebox.state_machine import StateMachine


def create_app(
    *, player=None, bluetooth=None, volume=None, rgb=None, nfc=None,
    quiz_media=None, buzzer=None,
    media_folder: Path | None = None,
) -> Flask:
    app_folder = Path(__file__).resolve().parent
    app = Flask(__name__)
    player = player or VlcPlayer(media_folder or app_folder / "media")
    bluetooth = bluetooth or BluetoothSpeaker()
    volume = volume or SystemVolume()
    rgb = rgb or RgbController()
    services = JukeboxServices(player, bluetooth, volume, rgb,
                               nfc if nfc is not None else NfcReader(),
                               quiz_media if quiz_media is not None else BluetoothMedia(),
                               buzzer if buzzer is not None else QuizBuzzer())
    machine = StateMachine(services)
    engine = CommandEngine(machine, services)
    oled = OledService(machine.status)
    oled.start()
    def encoder_command(command):
        future = engine.enqueue(command)

        def report_error(result):
            error = result.exception()
            if error is not None:
                app.logger.error("Encoder audio command failed: %s", error)

        future.add_done_callback(report_error)

    input_service = InputService(
        on_encoder_step=lambda direction: encoder_command(
            Command(CommandType.ADJUST_VOLUME, direction * 5)
        ),
        on_encoder_press=lambda: encoder_command(Command(CommandType.TOGGLE_OUTPUT_MUTE)),
        on_arcade_press=lambda player: encoder_command(Command(CommandType.ARCADE_PRESS, player)),
    )
    input_service.start()

    app.config["machine"] = machine
    app.config["player"] = player
    app.config["volume"] = volume
    app.config["rgb"] = rgb
    app.config["services"] = services
    app.config["engine"] = engine
    app.config["input_service"] = input_service
    app.config["oled"] = oled
    atexit.register(engine.close)
    atexit.register(input_service.stop)
    atexit.register(oled.stop)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        return jsonify(full_status())

    def full_status():
        data = machine.status()
        data["volume"] = volume.get()
        data["output_muted"] = volume.is_muted()
        data["rgb"] = rgb.status()
        data["oled"] = oled.status()
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
        return run_command(Command(CommandType.TOGGLE_OUTPUT_MUTE))

    @app.post("/api/volume")
    def set_volume():
        data = request.get_json(silent=True) or {}
        return run_command(Command(CommandType.SET_VOLUME, data.get("volume")))

    @app.post("/api/rgb")
    def set_rgb():
        data = request.get_json(silent=True) or {}
        return run_command(Command(CommandType.SET_RGB, data.get("mode", "")))

    @app.get("/api/inputs")
    def inputs():
        service: InputService | None = app.config.get("input_service")
        if not service:
            return jsonify({"states": {}})
        return jsonify({"states": service.get_states(), "status": service.status()})

    @app.get("/api/inputs/log")
    def inputs_log():
        service: InputService | None = app.config.get("input_service")
        if not service:
            return jsonify({"events": []})
        # past 30 minutes
        events = service.get_events_since(60 * 30)
        return jsonify({"events": events})

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
