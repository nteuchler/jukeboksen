# Rebuilding the Jukeboks Raspberry Pi

Recorded from the actual Pi on **2026-09-29**. This guide covers the current
`simple_jukebox` app, not the older `firsttests`, `StateMachineTest`, or
`Text2Speech` experiments. Commands below are for the **replacement Pi**;
writing this guide did not change the current Pi's system configuration.

For the shortest route, follow sections 1–7, then use the acceptance checklist.
The optional boot service is a proposed convenience, not an existing deployment.

## 1. Base system

| Item | Observed on the current Pi |
| --- | --- |
| Hardware | Raspberry Pi 4 Model B Rev 1.1 |
| OS | Raspberry Pi OS image, Debian 13 Trixie, 64-bit (`aarch64`) |
| Image reference | 2026-06-18, pi-gen stage4 (desktop image) |
| Kernel | `6.18.39+rpt-rpi-v8` |
| Python | 3.13.5 |
| User / hostname | `jukeboks` / `jukeboks` |
| Checkout | `/home/jukeboks/jukeboksen` |
| Git branch | `integration/simple-web-state-machine-v1` |
| Audio server | Real PulseAudio 17.0, not PipeWire's PulseAudio compatibility server |
| App startup | Started manually; no dedicated jukebox service installed |

Use a Raspberry Pi OS **64-bit Trixie** image for the closest reproduction.
A different Pi model, particularly Pi 5, needs separate GPIO/LED verification;
this guide records a Pi 4 setup. Package versions below are inventory, not an
instruction to downgrade a fresh image.

In Raspberry Pi Imager, configure user `jukeboks`, a password or SSH key,
SSH access, Wi-Fi if needed, timezone `Europe/Copenhagen`, and the correct Wi-Fi
country. Use a different hostname if both Pis will run on the same network.
The new Pi's IP address and Bluetooth MAC will differ.

## 2. System packages and permissions

Run in a terminal logged in as the normal `jukeboks` user:

```bash
sudo apt update
sudo apt install git curl build-essential pkg-config swig \
  python3 python3-venv python3-dev liblgpio-dev python3-rpi-lgpio \
  bluez bluez-tools pulseaudio pulseaudio-utils pulseaudio-module-bluetooth \
  vlc espeak-ng alsa-utils i2c-tools gpiod raspi-config raspi-utils
sudo usermod -aG audio,video,render,spi,i2c,gpio,input jukeboks
sudo systemctl enable --now bluetooth.service
sudo loginctl enable-linger jukeboks
```

Log out and back in after changing groups, or reboot after section 3.
Raspberry Pi OS supplies the Raspberry Pi kernel, firmware, device rules, and
hardware groups; a generic Debian image needs additional setup.
If APT reports a conflict between `pulseaudio` and `pipewire-pulse`, remove the
`pipewire-pulse` package before installing PulseAudio. Review the proposed
package changes; the goal is to use one audio server.

| Package/tool | Installed version observed | Purpose |
| --- | --- | --- |
| `bluez` | 5.82-1.1+rpt2 | Bluetooth daemon, `bluetoothctl`, `mpris-proxy` |
| `pulseaudio`, `pulseaudio-utils`, `pulseaudio-module-bluetooth` | 17.0+dfsg1-2+rpt1 | Speaker routing, phone audio, `pactl`, `parec`, `paplay` |
| `vlc` | 1:3.0.23-0+deb13u1+rpt2 | `cvlc` local music playback |
| `espeak-ng` | 1.52.0+dfsg-5 | Offline Coin survival spoken warnings |
| `alsa-utils` | 1.2.14-1+rpt1 | Audio device diagnostics |
| `python3`, `python3-dev`, `python3-venv` | 3.13.5-1 | App environment and extension builds |
| `python3-rpi-lgpio` | 0.6-0~rpt1+trixie | System GPIO compatibility library |
| `liblgpio-dev` | 0.2.2-1~rpt1+trixie | GPIO build support |
| `swig` | 4.3.0-1 | Python extension builds |
| `i2c-tools` | 4.4-2 | OLED/NFC bus diagnostics |
| `gpiod` | 2.2.1-2+deb13u1 | GPIO diagnostics |
| `git` | 1:2.47.3-0+deb13u1 | Source checkout |

The current machine also has developer/experimental packages such as `gh`,
Node.js, `mpv`, PulseAudio debug/equalizer/JACK modules, and desktop
tools. These are not dependencies of the current jukebox app. System
`python3-smbus2` and `python3-spidev` are installed too, but the isolated app
environment installs its own Python dependencies.

## 3. Boot configuration and wiring

Edit `/boot/firmware/config.txt`. Keep the new image's existing board-specific
settings and ensure these settings exist under `[all]` (do not repeatedly append
duplicate overlays):

```ini
[all]
dtparam=i2c_arm=on
dtparam=spi=on
dtparam=audio=on
dtoverlay=hifiberry-dac
```

`hifiberry-dac` provides the PCM5102A I2S output. The current image also has
`dtoverlay=vc4-kms-v3d`, `arm_64bit=1`, `arm_boost=1`, and `enable_uart=1`.
UART is not required by this app. The existing Pi has a serial console in
`cmdline.txt`; do not copy that file or its SD-card-specific `root=PARTUUID`.

Load the I2C userspace interface on boot:

```bash
echo i2c-dev | sudo tee /etc/modules-load.d/jukebox-i2c.conf
sudo reboot
```

The old Pi loads `i2c-dev` through `/etc/modules`; the file above is the modern
equivalent. No custom `/etc/asound.conf` is present on the current Pi.

Follow [HARDWARE_PINOUT.md](HARDWARE_PINOUT.md) for power connections and physical
header pin numbers. All GPIO numbers below are **BCM**:

| Device | Pins/settings |
| --- | --- |
| PCM5102A DAC | BCK 18, LRCK 19, DIN 21; GPIO20 unused |
| WS2812 RGB strip | Data 10 (SPI MOSI), 110 LEDs, brightness 50 in `rgb.py` |
| OLED | I2C bus 1, address `0x3c`, SSD1315, 128×64 |
| PN532 NFC | Must be set to I2C mode, bus 1, address `0x24` |
| Shared OLED/NFC I2C | SDA 2, SCL 3 |
| Encoder | A 4, B 17, push 16 |
| Stop / play-pause | 27 / 22 |
| Navigation left / right | 23 / 24 |
| Arcade buttons 1 / 2 | 5 / 6 |
| Coin / extra input | 12 / 25 |

Buttons use internal pull-ups and connect to ground when pressed. Do not run old
LED examples using GPIO18: that pin belongs to the DAC. Do not put another SPI
peripheral on the strip's SPI bus without reviewing the LED driver.

## 4. Get the code and create the Python environment

```bash
cd ~
git clone --branch integration/simple-web-state-machine-v1 https://github.com/nteuchler/jukeboksen.git
cd ~/jukeboksen
python3 -m venv simple_jukebox/.venv
simple_jukebox/.venv/bin/python -m pip install --upgrade pip
simple_jukebox/.venv/bin/python -m pip install -r simple_jukebox/requirements-dev.txt
```

Use `requirements.txt` instead if you do not want pytest. Git authentication may
be required for the repository. Use the latest saved/pushed branch or copy any
local commits from the old Pi before rebuilding.

### Important: GPIO package conflict

Both `RPi.GPIO` and `rpi-lgpio` install the `RPi.GPIO` import namespace. The
repository specifies **rpi-lgpio**. Blinka can also bring in legacy `RPi.GPIO`.
After installing dependencies, keep only the intended implementation:

```bash
simple_jukebox/.venv/bin/python -m pip uninstall -y RPi.GPIO
simple_jukebox/.venv/bin/python -m pip install --force-reinstall --no-deps rpi-lgpio==0.6
simple_jukebox/.venv/bin/python -c 'import RPi.GPIO as G; import lgpio; print(G.__file__)'
```

Inventory caveat: the inspected Pi currently reports *both* distributions;
its imported `RPi/GPIO/__init__.py` contains `from RPi._GPIO import *` (the legacy
implementation). Its `pip freeze` also points `rpi-lgpio` at a temporary wheel
under `/tmp/jukebox-gpio-repair/`. Neither should be copied as a reproducible
configuration. The clean install above follows the repository's intended backend;
verify physical inputs after rebuilding. `pip check` may report Blinka's legacy
`RPi.GPIO` dependency after this deliberate replacement; do not reinstall both
implementations just to silence that metadata warning.

Key Python versions observed (the requirements files define supported ranges):

| Distribution | Observed version |
| --- | --- |
| Flask | 3.1.3 |
| rpi_ws281x | 5.0.0 |
| rpi-lgpio / lgpio | 0.6 / 0.2.2.0 |
| luma.oled / luma.core | 3.15.0 / 2.6.0 |
| Pillow | 12.3.0 |
| adafruit-circuitpython-pn532 | 2.4.9 |
| adafruit-extended-bus | 1.0.2 |
| Adafruit-Blinka | 9.2.0 |
| smbus2 | 0.6.1 |
| pytest | 9.1.1 |

Do not copy `.venv` between Pis or OS versions. Recreate it. Copy your music into
`simple_jukebox/media/` separately: most media files are ignored by Git.

## 5. Audio server and DAC routing

Run user-service and `pactl` commands as **jukeboks, without sudo**. The app,
PulseAudio, and Bluetooth media proxy must share that user's session.

On the inspected Pi, PulseAudio service/socket are enabled, WirePlumber is
masked, and `pipewire-pulse` is absent (old dangling enablement links remain).
Core PipeWire service/socket are enabled, but PulseAudio owns the audio server.
Do not copy the dangling links. For this PulseAudio setup:

```bash
systemctl --user mask --now wireplumber.service
systemctl --user enable --now pulseaudio.socket pulseaudio.service
systemctl --user enable --now mpris-proxy.service
```

If `pipewire-pulse.service`/`.socket` still exist, disable and stop them first.
`loginctl enable-linger` from section 2 keeps user services available after SSH
logout. The current Pi also uses console autologin; it is not necessary for the
optional user service below.

In `/etc/pulse/default.pa`, edit the existing module lines to match these
observed settings. **Do not add duplicate module loads**:

```text
load-module module-stream-restore restore_device=false
load-module module-udev-detect tsched=0
load-module module-bluetooth-policy
load-module module-bluetooth-discover autodetect_mtu=yes
```

Keep the surrounding `.ifexists` blocks and other default modules. In
`/etc/pulse/daemon.conf`, set the existing option:

```ini
default-fragment-size-msec = 15
```

Then restart PulseAudio and identify the DAC output:

```bash
systemctl --user restart pulseaudio.service
pactl info
aplay -l
pactl list short sinks
```

On this Pi the DAC sink is `alsa_output.platform-soc_sound.stereo-fallback`.
If the replacement has a different name, substitute the name from its sink list:

```bash
pactl set-default-sink alsa_output.platform-soc_sound.stereo-fallback
pactl set-default-source alsa_output.platform-soc_sound.stereo-fallback.monitor
pactl set-sink-mute @DEFAULT_SINK@ 0
pactl set-sink-volume @DEFAULT_SINK@ 50%
```

PulseAudio's default-device restore module remembers the selection. Its state is
under `~/.config/pulse/`; do not copy old machine-ID filenames, device databases,
or authentication cookies to a new Pi. The equalizer reads the output monitor;
local VLC playback and the quiz buzzer also use this user's audio output.

## 6. Bluetooth

The current `/etc/bluetooth/main.conf` uses default values; no custom active
options were found. The app handles adapter power, name `Jukeboks`, discoverability,
pairability, and a default `NoInputNoOutput` pairing agent.

Select **Bluetooth speaker** or **Music quiz** in the website before pairing.
Leaving these modes powers Bluetooth off to prevent phone audio mixing with
local playback. Starting the app alone starts in **Idle**, not pairing mode.

```bash
systemctl status bluetooth --no-pager
bluetoothctl show
bluetoothctl devices
```

In an active Bluetooth mode, expect `Powered: yes`, `Pairable: yes`,
`Discoverable: yes`, and an `Audio Sink` UUID. Pair phones afresh on the new Pi;
do not migrate `/var/lib/bluetooth` pairing keys. Music quiz pause/resume uses
BlueZ AVRCP media-player controls exposed by the phone/player.

If a saved device fails with `br-connection-key-missing`, forget Jukeboks on that
device and remove **only that device's** stale pairing on the Pi:

```bash
bluetoothctl devices
# Substitute the phone's MAC, NOT the Pi adapter's MAC:
bluetoothctl remove AA:BB:CC:DD:EE:FF
```

Then pair again with Bluetooth mode active. This procedure resolved the Pixel 9
failure on the original Pi.

## 7. Run and verify

```bash
cd ~/jukeboksen
simple_jukebox/.venv/bin/python -m simple_jukebox.app
```

Run as the normal user, not root. Open `http://<new-pi-address>:5000` on the local
network. This is the existing Flask development server without authentication;
keep it on the local network. Run only one app instance so GPIO/audio ownership
does not conflict.

Optional hardware overrides (set before starting; defaults shown):

```bash
export JUKEBOX_OLED_DRIVER=ssd1315  # also supports ssd1306 or sh1106
export JUKEBOX_OLED_BUS=1
export JUKEBOX_OLED_ADDRESS=0x3c
export JUKEBOX_NFC_BUS=1
export JUKEBOX_NFC_ADDRESS=0x24
```

Acceptance checklist:

- `id` includes `gpio`, `spi`, `i2c`, and `audio`; device files exist under
  `/dev/gpiochip*`, `/dev/spidev0.*`, and `/dev/i2c-1`.
- `pactl info` identifies PulseAudio and the DAC as the default sink.
- Website Local files playback comes out of the DAC/amplifier/speaker.
- A newly paired phone plays audio in Bluetooth speaker mode.
- Encoder rotates volume; click toggles mute. A stuck two-second press disables
  the click, and the website can re-enable it.
- Navigation buttons cycle modes; website navigation disable/re-enable works.
- Music quiz: ARCADE_1 is Player 2/green, ARCADE_2 is Player 1/red; the first
  press wins, pauses supported phone playback, and sounds the buzzer.
- Coin survival: try a one-minute duration, verify speech at 30/10 seconds,
  alarm and dying sounds at expiry, shrinking LED bars, and coin-triggered refill.
  Restore 30 minutes after testing.
- OLED displays the current mode. NFC reader reports a UID in NFC mode.
- RGB effects work on GPIO10, including red/green colors and the audio equalizer.
- No current low-voltage warning: `vcgencmd get_throttled` ideally shows `0x0`.

Useful diagnostics from another terminal:

```bash
curl http://127.0.0.1:5000/api/status
curl http://127.0.0.1:5000/api/inputs
journalctl -u bluetooth --since '10 minutes ago' --no-pager
journalctl --user -u pulseaudio --since '10 minutes ago' --no-pager
```

With the app stopped, `i2cdetect -y 1` can check for addresses `24` and `3c`.
The old Pi has intermittently reported missing OLED/PN532 devices: their presence
must be checked physically; software installation alone does not verify wiring.

Run the tests **with the app stopped** (some tests initialize hardware adapters):

```bash
simple_jukebox/.venv/bin/python -m pytest -q simple_jukebox/tests
```

The test suite does not replace the physical acceptance checks above.

## 8. Optional: start the app at boot

This user-service template is **not installed or boot-tested on the current Pi**.
First get manual startup and audio working. Stop the manually launched app.
Create `~/.config/systemd/user/jukebox.service` (create the directory if needed):

```ini
[Unit]
Description=Jukeboks web and hardware controller
Wants=pulseaudio.service mpris-proxy.service
After=pulseaudio.service mpris-proxy.service

[Service]
Type=simple
WorkingDirectory=%h/jukeboksen
ExecStart=%h/jukeboksen/simple_jukebox/.venv/bin/python -m simple_jukebox.app
Environment=PYTHONUNBUFFERED=1
KillSignal=SIGINT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now jukebox.service
systemctl --user status jukebox.service --no-pager
journalctl --user -u jukebox.service -f
```

The linger setting from section 2 is needed for startup without login. Reboot and
verify the website and audio before relying on unattended startup. The app still
starts in Idle; use navigation or the website to select the desired mode. Stop
the service before a manual run or tests:

```bash
systemctl --user stop jukebox.service
```

## 9. Keep a recoverable copy

Save/push code commits and back up `simple_jukebox/media/` separately. Keep a copy
of this guide, your actual wiring, and any later edits to boot/PulseAudio config.
A full SD-card image is the quickest exact restore to matching hardware; this
guide is the cleaner route to a newly installed Pi.

To record the old Pi's inventory for a future comparison:

```bash
apt-mark showmanual > ~/jukebox-apt-manual.txt
dpkg-query -W > ~/jukebox-debian-package-versions.txt
cd ~/jukeboksen
simple_jukebox/.venv/bin/python -m pip freeze > ~/jukebox-python-inventory.txt
git rev-parse HEAD > ~/jukebox-code-commit.txt
```

Those are inventories, not portable install scripts. In particular, inspect
Python local-file dependencies and the GPIO conflict described above before
attempting to restore from `pip freeze`.
