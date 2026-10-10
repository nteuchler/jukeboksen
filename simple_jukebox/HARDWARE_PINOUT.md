# Jukeboks Hardware Pinout

This file is the hardware wiring reference for the Raspberry Pi 4 Jukeboks project.

**Treat this file as the source of truth when modifying GPIO-related code.**
Do not change GPIO assignments in software unless the physical perfboard wiring is also changed.

The Raspberry Pi uses **BCM GPIO numbering** in software.

---

## Raspberry Pi

- Board: Raspberry Pi 4 Model B
- Header: standard 40-pin GPIO header
- GPIO logic voltage: **3.3 V**
- Do not apply 5 V or 12 V directly to GPIO pins.
- All external modules and controls share a common ground where appropriate.

---

# Final GPIO assignments

| Function | BCM GPIO | Physical pin | Direction | Notes |
|---|---:|---:|---|---|
| I2C SDA | GPIO2 | 3 | Bidirectional | Shared by OLED and NFC reader |
| I2C SCL | GPIO3 | 5 | Output/bidirectional | Shared by OLED and NFC reader |
| Rotary encoder A / CLK | GPIO4 | 7 | Input | Internal pull-up |
| Rotary encoder B / DT | GPIO17 | 11 | Input | Internal pull-up |
| I2S BCLK | GPIO18 | 12 | Output | PCM5102A BCK |
| Stop button | GPIO27 | 13 | Input | Button to GND, internal pull-up |
| Play / pause button | GPIO22 | 15 | Input | Button to GND, internal pull-up |
| Navigation Left | GPIO23 | 16 | Input | Button to GND, internal pull-up |
| Navigation Right | GPIO24 | 18 | Input | Button to GND, internal pull-up |
| RGB LED strip DATA | GPIO10 | 19 | Output | Existing WS2812/rpi_ws281x connection |
| Optional / unassigned general input | GPIO25 | 22 | Input | Spare input; may be used for an extra button to GND |
| Arcade button 1 | GPIO5 | 29 | Input | Button to GND, internal pull-up |
| Arcade button 2 | GPIO6 | 31 | Input | Button to GND, internal pull-up |
| Coin input | GPIO12 | 32 | Input | Intended for dry contact / switch to GND |
| I2S LRCLK / LCK | GPIO19 | 35 | Output | PCM5102A LCK/LRCK |
| Rotary encoder push switch | GPIO16 | 36 | Input | Switch to GND, internal pull-up |
| Spare | GPIO20 | 38 | Unused | Leave free |
| I2S DATA OUT | GPIO21 | 40 | Output | PCM5102A DIN |

---

# Power pins

Useful Raspberry Pi header power pins:

| Supply | Physical pins |
|---|---|
| 3.3 V | 1, 17 |
| 5 V | 2, 4 |
| GND | 6, 9, 14, 20, 25, 30, 34, 39 |

The perfboard uses a common ground bus.

Do not route large LED-strip current through small Raspberry Pi/perfboard traces.
The RGB LED strip should use an appropriate external 5 V supply, with its ground connected to Raspberry Pi ground.

---

# Important: no input resistors are currently fitted

The perfboard wiring does **not** contain the previously suggested 1 kOhm series resistors on the buttons or rotary encoder.

Mechanical controls are wired directly:

```text
GPIO ---- switch/button ---- GND
```

Software must configure these GPIOs as inputs with internal pull-ups.

Therefore:

- released/open = HIGH
- pressed/closed = LOW

Example concept:

```python
# Exact GPIO library may differ.
# Configure button/encoder input with a pull-up.
```

Do not configure these button GPIOs as driven HIGH outputs because a pressed button would directly connect the GPIO to ground.

Inputs using this scheme:

- GPIO4  - rotary encoder A
- GPIO17 - rotary encoder B
- GPIO16 - rotary encoder push
- GPIO27 - stop
- GPIO22 - play / pause
- GPIO23 - navigation left
- GPIO24 - navigation right
- GPIO25 - extra button
- GPIO5  - arcade button 1
- GPIO6  - arcade button 2
- GPIO12 - coin input

Mechanical switch/encoder debounce must be handled in software.

---

# Rotary encoder

The previous three-position toggle switch has been replaced by a rotary encoder.

Connections:

```text
Raspberry Pi               Rotary encoder

GPIO4  / pin 7   --------  A / CLK
GPIO17 / pin 11  --------  B / DT
GPIO16 / pin 36  --------  push switch
GND              --------  encoder common
GND              --------  push-switch common
```

The rotary encoder is a mechanical encoder and is used with 3.3 V GPIO pull-ups.

For the **HW-040 module**, use the labelled module pins (the diagram above
describes the bare encoder contacts):

| HW-040 label | Raspberry Pi connection |
|---|---|
| CLK | BCM4, physical pin 7 |
| DT | BCM17, physical pin 11 |
| SW | BCM16, physical pin 36 |
| + | 3.3 V, physical pin 1 or 17 |
| GND | Ground, e.g. physical pin 39 |

Use 3.3 V for the module's `+` pin: its onboard pull-up resistors connect
the signal lines to this supply. Do not connect it to 5 V for Pi GPIO use.
SW is a normally open switch to GND: released is HIGH and pressed is LOW.
Some modules omit the SW pull-up resistor, so the software enables the Pi's
internal pull-up on BCM16. CLK/DT are quadrature signals and may rest LOW;
their levels alone do not indicate a pressed push button.

If ENCODER_PRESS stays pressed, `pinctrl get 16` should show `ip pu` with
`hi` when released. A steady `lo` with `pu` already enabled requires checking
the physical circuit, not reversing the software polarity. With power off,
disconnect the SW lead at physical pin 36; after powering up and starting the
app, the now-unconnected BCM16 input should read HIGH. If it does, inspect
the lead/module for a short to GND, incorrect header placement, or a stuck
switch. If it remains LOW, investigate the Pi header/board and other attached
circuitry. On an unpowered, disconnected module, SW-to-GND should be open
when released and have continuity only while pressed.

References: [HW-040 supplier wiring and SW pull-up notes](https://probots.co.in/hw-040-rotary-encoder-module-with-knob-360-degree.html)
and [encoder module circuit guide](https://www.electrokit.com/upload/quick/15/16/0285_Userguide.pdf).

Suggested UI behaviour:

- rotate clockwise: next menu item / next mode
- rotate counter-clockwise: previous menu item / previous mode
- press: select / enter

Do not implement the encoder as two independent buttons.
Use proper quadrature decoding and debounce.

---

# PCM5102A I2S DAC

Module: **GY-PCM5102 / PCM5102A I2S DAC**

Connections:

| PCM5102A module | Raspberry Pi |
|---|---|
| BCK | GPIO18 / physical pin 12 |
| LCK / LRCK | GPIO19 / physical pin 35 |
| DIN | GPIO21 / physical pin 40 |
| GND | GND |
| VIN/VCC / + | **5 V for this GY-PCM5102A breakout, as confirmed for the user's module** |
| SCK | Hold LOW for 3-wire I2S PLL operation; connect to GND unless the breakout already straps SCK LOW |

I2S signal direction:

```text
Pi GPIO18 PCM_CLK  ---> DAC BCK
Pi GPIO19 PCM_FS   ---> DAC LRCK/LCK
Pi GPIO21 PCM_DOUT ---> DAC DIN
```

The three I2S signal lines above are **3.3 V logic from the Raspberry Pi**.
The module's 5 V `VIN/VCC/+` supply does **not** mean the I2S GPIO signals are 5 V.
Never feed 5 V back into GPIO18, GPIO19 or GPIO21.

GPIO20 is PCM_DIN on the Raspberry Pi and is **not used** by this DAC.
Leave GPIO20 free.

The DAC should be mounted near the audio side of the perfboard.

Keep:

- I2S wiring reasonably short
- analog DAC L/R wiring short
- analog DAC output wiring away from LED power wiring
- analog audio wiring away from class-D amplifier speaker outputs

The PCM5102A output is line-level audio and feeds the external amplifier.

---

# USB microphone

Speech/audio input uses a **USB headset microphone**.

The USB microphone does not use any GPIO pins.

Expected architecture:

```text
USB microphone ---> speech recording / STT / chat input

PCM5102A I2S ---> amplifier ---> speaker
```

Do not reserve GPIO20 for a microphone unless the hardware design is changed later.

---

# OLED display

Interface: I2C

Connections:

```text
OLED SDA ---> GPIO2 / physical pin 3
OLED SCL ---> GPIO3 / physical pin 5
OLED GND ---> GND
OLED VCC ---> appropriate module supply, normally 3.3 V for this design
```

The OLED shares SDA/SCL with the NFC reader.

Software must address each I2C device by its own I2C address.

---

# NFC reader

Interface: I2C

Connections:

```text
NFC SDA ---> GPIO2 / physical pin 3
NFC SCL ---> GPIO3 / physical pin 5
NFC GND ---> GND
NFC VCC ---> appropriate module supply
```

GPIO2 and GPIO3 are shared with the OLED.

Do not put 5 V onto Raspberry Pi SDA/SCL.

NFC software behaviour should trigger once when a new tag is presented:

```text
tag appears
    |
    v
trigger action once
    |
same tag remains
    |
ignore
    |
tag removed
    |
reader becomes armed again
```

The same continuously-present tag must not repeatedly trigger actions.

---

# RGB LED strip

Existing code uses:

```text
GPIO10 / physical pin 19
```

Do not move this GPIO in software unless the perfboard wiring is changed.

Current connection:

```text
GPIO10 ---> RGB strip DATA
Pi GND  ---> RGB strip / LED PSU common GND
```

The LED strip uses a separate suitable 5 V power path.

The current hardware description assumes **no added series resistor or level shifter** unless one is physically added later.

GPIO10 is also SPI0 MOSI, so avoid assigning SPI0 to another peripheral without reviewing the RGB implementation.

## Important legacy-code conflict

An older project test script (`rgbtest copy.py`) used:

```python
LED_PIN = 18
```

**GPIO18 is no longer available for RGB. It is permanently assigned to the PCM5102A I2S BCLK in the final perfboard design.**

The current/final RGB assignment is:

```python
LED_PIN = 10
```

Codex should search the repository for old RGB code using GPIO18 and either update it to GPIO10 or retire/remove that obsolete test code. Never run an RGB driver on GPIO18 while I2S audio is configured.

---

# Playback buttons

```text
GPIO27 / pin 13 ---> Stop button ---> GND
GPIO22 / pin 15 ---> Play / pause button ---> GND
```

Both are active LOW.

Software should convert these into logical events such as:

```text
STOP
PLAY_PAUSE
```

The state machine should not need to know the underlying GPIO numbers.

---

# Navigation buttons

```text
GPIO23 / pin 16 ---> Navigation Left ---> GND
GPIO24 / pin 18 ---> Navigation Right ---> GND
```

Both are active LOW.

Suggested logical events:

```text
NAV_LEFT
NAV_RIGHT
```

---

# Arcade buttons

```text
GPIO5 / pin 29 ---> Arcade button 1 ---> GND
GPIO6 / pin 31 ---> Arcade button 2 ---> GND
```

Both are active LOW.

Suggested logical events:

```text
ARCADE_1
ARCADE_2
```

These will primarily be used by music quiz mode.

---

# Optional / unassigned general input

GPIO25 / physical pin 22 is available as an additional mechanical-input channel.

If used as a button:

```text
GPIO25 / pin 22 ---> button ---> GND
```

Configure it as an input with the internal pull-up; pressed/closed is LOW.

This input was kept because the original hardware description said there would be seven general digital-input channels, while only six named functions were listed at that point. It is therefore **not currently assigned to a required control** and can remain unused.

---

# Coin input

Current assigned input:

```text
GPIO12 / physical pin 32
```

For a simple microswitch/dry-contact coin detector:

```text
GPIO12 ---> coin switch ---> GND
```

Active LOW.

Suggested event:

```text
COIN_INSERTED
```

IMPORTANT:

GPIO12 must only see Raspberry Pi-compatible 3.3 V logic.

If a future electronic coin acceptor outputs 5 V or 12 V pulses, it must **not** be connected directly to GPIO12.
Add appropriate isolation/level conversion, such as an optocoupler or suitable transistor/interface circuit.

Coin mode concept:

- maintain a time-remaining value
- a valid coin event adds time
- target increment: 30 minutes per coin
- do not merely reset the timer if remaining time already exists

Example:

```text
remaining_time += 30 minutes
```

---

# Pins intentionally left unused/reserved

Avoid using these unless the hardware design is intentionally revised.

## GPIO20 / physical pin 38

Currently spare.

It is also PCM_DIN and could later be used for I2S input, but the current microphone is USB.

## GPIO14 / physical pin 8
## GPIO15 / physical pin 10

Leave available for UART/debugging.

## Physical pins 27 and 28

ID_SD and ID_SC.

These are associated with Raspberry Pi HAT identification/EEPROM functionality.
Do not assign normal controls to them.

## GPIO13 / physical pin 33
## GPIO26 / physical pin 37

Currently available as spare GPIOs.

---

# Software architecture expectation

Hardware-specific code should be isolated from mode logic.

Recommended structure:

```text
hardware/
    gpio_inputs.py
    rotary_encoder.py
    nfc.py
    oled.py
    rgb.py
    audio_output.py
    microphone.py

services/
    input_service.py
    audio_service.py
    display_service.py

modes/
    nfc_mode.py
    chat_mode.py
    music_quiz_mode.py
    coin_mode.py
```

`input_service` should translate physical inputs into logical events.

For example:

```text
GPIO27 falling edge ---> STOP
GPIO22 falling edge ---> PLAY_PAUSE
GPIO23 falling edge ---> NAV_LEFT
GPIO24 falling edge ---> NAV_RIGHT
GPIO5 falling edge  ---> ARCADE_1
GPIO6 falling edge  ---> ARCADE_2
GPIO12 falling edge ---> COIN_INSERTED
encoder CW           ---> ENCODER_RIGHT
encoder CCW          ---> ENCODER_LEFT
encoder press        ---> ENCODER_PRESS
```

Mode/state-machine code should consume logical events rather than accessing GPIO pins directly.

---

# Current modes

Planned jukebox modes:

1. CD afspiller mode
2. Chat / Bumblebee speech mode
3. Music quiz mode
4. Coin timer mode

## NFC mode

- continuously monitor NFC reader
- trigger when a new tag appears
- ignore repeated reads while the same tag remains present
- re-arm after tag removal

## Chat mode

- text can be entered through Flask
- response can be converted to speech/audio using the Bumblebee-style playback system
- USB microphone may later provide voice input

## Music quiz mode

- uses arcade buttons
- Bluetooth or local music can provide quiz audio
- first valid buzzer press should lock out competing buzzers until the quiz state allows them again

## Coin mode

- music is allowed while time remains
- each coin adds 30 minutes
- warn as time gets low
- stop/transition when time reaches zero

---

# GPIO summary for code

Use BCM numbering:

```python
PIN_I2C_SDA = 2
PIN_I2C_SCL = 3

PIN_ENCODER_A = 4
PIN_ENCODER_B = 17
PIN_ENCODER_BUTTON = 16

PIN_STOP = 27
PIN_PLAY_PAUSE = 22

PIN_NAV_LEFT = 23
PIN_NAV_RIGHT = 24

PIN_EXTRA_BUTTON = 25

PIN_ARCADE_1 = 5
PIN_ARCADE_2 = 6

PIN_COIN = 12

PIN_RGB = 10

PIN_I2S_BCLK = 18
PIN_I2S_LRCLK = 19
PIN_I2S_DOUT = 21
```

Do not try to manually control GPIO18/19/21 as normal GPIO while the Linux I2S audio subsystem owns them.

---

# Physical 40-pin reference

```text
             Raspberry Pi 4 J8

       3V3   1  2   5V
     GPIO2   3  4   5V
     GPIO3   5  6   GND
     GPIO4   7  8   GPIO14
       GND   9 10   GPIO15
    GPIO17  11 12   GPIO18
    GPIO27  13 14   GND
    GPIO22  15 16   GPIO23
       3V3  17 18   GPIO24
    GPIO10  19 20   GND
     GPIO9  21 22   GPIO25
    GPIO11  23 24   GPIO8
       GND  25 26   GPIO7
     ID_SD  27 28   ID_SC
     GPIO5  29 30   GND
     GPIO6  31 32   GPIO12
    GPIO13  33 34   GND
    GPIO19  35 36   GPIO16
    GPIO26  37 38   GPIO20
       GND  39 40   GPIO21
```

**Physical pin numbering and BCM GPIO numbering are not the same thing.**

When viewing/soldering the underside of the perfboard, the connector appears mirrored compared with the component-side header diagram.
Always identify physical pin 1 before soldering or probing.

---

# Rules for Codex / future modifications

1. Use BCM GPIO numbering in Python.
2. Do not silently change GPIO assignments.
3. Buttons and encoder currently have **no external series resistors**.
4. Configure mechanical inputs with internal pull-ups and treat LOW as active.
5. Implement debounce in software.
6. Do not drive button GPIOs HIGH as outputs.
7. GPIO10 belongs to the RGB strip.
8. Any old RGB code using GPIO18 is obsolete and must not be used with this hardware.
9. GPIO18, GPIO19 and GPIO21 belong to I2S audio output.
10. The GY-PCM5102A module used here is powered from 5 V, while its I2S signal lines remain 3.3 V logic.
11. GPIO2 and GPIO3 belong to the shared I2C bus.
12. GPIO20 is currently spare.
13. USB microphone requires no GPIO allocation.
14. Never assume a coin acceptor output is GPIO-safe unless it is a dry contact or confirmed 3.3 V-compatible signal.
15. Keep physical GPIO access out of individual modes where possible; modes should consume logical events from an input service.
