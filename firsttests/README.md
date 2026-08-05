# Magical Jukebox

A PC-testable starting point for a Raspberry Pi jukebox. The current version focuses on:

- Flask control panel and JSON API
- Async state machine in a dedicated thread
- Working `idle`, `placeholder`, and `bluetooth_speaker` modes
- Disabled scaffolds for `music_quiz`, `activity_n`, and `update`
- Mock services for Bluetooth, audio, buttons, connectivity, battery, and lighting
- Raspberry Pi service profile for real BlueZ Bluetooth input and WS281x LED strips
- Live-ish status and in-memory logs through polling

No Raspberry Pi hardware is required for the default `mock` profile.

## Architecture

```text
Flask request thread
        |
        | thread-safe submit
        v
Async Engine thread -> StateMachine -> Active Mode
                            |              |
                            v              v
                        StatusStore     Services
                            |
                            v
                      Flask status API
```

The web layer never calls GPIO, BlueZ, audio players, or mode internals directly. It only submits commands and reads immutable status snapshots.

## Active modes

| Mode | Enabled | Current implementation |
|---|---:|---|
| `idle` | Yes | Real state-machine mode |
| `placeholder` | Yes | Real test flow with button/force-next transitions |
| `bluetooth_speaker` | Yes | Real mode logic using simulated Bluetooth in `mock` and BlueZ input in `raspberry_pi` |
| `music_quiz` | No | Scaffold only |
| `activity_n` | No | Scaffold only |
| `update` | No | Scaffold only |

## Run on a PC

```bash
cd magical-jukebox
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
magical-jukebox
```

Open <http://127.0.0.1:5000>.

Alternative:

```bash
flask --app magical_jukebox:create_app run --no-reload
```

Do not use Flask's reloader with the background engine enabled, because the reloader starts the application more than once.

## Run on Raspberry Pi 4

Install BlueZ tools and optional LED dependency:

```bash
sudo apt update
sudo apt install -y bluetooth bluez bluez-tools
pip install -e '.[pi,dev]'
```

Run with the Pi profile:

```bash
export SERVICE_PROFILE=raspberry_pi
export LED_PIXEL_COUNT=60
magical-jukebox
```

When `SERVICE_PROFILE=raspberry_pi`, Bluetooth mode uses the Raspberry Pi's real Bluetooth input via `bluetoothctl` events.

## Test

```bash
pytest
```

## Main API routes

```text
GET  /api/status
GET  /api/logs
GET  /api/modes
GET  /api/media
POST /api/commands
POST /api/mode/<mode_name>
POST /api/force-next
POST /api/simulate/button/<button_id>
POST /api/simulate/bluetooth/connect
POST /api/simulate/bluetooth/disconnect
POST /api/audio/play
POST /api/audio/stop
POST /api/lighting/fill
POST /api/lighting/pixel/<index>
POST /api/lighting/clear
```

Example command:

```bash
curl -X POST http://127.0.0.1:5000/api/commands \
  -H 'Content-Type: application/json' \
  -d '{"type":"change_mode","payload":{"mode":"placeholder"}}'
```

## Raspberry Pi profile notes

- Bluetooth adapter: `BluezBluetoothService` (real device connect/disconnect monitoring)
- Lighting adapter: `PiRgbLedStripService` (WS281x individually addressable RGB strips)
- Audio still uses the mock adapter in this version

## Media

Put `.mp3` or `.wav` files in:

```text
src/magical_jukebox/media/
```

The current mock audio service only simulates playback state. It intentionally does not play sound yet.
