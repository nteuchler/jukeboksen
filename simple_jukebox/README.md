# Simple Jukeboks — milestone 1

This is separate from `firsttests`. It has one state machine, two hardware wrappers,
one Flask file, and one web page.

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

All state-changing web requests are submitted as typed commands to the async
command engine. Its queue processes one mode, playback, volume, or RGB change at
a time on a dedicated worker thread; Flask does not mutate controllers directly.
The core receives audio, Bluetooth, volume, and RGB through the protocols in
`services.py`; Raspberry Pi controller classes are injected only by `app.py`.

Run the focused tests with:

```bash
simple_jukebox/.venv/bin/python -m pytest -q simple_jukebox/tests
```
