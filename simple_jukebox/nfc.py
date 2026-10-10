"""Optional PN532 I2C reader, polled only while NFC mode is active."""
from __future__ import annotations

from collections import deque
import os
import logging
import threading

from simple_jukebox.ndef import read_text_records


class NfcReader:
    def __init__(self, device_factory=None, interval=0.1):
        self._factory = device_factory or self._open_device
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._events = deque()
        self._data = dict(texts=[], last_texts=[], text_error=None,
                          active=False, connected=False, uid=None, last_uid=None,
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
            return {**self._data, "texts": list(self._data["texts"]),
                    "last_texts": list(self._data["last_texts"])}

    def _update(self, **values):
        with self._lock:
            self._data.update(values)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            if self._stop.is_set():
                raise RuntimeError("NFC reader is still stopping; try again")
            return
        self._stop.clear()
        with self._lock:
            self._events.clear()
        self._update(active=True, connected=False, uid=None, last_uid=None,
                     detections=0, error=None, texts=[], last_texts=[], text_error=None)
        self._thread = threading.Thread(target=self._run, name="jukebox-nfc", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._update(active=False, connected=False, uid=None, texts=[])

    def drain_events(self):
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def _record(self, raw_uid, reader=None):
        uid = bytes(raw_uid).hex().upper() if raw_uid is not None else None
        with self._lock:
            fresh = uid is not None and uid != self._data["uid"]
        texts, text_error = [], None
        if fresh and reader is not None:
            try:
                texts = read_text_records(reader, self._stop.is_set)
            except Exception as error:
                text_error = str(error)
        with self._lock:
            if self._stop.is_set():
                return
            if fresh:
                self._data.update(last_uid=uid, texts=texts, last_texts=texts,
                                  text_error=text_error)
                self._data["detections"] += 1
                self._events.append({"uid": uid, "texts": texts, "error": text_error})
            elif uid is None:
                self._data["texts"] = []
            self._data.update(uid=uid, connected=True, error=None)

    def _run(self):
        while not self._stop.is_set():
            cleanup = None
            try:
                reader, cleanup = self._factory()
                logging.getLogger(__name__).info("NFC connected")
                while not self._stop.is_set():
                    self._record(reader.read_passive_target(timeout=0.5), reader)
                    self._stop.wait(self._interval)
            except Exception as error:
                logging.getLogger(__name__).warning("NFC unavailable: %s", error)
                self._update(connected=False, uid=None, texts=[], error=str(error))
            finally:
                if cleanup is not None:
                    try:
                        cleanup()
                    except Exception as error:
                        self._update(error=str(error))
            if not self._stop.is_set():
                self._stop.wait(5)
        self._update(active=False, connected=False, uid=None, texts=[])
