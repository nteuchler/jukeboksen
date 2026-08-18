#!/usr/bin/env python3

import re
import subprocess
import threading
import time


DEVICE_PATTERN = re.compile(
    r"Device ([0-9A-Fa-f:]{17}).*(?:Connected|Paired): yes"
)


class BluetoothSpeaker:
    def __init__(self, name="Jukeboks"):
        self.name = name
        self.process = None
        self.running = False

    def send(self, command):
        if self.process and self.process.stdin:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()

    def read_output(self):
        """Trust phones automatically after they pair or connect."""
        if not self.process or not self.process.stdout:
            return

        for line in self.process.stdout:
            print(line, end="")

            match = DEVICE_PATTERN.search(line)

            if match:
                mac_address = match.group(1)
                self.send(f"trust {mac_address}")

            if not self.running:
                break

    def start(self):
        if self.running:
            return

        print("Starting Bluetooth speaker...")

        # Register NoInputNoOutput immediately, avoiding yes/no prompts.
        self.process = subprocess.Popen(
            ["bluetoothctl", "--agent", "NoInputNoOutput"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        self.running = True

        threading.Thread(
            target=self.read_output,
            daemon=True,
        ).start()

        commands = [
            "power on",
            f"system-alias {self.name}",
            "pairable on",
            "discoverable-timeout 0",
            "discoverable on",
        ]

        for command in commands:
            self.send(command)
            time.sleep(0.4)

        print(f"\nBluetooth speaker active as '{self.name}'.")
        print("Connect from your phone. Press Ctrl+C to stop.\n")

    def stop(self):
        if not self.running:
            return

        print("\nStopping Bluetooth speaker...")

        self.send("discoverable off")
        self.send("pairable off")
        self.send("quit")

        self.running = False

        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.terminate()

        self.process = None


if __name__ == "__main__":
    speaker = BluetoothSpeaker("Jukeboks")

    try:
        speaker.start()

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        pass

    finally:
        speaker.stop()