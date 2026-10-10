"""Bounded, asynchronous local diagnostics, independent of browser requests."""
from __future__ import annotations

import atexit
import json
import logging
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

LOGGER = logging.getLogger(__name__)
_listener = None


def configure_logging(folder=None):
    global _listener
    if _listener is not None:
        return
    folder = Path(folder or os.environ.get("JUKEBOX_LOG_DIR") or
                  Path(__file__).resolve().parent / "logs")
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "jukebox.log", maxBytes=2_000_000,
                                 backupCount=5, encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03dZ %(levelname)s pid=%(process)d %(threadName)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    # Never block the GPIO sampling loop on filesystem I/O.
    messages = queue.Queue(maxsize=10000)
    root = logging.getLogger()
    root.addHandler(QueueHandler(messages))
    root.setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    _listener = QueueListener(messages, handler)
    _listener.start()
    atexit.register(_listener.stop)
    LOGGER.info("Application starting; log=%s", folder / "jukebox.log")


class Diagnostics:
    def __init__(self, snapshot, interval=30):
        self.snapshot = snapshot
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="jukebox-diagnostics", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=3)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                LOGGER.info("Health %s", json.dumps(self.snapshot(), sort_keys=True))
                result = subprocess.run(
                    ["pinctrl", "get", "2,3,4,5,6,10,12,16,17,22,23,24,25,27"],
                    capture_output=True, text=True, timeout=2, check=False)
                LOGGER.info("GPIO registers: %s", (result.stdout or result.stderr).strip().replace("\n", "; "))
            except Exception:
                LOGGER.exception("Diagnostic snapshot failed")
            self.stop_event.wait(self.interval)
