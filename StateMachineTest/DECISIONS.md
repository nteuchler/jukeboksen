# Jukebox architecture decisions

This file records why the project is built this way. It should be updated after
every completed slice.

## Slice 1: state-machine core

### Scope

This slice contains only the state-machine core and an interactive terminal.
It deliberately does not use Flask, GPIO, Bluetooth, audio, or RGB libraries.

### Decisions

1. **One owner of state**  
   `StateMachine` is the only object allowed to change the current mode and
   step. Flask and hardware inputs will send it commands instead of changing
   shared variables.

2. **Commands pass through an async queue**  
   A queue lets web requests, buttons, and timers use the same input path. The
   machine handles one command at a time, preventing two inputs from changing
   state simultaneously.

3. **Use Python's standard library first**  
   The core uses `asyncio`, `dataclasses`, `enum`, and `unittest`. It can run on
   a PC without installing packages.

4. **Modes are explicit values**  
   The first modes are `idle`, `bluetooth`, and `activity`. `activity` is a
   placeholder. Invalid mode names are rejected instead of silently accepted.

5. **A step counter is initially generic**  
   The `next` command increments `step`. This gives the future web interface a
   simple way to fake a button press or force progress. When the first real
   activity is designed, this will become named activity states.

6. **Hardware scripts stay separate for now**  
   The supplied RGB scripts initialize hardware at import time and run long
   loops. The Bluetooth scripts also start subprocesses and threads. They will
   later be wrapped behind small service interfaces so tests can substitute
   fake services.

### Current command flow

`terminal -> command queue -> StateMachine -> status`

The next planned slice is a minimal Flask server that reads `status()` and
sends commands through `send()`. It should be tested from a browser and with
`curl` before any Raspberry Pi service is connected.

## Slice 2: Flask-to-state-machine command bridge

### Completed

The working `simple_jukebox` Flask application now submits every mutating web
request as a typed command to `CommandEngine`. A dedicated event-loop thread
drains the async command queue and handles commands sequentially. Mode changes,
local playback, stop, mute, system volume, RGB selection, and shutdown all use
this path. Read-only status and media-list requests remain direct queries.

The managed Pi environment blocks the event loop's usual cross-thread wakeup
socket, so Flask writes to a thread-safe ingress queue. The engine drains that
into its `asyncio.Queue` on a short async tick. Hardware actions still execute
on only one engine thread, and tests verify they do not execute on Flask's
calling thread.

Current command flow:

`Flask request -> typed command -> ingress -> asyncio queue -> CommandEngine -> StateMachine/services`

The next planned slice is to formalize Bluetooth, audio, volume, and RGB behind
service interfaces so the state machine depends on contracts rather than
concrete Raspberry Pi controllers.

## Slice 3: service interfaces

### Completed

`simple_jukebox.services` now defines hardware-independent protocols for audio,
Bluetooth, system volume, and RGB lighting. `JukeboxServices` groups those
contracts into one immutable dependency container used by both `StateMachine`
and `CommandEngine`. Flask's application factory is the composition boundary
that constructs and injects the concrete Raspberry Pi adapters.

Tests inject lightweight fake services through the same container, so core and
web behavior remain testable without VLC, BlueZ, PulseAudio, or LED hardware.

Current dependency flow:

`app.py -> JukeboxServices(protocols) -> StateMachine/CommandEngine -> adapters`

The next planned slice is centralized status and event logging so the website
can expose command progress, service failures, and recent backend messages.
