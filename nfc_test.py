#!/usr/bin/env python3
"""Standalone PN532 I2C test; no jukebox imports or services.

Run: simple_jukebox/.venv/bin/python nfc_test.py
Requires: adafruit-circuitpython-pn532 and adafruit-extended-bus.
Set the reader to I2C mode and keep the jukebox out of NFC mode while testing.
"""

import argparse
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bus", type=int, default=1, help="I2C bus (default: 1)")
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x24,
                        help="I2C address (default: 0x24)")
    args = parser.parse_args()

    try:
        from adafruit_extended_bus import ExtendedI2C
        from adafruit_pn532.i2c import PN532_I2C
    except ImportError as error:
        print(f"Missing driver: {error}. Use a Python environment containing "
              "adafruit-circuitpython-pn532 and adafruit-extended-bus.", file=sys.stderr)
        return 1

    bus = None
    try:
        print(f"Connecting to PN532 on I2C bus {args.bus}, address {args.address:#04x}...",
              flush=True)
        bus = ExtendedI2C(args.bus)
        reader = PN532_I2C(bus, address=args.address)
        chip, major, minor, _ = reader.firmware_version
        print(f"Reader found (chip ID 0x{chip:02X}), firmware {major}.{minor}", flush=True)
        reader.SAM_configuration()
        print("Present a tag. Press Ctrl+C to stop.", flush=True)
        previous_uid = None
        while True:
            raw_uid = reader.read_passive_target(timeout=0.5)
            uid = bytes(raw_uid).hex().upper() if raw_uid is not None else None
            if uid != previous_uid:
                print(f"Tag UID: {uid}" if uid else "Tag removed.", flush=True)
            previous_uid = uid
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as error:
        print(f"NFC error: {error}\nCheck wiring, I2C mode, and that I2C is enabled.",
              file=sys.stderr)
        return 1
    finally:
        if bus is not None:
            bus.deinit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
