from __future__ import annotations

import atexit
import logging
from typing import Any

from flask import Flask

from magical_jukebox.config import Config
from magical_jukebox.core.engine import Engine
from magical_jukebox.core.log_store import LogStore, RingBufferLogHandler
from magical_jukebox.core.mode_registry import build_mode_registry
from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.factory import build_services
from magical_jukebox.web.routes import web_bp


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    log_store = LogStore(max_entries=int(app.config["LOG_BUFFER_SIZE"]))
    _configure_logging(log_store)

    status_store = StatusStore()
    registry = build_mode_registry()
    services = build_services(
        profile=str(app.config["SERVICE_PROFILE"]),
        status_store=status_store,
        media_dir=app.config["MEDIA_DIR"],
        bluetooth_poll_interval_s=float(app.config["BLUETOOTH_POLL_INTERVAL_S"]),
        led_pixel_count=int(app.config["LED_PIXEL_COUNT"]),
        led_gpio_pin=int(app.config["LED_GPIO_PIN"]),
        led_brightness=int(app.config["LED_BRIGHTNESS"]),
        led_dma_channel=int(app.config["LED_DMA_CHANNEL"]),
        led_frequency_hz=int(app.config["LED_FREQUENCY_HZ"]),
        led_invert_signal=bool(app.config["LED_INVERT_SIGNAL"]),
        led_pwm_channel=int(app.config["LED_PWM_CHANNEL"]),
    )
    engine = Engine(
        status_store=status_store,
        registry=registry,
        services=services,
    )

    app.extensions["jukebox_log_store"] = log_store
    app.extensions["jukebox_status_store"] = status_store
    app.extensions["jukebox_registry"] = registry
    app.extensions["jukebox_services"] = services
    app.extensions["jukebox_engine"] = engine

    app.register_blueprint(web_bp)

    if app.config.get("START_ENGINE", True):
        engine.start()
        atexit.register(engine.stop)

    return app


def _configure_logging(log_store: LogStore) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    memory_handler = next(
        (handler for handler in root_logger.handlers if isinstance(handler, RingBufferLogHandler)),
        None,
    )
    if memory_handler is None:
        memory_handler = RingBufferLogHandler(log_store)
        memory_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        root_logger.addHandler(memory_handler)
    else:
        memory_handler.store = log_store

    if not any(getattr(handler, "_magical_jukebox_console", False) for handler in root_logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler._magical_jukebox_console = True  # type: ignore[attr-defined]
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        root_logger.addHandler(console_handler)
