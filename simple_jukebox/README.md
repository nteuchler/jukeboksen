# Simple Jukeboks — milestone 1

This is separate from `firsttests`. It has one state machine, two hardware wrappers,
one Flask file, and one web page.

For a replacement Pi, follow [Raspberry Pi setup and rebuild guide](RASPBERRY_PI_SETUP.md).

## Run

From the repository root:

```bash
python3 -m venv simple_jukebox/.venv
simple_jukebox/.venv/bin/pip install -r simple_jukebox/requirements-dev.txt
simple_jukebox/.venv/bin/python -m simple_jukebox.app
```

Open `http://<raspberry-pi-address>:5000`. Put MP3, WAV, OGG, FLAC, or M4A files in
`simple_jukebox/media/`; they are shown in the Local music list. Switching away from Local files stops VLC; switching
away from Bluetooth makes the adapter non-discoverable and non-pairable.
The page also controls the PulseAudio default-output volume and selects Off, Flame,
Party, or audio-reactive Equalizer RGB effects owned by `simple_jukebox/rgb.py`.
The Equalizer
listens to the common speaker-output monitor, so it reacts to local files and
Bluetooth playback.

The left/right navigation buttons (BCM23/BCM24) select the previous/next mode:
NFC reader → Idle → Local files → Bluetooth speaker → Music quiz, wrapping at
either end. Each debounced press moves once; holding does not repeat. Use
**Disable/Enable navigation buttons** in the website's Mode section to lock or
unlock these physical controls. Website mode selection stays available. Navigation
is enabled when the app starts; after re-enabling, release any held button before
pressing again.

Rotating the encoder (A on BCM4, B on BCM17) adjusts the output volume by
5 percentage points per full quadrature cycle, limited to 0–100%.
The input log shows `ENCODER_RIGHT` / `ENCODER_LEFT` for rotation.
The encoder button toggles mute on release. Holding it for 2 seconds disables
the button, preventing a stuck switch from muting playback. Use the **Enable/Disable
encoder button** toggle in the website's input section to control it manually.
Restarting the app also re-enables it. If the switch remains held after enabling,
it disables again after 2 seconds.
Rotation still adjusts volume, and input status reports `encoder_button_disabled`.

The I2C OLED automatically shows the current mode, playback/mute or Bluetooth
readiness, track, and machine message. It refreshes every half second without a
browser connected; long text is shortened to fit. The default display is an
NFP1315-61AY (SSD1315), 128×64 on bus 1 at address 0x3C. Set `JUKEBOX_OLED_DRIVER=sh1106`
for an SH1106 display, or set `JUKEBOX_OLED_BUS` and `JUKEBOX_OLED_ADDRESS`
to match your wiring. Enable I2C on the Pi and ensure the app user can access
`/dev/i2c-1`. Missing hardware does not prevent the app from starting: OLED
failures appear in the log and `/api/status` under `oled`, with retries every
five seconds. Drivers use [Luma.OLED](https://luma-oled.readthedocs.io/en/latest/python-usage.html).

All state-changing web requests are submitted as typed commands to the async
command engine. Its queue processes one mode, playback, volume, or RGB change at
a time on a dedicated worker thread; Flask does not mutate controllers directly.
The core receives audio, Bluetooth, volume, and RGB through the protocols in
`services.py`; Raspberry Pi controller classes are injected only by `app.py`.

Run the focused tests with:

```bash
simple_jukebox/.venv/bin/python -m pytest -q simple_jukebox/tests
```

### NFC reading state

Select **NFC reader** on the control page (or POST `{"mode":"nfc"}` to
`/api/mode`). The reader scans in the background only while this state is active.
The web page and OLED show tag UIDs; `/api/status` includes `nfc` connection/error,
current `uid`, `last_uid`, and `detections` fields. A held tag counts once;
removing and presenting it again, or presenting a different UID, counts again.
Entering the state resets the previous scan results. This reads ISO14443A tag
UIDs, not NDEF contents, and does not yet map tags to music.

The driver currently assumes a **PN532 configured for I2C**, using bus 1 and
7-bit address `0x24`. SDA/SCL share GPIO2/GPIO3 with the OLED as described in
`HARDWARE_PINOUT.md`. Install the updated requirements and enable I2C on the Pi.
Override `JUKEBOX_NFC_BUS` or `JUKEBOX_NFC_ADDRESS` if needed. Missing readers or
driver packages appear as NFC errors; the worker retries every five seconds.
Driver API: https://docs.circuitpython.org/projects/pn532/en/latest/api.html

On this Pi, keep `rpi-lgpio` as the GPIO backend. If installing the NFC
requirements also installs `RPi.GPIO` through Blinka, remove that conflicting
package and restore the backend:

```bash
simple_jukebox/.venv/bin/pip uninstall -y RPi.GPIO
simple_jukebox/.venv/bin/pip install --force-reinstall --no-deps rpi-lgpio
```

### Music quiz

Select **Music quiz**, connect the phone to **Jukeboks**, and play music.
The first debounced arcade press wins: **ARCADE_1 is Player 2 and turns the strip green**;
**ARCADE_2 is Player 1 and turns it red**. The jukebox requests Bluetooth AVRCP pause and plays
a short synthesized buzzer through the current output. Further presses are
ignored until the phone reports paused/stopped and then playing again. Resume
from the phone to restore the equalizer and start the next round.

Remote pause and automatic re-arming require the phone/player to expose BlueZ
`MediaPlayer1` controls and playback status. Failures appear on the website;
manual pause then resume works when status is available. Leaving quiz mode
stops the buzzer and Bluetooth speaker and restores the previous RGB effect.
The buzzer respects the shared output volume and mute setting.
