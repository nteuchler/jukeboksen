from __future__ import annotations

import os
from pathlib import Path


class Config:
    SECRET_KEY = "development-only-change-me"
    START_ENGINE = True
    SERVICE_PROFILE = os.getenv("SERVICE_PROFILE", "mock")
    LOG_BUFFER_SIZE = 500
    MEDIA_DIR = Path(__file__).resolve().parent / "media"
    STATUS_POLL_INTERVAL_MS = 750
    BLUETOOTH_POLL_INTERVAL_S = float(os.getenv("BLUETOOTH_POLL_INTERVAL_S", "1.0"))
    LED_PIXEL_COUNT = int(os.getenv("LED_PIXEL_COUNT", "0"))
    LED_GPIO_PIN = int(os.getenv("LED_GPIO_PIN", "18"))
    LED_BRIGHTNESS = int(os.getenv("LED_BRIGHTNESS", "64"))
    LED_DMA_CHANNEL = int(os.getenv("LED_DMA_CHANNEL", "10"))
    LED_FREQUENCY_HZ = int(os.getenv("LED_FREQUENCY_HZ", "800000"))
    LED_INVERT_SIGNAL = os.getenv("LED_INVERT_SIGNAL", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    LED_PWM_CHANNEL = int(os.getenv("LED_PWM_CHANNEL", "0"))


class TestConfig(Config):
    TESTING = True
    START_ENGINE = False
