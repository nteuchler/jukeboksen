import random
import time

from rpi_ws281x import PixelStrip, Color

LED_COUNT = 110
LED_PIN = 10
LED_BRIGHTNESS = 50  # 0–255
FRAME_DELAY = 0.03
COOLING = 0.01
SPARK_PROBABILITY = 0.85
SIDE_FLAME_LENGTH = min(30, LED_COUNT // 2)
BASE_HEAT = 0.5

strip = PixelStrip(LED_COUNT, LED_PIN, brightness=LED_BRIGHTNESS)
strip.begin()


def heat_to_color(heat: float):
    heat = max(0.0, min(1.0, heat))
    if heat < 0.33:
        return Color(int(180 * heat * 3), 0, 0)
    if heat < 0.66:
        level = (heat - 0.33) * 3
        return Color(255, int(120 * level), 0)
    level = (heat - 0.66) * 3
    return Color(255, int(140 + 115 * level), int(40 + 215 * level))


def render_flame_frame(left_heat, right_heat):
    for offset, heat in enumerate(left_heat):
        strip.setPixelColor(offset, heat_to_color(heat))

    for offset, heat in enumerate(right_heat):
        strip.setPixelColor(LED_COUNT - 1 - offset, heat_to_color(heat))

    for pixel in range(SIDE_FLAME_LENGTH, LED_COUNT - SIDE_FLAME_LENGTH):
        strip.setPixelColor(pixel, Color(0, 0, 0))

    strip.show()


def animate_flame():
    left_heat = [0.0 for _ in range(SIDE_FLAME_LENGTH)]
    right_heat = [0.0 for _ in range(SIDE_FLAME_LENGTH)]

    while True:
        for heat_band in (left_heat, right_heat):
            for index in range(SIDE_FLAME_LENGTH):
                heat_band[index] = max(0.0, heat_band[index] - random.uniform(0.0, COOLING))

        for heat_band in (left_heat, right_heat):
            heat_band[0] = max(heat_band[0], BASE_HEAT * random.uniform(0.85, 1.0))
            if SIDE_FLAME_LENGTH > 1:
                heat_band[1] = max(heat_band[1], BASE_HEAT * random.uniform(0.45, 0.8))
            if SIDE_FLAME_LENGTH > 2:
                heat_band[2] = max(heat_band[2], BASE_HEAT * random.uniform(0.2, 0.5))

        for heat_band in (left_heat, right_heat):
            for index in range(SIDE_FLAME_LENGTH - 1, 0, -1):
                heat_band[index] = (
                    heat_band[index] * 0.35
                    + heat_band[index - 1] * 0.45
                    + heat_band[min(index + 1, SIDE_FLAME_LENGTH - 1)] * 0.2
                )

        if random.random() < SPARK_PROBABILITY:
            spark_strength = random.uniform(0.8, 1.0)
            spread = max(4, SIDE_FLAME_LENGTH // 3)
            for offset in range(spread):
                falloff = 1.0 - (offset / spread)
                flicker = random.uniform(0.85, 1.0)
                left_heat[offset] = max(left_heat[offset], spark_strength * falloff * flicker)
                right_heat[offset] = max(right_heat[offset], spark_strength * falloff * flicker)

        render_flame_frame(left_heat, right_heat)
        time.sleep(FRAME_DELAY)

try:
    animate_flame()

finally:
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()