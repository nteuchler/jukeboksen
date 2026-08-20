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
Party, or audio-reactive Equalizer RGB effects from `rgbtest.py`. The Equalizer
listens to the common speaker-output monitor, so it reacts to local files and
Bluetooth playback.

Run the focused tests with:

```bash
simple_jukebox/.venv/bin/python -m pytest -q simple_jukebox/tests
```
