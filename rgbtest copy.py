import time
from rpi_ws281x import PixelStrip, Color

LED_COUNT = 100
LED_PIN = 18
LED_BRIGHTNESS = 50  # 0–255

strip = PixelStrip(LED_COUNT, LED_PIN, brightness=LED_BRIGHTNESS)
strip.begin()

try:
    # Green strip
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(0, 220, 0))

    # LED number 10 blue
    strip.setPixelColor(10, Color(0, 20, 255))
    strip.show()

    time.sleep(4)

    # Moving red pixel
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(255, 0, 0))
        strip.show()
        time.sleep(0.05)

    time.sleep(4)

finally:
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()