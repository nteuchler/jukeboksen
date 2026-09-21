"""Optional PN532 I2C reader, polled only while NFC mode is active."""
from __future__ import annotations

import os
import threading


class NfcReader:
    def __init__(self, device_factory=None, interval=0.1):
        self._factory = device_factory or self._open_device
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._data = dict(active=False, connected=False, uid=None, last_uid=None,
                          detections=0, error=None)

    @staticmethod
    def _open_device():
        from adafruit_extended_bus import ExtendedI2C
        from adafruit_pn532.i2c import PN532_I2C

        bus = ExtendedI2C(int(os.environ.get("JUKEBOX_NFC_BUS", "1")))
        try:
            reader = PN532_I2C(bus, address=int(os.environ.get("JUKEBOX_NFC_ADDRESS", "0x24"), 0))
            reader.SAM_configuration()
        except Exception:
            bus.deinit()
            raise
        return reader, bus.deinit

    def status(self):
        with self._lock:
            return dict(self._data)

    def _update(self, **values):
        with self._lock:
            self._data.update(values)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            if self._stop.is_set():
                raise RuntimeError("NFC reader is still stopping; try again")
            return
        self._stop.clear()
        self._update(active=True, connected=False, uid=None, last_uid=None,
                     detections=0, error=None)
        self._thread = threading.Thread(target=self._run, name="jukebox-nfc", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._update(active=False, connected=False, uid=None)

    def _record(self, raw_uid):
        uid = bytes(raw_uid).hex().upper() if raw_uid is not None else None
        with self._lock:
            if self._stop.is_set():
                return
            if uid is not None and uid != self._data["uid"]:
                self._data["last_uid"] = uid
                self._data["detections"] += 1
            self._data.update(uid=uid, connected=True, error=None)

    def _run(self):
        while not self._stop.is_set():
            cleanup = None
            try:
                reader, cleanup = self._factory()
                while not self._stop.is_set():
                    self._record(reader.read_passive_target(timeout=0.5))
                    self._stop.wait(self._interval)
            except Exception as error:
                self._update(connected=False, error=str(error))
            finally:
                if cleanup is not None:
                    try:
                        cleanup()
                    except Exception as error:
                        self._update(error=str(error))
            if not self._stop.is_set():
                self._stop.wait(5)
        self._update(active=False, connected=False, uid=None)
