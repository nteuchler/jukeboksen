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

