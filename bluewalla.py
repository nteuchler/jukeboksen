#!/usr/bin/env python3

import re
import subprocess
import threading
import time

from rgbtest import _pulse_environments, clear_strip, run_equalizer


class BluetoothSpeaker:
    def __init__(self, name="Jukeboks"):
        self.name = name
        self.process = None
        self.running = False
        self.equalizer_stop = threading.Event()
        self.equalizer_thread = None
        self.audio_stop = threading.Event()
        self.audio_thread = None
        self.loopback = None
        self.loopback_env = None

    def command(self, command):
        if self.process and self.process.stdin:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()

    def read_output(self):
        device_pattern = re.compile(
            r"Device ([0-9A-Fa-f:]{17}).*(?:Paired|Connected): yes"
        )

        for line in self.process.stdout:
            print(line, end="")

            match = device_pattern.search(line)

            if match:
                mac_address = match.group(1)
                self.command(f"trust {mac_address}")

            if not self.running:
                break

    def forget_paired_devices(self):
        """Remove stale bonds so every pairing session starts cleanly."""
        result = subprocess.run(
            ["bluetoothctl", "devices", "Paired"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        mac_addresses = re.findall(
            r"^Device ([0-9A-Fa-f:]{17})\b", result.stdout, re.MULTILINE
        )
        for mac_address in mac_addresses:
            print(f"Removing old Bluetooth pairing {mac_address}...")
            subprocess.run(
                ["bluetoothctl", "remove", mac_address],
                check=False,
                timeout=5,
            )

    @staticmethod
    def _pactl_lines(arguments, pulse_env):
        result = subprocess.run(
            ["pactl", *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
            env=pulse_env,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def route_bluetooth_audio(self):
        """Connect an A2DP phone source to the machine's speaker output."""
        last_status = None
        while not self.audio_stop.wait(0.5):
            if self.loopback is not None:
                code, output, _ = self._pactl_lines(
                    ["list", "short", "modules"], self.loopback_env
                )
                module_ids = {line.split()[0] for line in output.splitlines() if line}
                if code == 0 and self.loopback in module_ids:
                    continue
                self.loopback = None
                self.loopback_env = None

            found_audio_server = False
            for pulse_env in _pulse_environments():
                code, sources_output, error = self._pactl_lines(
                    ["list", "short", "sources"], pulse_env
                )
                if code != 0:
                    continue
                found_audio_server = True
                sources = [
                    fields[1]
                    for line in sources_output.splitlines()
                    if len(fields := line.split()) >= 2
                ]
                bluetooth_sources = [
                    source for source in sources if source.startswith("bluez_source")
                ]
                if not bluetooth_sources:
                    continue

                source = bluetooth_sources[0]
                code, module_id, error = self._pactl_lines(
                    [
                        "load-module",
                        "module-loopback",
                        f"source={source}",
                        "sink=@DEFAULT_SINK@",
                        "latency_msec=60",
                    ],
                    pulse_env,
                )
                if code == 0 and module_id.isdigit():
                    self.loopback = module_id
                    self.loopback_env = pulse_env
                    print(
                        f"Bluetooth audio routed: {source} -> @DEFAULT_SINK@ "
                        f"(module {module_id})",
                        flush=True,
                    )
                    last_status = "routed"
                    break
                status = f"Could not create Bluetooth audio loopback: {error}"
                if status != last_status:
                    print(status, flush=True)
                    last_status = status
            else:
                status = (
                    "Waiting for Bluetooth A2DP audio source..."
                    if found_audio_server
                    else "Cannot connect to the PulseAudio server."
                )
                if status != last_status:
                    print(status, flush=True)
                    last_status = status

    def stop_audio_routing(self):
        self.audio_stop.set()
        if self.audio_thread:
            self.audio_thread.join(timeout=2)
            self.audio_thread = None
        if self.loopback is not None and self.loopback_env is not None:
            self._pactl_lines(
                ["unload-module", self.loopback], self.loopback_env
            )
        self.loopback = None
        self.loopback_env = None

    def start(self):
        if self.running:
            return

        print("Starting Bluetooth speaker...")

        self.forget_paired_devices()

        # Start directly with a non-interactive pairing agent.
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

        # Give bluetoothctl time to register its agent.
        time.sleep(1)

        commands = [
            "default-agent",
            "power on",
            f"system-alias {self.name}",
            "pairable on",
            "discoverable-timeout 0",
            "discoverable on",
        ]

        for command in commands:
            self.command(command)
            time.sleep(0.5)

        print(f"\nBluetooth speaker '{self.name}' is ready.")
        self.audio_stop.clear()
        self.audio_thread = threading.Thread(
            target=self.route_bluetooth_audio,
            name="bluetooth-audio-router",
            daemon=True,
        )
        self.audio_thread.start()
        self.equalizer_stop.clear()
        self.equalizer_thread = threading.Thread(
            target=run_equalizer,
            args=(self.equalizer_stop,),
            name="bluetooth-equalizer",
            daemon=True,
        )
        self.equalizer_thread.start()
        print("Playback-reactive equalizer started.")
        print("Press Ctrl+C to stop.")

    def stop(self):
        if not self.running:
            return

        print("\nStopping Bluetooth speaker...")

        self.stop_audio_routing()
        self.equalizer_stop.set()
        if self.equalizer_thread:
            self.equalizer_thread.join(timeout=2)
            self.equalizer_thread = None
        clear_strip()

        self.command("discoverable off")
        self.command("pairable off")
        self.command("quit")

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
