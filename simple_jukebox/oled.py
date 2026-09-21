"""Keep the optional I2C OLED in sync with the machine, without web requests."""

from __future__ import annotations

import logging
import os
import threading

LOGGER = logging.getLogger(__name__)


def status_lines(status):
    mode = status.get("mode", "idle")
    title = {"idle": "Idle", "local_files": "Local files", "bluetooth": "Bluetooth"}.get(mode, str(mode))
    if mode == "nfc":
        nfc = status.get("nfc") or {}
        return ["NFC reader", "Reader error" if nfc.get("error") else
                "Tag detected" if nfc.get("uid") else "Waiting for tag",
                str(nfc.get("last_uid") or ""), str(nfc.get("error") or "Present an NFC tag")]
    if mode == "bluetooth":
        playback = "BT ready" if status.get("bluetooth_active") else "BT inactive"
    else:
        playback = "Playing" if status.get("playing") else "Stopped"
    if status.get("muted"):
        playback += " (muted)"
    return [title, playback, str(status.get("track") or ""), str(status.get("message") or "")]


class OledService:
    def __init__(self, get_status, device_factory=None, interval=0.5):
        self._get_status = get_status
        self._device_factory = device_factory or self._open_device
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None
        self._device = None
        self._last_lines = None
        self.error = None

    @staticmethod
    def _open_device():
        from luma.core.interface.serial import i2c
        from luma.oled.device import ssd1306, ssd1315, sh1106

        model = os.environ.get("JUKEBOX_OLED_DRIVER", "ssd1315").lower()
        drivers = {"ssd1306": ssd1306, "ssd1315": ssd1315, "sh1106": sh1106}
        if model not in drivers:
            raise ValueError("JUKEBOX_OLED_DRIVER must be ssd1306, ssd1315 or sh1106")
        serial = i2c(port=int(os.environ.get("JUKEBOX_OLED_BUS", "1")),
                     address=int(os.environ.get("JUKEBOX_OLED_ADDRESS", "0x3c"), 0))
        return drivers[model](serial, width=128, height=64)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="jukebox-oled", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def status(self):
        return {"connected": self._device is not None and self.error is None, "error": self.error}

    def _disconnect(self):
        device, self._device = self._device, None
        self._last_lines = None
        if device is not None:
            try:
                device.cleanup()
            except Exception:
                LOGGER.debug("OLED cleanup failed", exc_info=True)

    def _refresh(self):
        from PIL import Image, ImageDraw, ImageFont

        if self._device is None:
            self._device = self._device_factory()
        lines = status_lines(self._get_status())
        if lines == self._last_lines:
            return
        frame = Image.new("1", (self._device.width, self._device.height))
        draw = ImageDraw.Draw(frame)
        font = ImageFont.load_default(size=10)
        for index, line in enumerate(lines):
            line = " ".join(line.split())
            if draw.textlength(line, font=font) > self._device.width:
                while line and draw.textlength(line + "...", font=font) > self._device.width:
                    line = line[:-1]
                line += "..."
            draw.text((0, index * 16), line, font=font, fill=255)
        self._device.display(frame)
        self._last_lines = lines

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    self._refresh()
                    self.error = None
                except Exception as error:
                    message = str(error)
                    if message != self.error:
                        LOGGER.warning("OLED unavailable: %s", message)
                    self.error = message
                    self._disconnect()
                self._stop.wait(5 if self.error else self._interval)
        finally:
            self._disconnect()
