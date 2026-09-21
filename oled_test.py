#!/usr/bin/env python3
"""Standalone 128x64 OLED test; no jukebox imports or services.

Run: simple_jukebox/.venv/bin/python oled_test.py
Requires: luma.oled. Stop any other program using the OLED before testing.
Shows text and a moving bar until Ctrl+C, then clears the display.
"""

import argparse
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bus", type=int, default=1, help="I2C bus (default: 1)")
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x3C,
                        help="I2C address (default: 0x3c)")
    parser.add_argument("--driver", choices=("ssd1315", "ssd1306", "sh1106"),
                        default="ssd1315", help="Display driver (default: ssd1315)")
    args = parser.parse_args()

    try:
        from luma.core.interface.serial import i2c
        from luma.core.render import canvas
        from luma.oled.device import ssd1306, ssd1315, sh1106
    except ImportError as error:
        print(f"Missing driver: {error}. Use a Python environment containing luma.oled.",
              file=sys.stderr)
        return 1

    device = None
    try:
        serial = i2c(port=args.bus, address=args.address)
        drivers = {"ssd1315": ssd1315, "ssd1306": ssd1306, "sh1106": sh1106}
        device = drivers[args.driver](serial, width=128, height=64)
        print(f"Testing {args.driver} on I2C bus {args.bus}, address {args.address:#04x}.")
        print("Look for text, a border, and a moving bar. Press Ctrl+C to stop.")
        started = time.monotonic()
        while True:
            elapsed = time.monotonic() - started
            x = 4 + int(elapsed * 35) % 100
            with canvas(device) as draw:
                draw.rectangle((0, 0, 127, 63), outline="white")
                draw.text((8, 6), "OLED TEST", fill="white")
                draw.text((8, 22), f"{args.driver} 128x64", fill="white")
                draw.text((8, 36), f"Running: {int(elapsed)}s", fill="white")
                draw.rectangle((x, 53, x + 20, 58), fill="white")
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as error:
        print(f"OLED error: {error}\nCheck wiring, I2C settings, and display driver.",
              file=sys.stderr)
        return 1
    finally:
        if device is not None:
            device.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
