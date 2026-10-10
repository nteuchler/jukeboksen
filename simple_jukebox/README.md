# Simple Jukeboks — milestone 1

This is separate from `firsttests`. It has one state machine, two hardware wrappers,
one Flask file, and one web page.

For a replacement Pi, follow [Raspberry Pi setup and rebuild guide](RASPBERRY_PI_SETUP.md).

## Run

On the configured Pi, `jukebox.service` starts the app at boot without login.
The control page is at `http://jukeboks.local:5000` (or the Pi's IP address).
Manage it as the `jukeboks` user.

### Restart the service

After changing the app code, restart the service and check that it is running:

```bash
systemctl --user restart jukebox.service
systemctl --user status jukebox.service
```

To watch the service logs:

```bash
journalctl --user -u jukebox.service -f
```

The normal app entrypoint also saves diagnostics to `simple_jukebox/logs/jukebox.log`
without a browser connected. Files rotate at 2 MB with five backups (about 12 MB
maximum); they survive restarts and are ignored by Git. Set `JUKEBOX_LOG_DIR` to
override the directory. Timestamps are UTC. Logging includes initial GPIO levels,
debounced press/release transitions, hardware/web command types, command failures,
OLED/NFC errors, and a health/GPIO-register snapshot every 30 seconds. It does not
log typed text or NFC text content. Disk writes run on a separate thread; the
bounded logging queue can drop records under extreme load.

```bash
tail -f simple_jukebox/logs/jukebox.log
```

If you changed `simple_jukebox/jukebox.service`, run these commands from the
repository root to install the updated unit and restart it:

```bash
install -D -m 644 simple_jukebox/jukebox.service ~/.config/systemd/user/jukebox.service
systemctl --user daemon-reload
systemctl --user restart jukebox.service
systemctl --user status jukebox.service
```

### Install or run manually

The unit is saved in [jukebox.service](jukebox.service). To install it on a
replacement Pi after setting up dependencies and audio:

```bash
install -D -m 644 simple_jukebox/jukebox.service ~/.config/systemd/user/jukebox.service
sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now jukebox.service
```

Stop the service with `systemctl --user stop jukebox.service` before a manual
run or hardware tests; start it again afterward.

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
NFC reader → Idle → Local files → Bluetooth speaker → Music quiz → Coin survival, wrapping at
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

### Replay and typed text

**Replay last item** repeats the last local file, NFC action (real or simulated),
or typed TTS/text2Music request. The last item survives Stop and mode changes
within the app session, and resets when the service restarts. NFC replay retains
the action's original settings even if you edit the mapping afterward.

Under **Play your text**, enter a sentence and choose **Danish TTS** or
**text2Music**. Playing switches to Local files mode. Both use the shared speaker
volume/mute and can be stopped, replaced, or replayed. Leaving the mode stops
playback and any synthesis in progress.

text2Music calls the repo's `Text2Speech/bumblebee_player.py` renderer with the
existing `Text2Speech/output/index.json` and WAV clip library. It uses the best
matching song-word clips, phrase matching, volume normalization, and Danish TTS
for missing words. The library must be present on a replacement Pi (it is not in
Git). The jukebox requirements include `pydub` and Python 3.13's `audioop-lts`.
Rendering runs in a cancellable subprocess; playback uses PulseAudio like TTS.
Errors appear beside the text controls.

TTS and text2Music replace participant names with complete soundbytes from
`simple_jukebox/assets/DeltagerJingles`. Filenames supply the names (for example,
`Lea.mp3` and `Carl Christian.mp3`); matching ignores case and respects word
boundaries. `Eskilds Jingle.mp3` also matches `Eskild`. Clips play at each mention
between the surrounding speech or music. Add new audio files to this folder to
make more names available on the next playback. TTS uses `ffmpeg` to decode clips.

`POST /api/text/play` accepts `{"type":"tts","text":"Hej"}` or
`{"type":"text2music","text":"Hej"}`. `POST /api/replay` repeats the last item;
`/api/status` includes its label as `last_played`. NFC mappings can also use
`{"type":"text2music","text":"Hej med dig"}`.

### Sleeping mode

Set **Alarm time** in the Sleeping section using 24-hour `HH:MM` (for example,
`08:00`), save it, then select **Sleeping**. The next occurrence of that time
in Europe/Copenhagen is scheduled; if it has passed today, it is set for tomorrow.
The alarm runs without the website being open. Saving a new time while Sleeping
is selected reschedules it. The website shows the scheduled date and time.
`POST /api/sleeping` accepts `{"alarm_time":"08:00"}`; select it through
`POST /api/mode` with `{"mode":"sleeping"}`. Status includes `sleeping` with
the phase, alarm time, scheduled timestamp, remaining seconds, and playback errors.

At the scheduled time, `assets/AlarmApple.mp3` loops. Its playback volume rises
from 50% to 100% over two minutes, relative to the current output volume.
Either arcade button stops the alarm, waits five seconds, speaks **Godmorgen gruppe 5** in Danish,
then starts DR P8 Jazz from `https://live-icy.dr.dk/A/A22H.mp3`.
Press either arcade button again to cancel the five-second wait, greeting, or radio. Presses during
the waiting period do nothing. Leaving Sleeping or using Stop cancels the alarm
and playback. P8 Jazz needs an internet connection.

### NFC reading state

Select **NFC reader** on the control page (or POST `{"mode":"nfc"}` to
`/api/mode`). The reader scans in the background only while this state is active.
The web page and OLED show tag UIDs; `/api/status` includes `nfc` connection/error,
current `uid`, `last_uid`, and `detections` fields. A held tag counts once;
removing and presenting it again, or presenting a different UID, counts again.
Entering the state resets the previous scan results. This reads ISO14443A tag
UIDs and NDEF Text records on supported Type 2 tags, and can map text to audio.

#### NFC text → local audio or Danish speech

Edit [nfc_actions.json](nfc_actions.json). Each key is the **exact text** stored
in an NDEF Text record (case and whitespace matter):

```json
{
  "min-sang": {"type": "file", "file": "min-sang.mp3"},
  "hej": {
    "type": "tts",
    "text": "Hej og velkommen til jukeboksen!",
    "voice": "da",
    "rate": 145
  }
}
```

Put local audio in `simple_jukebox/media/`; `file` is a filename from the Local
music list, without a directory. Replace the example `song.mp3` with your file.
Write an **NDEF Text record**, such as `hej`, to a tag, then select **NFC reader**
and present it. TTS runs offline with `espeak-ng`; Danish (`da`) is the default
when `voice` is omitted. `rate` is words per minute (80–450, default 145).
The spoken sentence comes from the mapping's `text` field.

To try a mapping without a physical tag, use **Try an NFC tag** on the website.
Choose an entry to preview its audio filename or spoken text, then click **Play
selected tag**. This switches to NFC mode and plays the same configured action;
you can click again to replay. **Stop** ends playback. **Refresh list** picks up
mapping edits. Simulated plays do not increment physical tag detections.

Mappings reload on every new presentation; no service restart is needed.
Holding a tag plays once. Remove and present it again to replay. With multiple
Text records, the first mapped record wins. A new valid action stops the previous
NFC audio. Unmapped tags, malformed records, or invalid mappings display a message
and leave current playback alone. **Stop** or leaving NFC mode stops both files
and speech; volume and mute apply to both. Reading remains active during playback.

The website and OLED show the last decoded text. `/api/status` adds `nfc.texts`,
`nfc.last_texts`, `nfc.text_error`, and `nfc_action` (matched text, speech activity,
and playback errors). UID detection remains available for unsupported tags.
Text support covers unencrypted NFC Forum Type 2 NTAG213/215/216 and compatible
Ultralight tags with an NDEF capability container, UTF-8/UTF-16 Text records,
and short/long record lengths. MIFARE Classic, Type 4, chunked NDEF messages,
and reserved-memory holes inside the NDEF area are not supported.
Implementation references: [NXP NTAG memory layout](https://www.nxp.com/docs/en/data-sheet/NTAG213_215_216.pdf)
and [Adafruit PN532 API](https://docs.circuitpython.org/projects/pn532/en/latest/api.html).

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

### Coin survival

Select **Coin survival** to start a 30-minute countdown. The website's Coin
survival section accepts **1–180 whole minutes**; applying a new duration while
running restarts the countdown. The selected duration is kept across mode
changes for this app session; restarting the app restores the 30-minute default.

Each debounced coin input on **BCM12** resets the timer to the full selected
duration, stops the current warning/alarm, refills the LEDs, and plays a short
random clip matching `assets/coin_moan*.wav`. Add numbered WAV files to that
folder for variety; no restart is needed after adding clips. The original
1.73-second ghost moan is bundled for offline playback; see
[sound credits](assets/README.md). A held contact
counts once. Coins outside this mode still count in the input log but do not
start a countdown.

Offline spoken warnings play at 10, 5, and 1 minute, then 30 and 10 seconds
remaining (only thresholds below the starting duration). At zero, a synthesized
alarm, descending dying sound, and revival prompt repeat every 15 seconds until
a coin arrives or you leave the mode. Audio uses the normal speaker volume and
mute settings. Install its system dependencies on a replacement Pi:

```bash
sudo apt install espeak-ng pulseaudio-utils
```

Both LED sides shrink symmetrically from 45 LEDs per side to zero, with a fading
edge and green-to-yellow-to-red color progression. The middle LEDs stay dark.
The website and OLED also show remaining time. This mode owns the LED strip;
leaving it cancels the sounds/countdown and restores the previous RGB effect.
It does not enable Bluetooth or local music playback.

The command worker advances the monotonic timer without an open browser.
`POST /api/survival` with `{"minutes":30}` sets the duration; `/api/status`
includes `survival` with duration, remaining seconds, fraction, expiry, and audio
errors. GPIO coin events are submitted through the command queue.
