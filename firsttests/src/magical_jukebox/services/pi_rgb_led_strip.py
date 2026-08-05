from __future__ import annotations

import logging

from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.base import BaseEventService

logger = logging.getLogger(__name__)


class PiRgbLedStripService(BaseEventService):
    def __init__(
        self,
        status_store: StatusStore,
        *,
        pixel_count: int,
        gpio_pin: int,
        brightness: int,
        dma_channel: int,
        frequency_hz: int,
        invert_signal: bool,
        pwm_channel: int,
    ) -> None:
        super().__init__()
        self.status_store = status_store
        self.pixel_count = max(int(pixel_count), 0)
        self._strip = None
        self._color = (0, 0, 0)

        if self.pixel_count <= 0:
            self.status_store.patch_section(
                "lighting",
                available=False,
                enabled=False,
                pixel_count=0,
                last_color=[0, 0, 0],
            )
            logger.info("LED strip disabled because pixel count is 0")
            return

        try:
            from rpi_ws281x import Color, PixelStrip  # type: ignore[import-not-found]
        except ImportError:
            self.status_store.patch_section(
                "lighting",
                available=False,
                enabled=False,
                pixel_count=self.pixel_count,
                last_color=[0, 0, 0],
            )
            logger.warning(
                "rpi_ws281x is not installed; LED strip service is unavailable on this system"
            )
            return

        self._color_factory = Color
        self._strip = PixelStrip(
            self.pixel_count,
            int(gpio_pin),
            int(frequency_hz),
            int(dma_channel),
            bool(invert_signal),
            int(brightness),
            int(pwm_channel),
        )
        self._strip.begin()
        self.status_store.patch_section(
            "lighting",
            available=True,
            enabled=True,
            pixel_count=self.pixel_count,
            last_color=[0, 0, 0],
        )

    async def set_pixel(self, pixel_index: int, red: int, green: int, blue: int) -> None:
        if self._strip is None:
            return
        index = int(pixel_index)
        if index < 0 or index >= self.pixel_count:
            raise ValueError(f"pixel_index must be between 0 and {self.pixel_count - 1}")
        r, g, b = _clamp_color(red), _clamp_color(green), _clamp_color(blue)
        self._strip.setPixelColor(index, self._color_factory(r, g, b))
        self._strip.show()
        self._color = (r, g, b)
        self.status_store.patch_section("lighting", last_color=[r, g, b])

    async def fill(self, red: int, green: int, blue: int) -> None:
        if self._strip is None:
            return
        r, g, b = _clamp_color(red), _clamp_color(green), _clamp_color(blue)
        color = self._color_factory(r, g, b)
        for pixel in range(self.pixel_count):
            self._strip.setPixelColor(pixel, color)
        self._strip.show()
        self._color = (r, g, b)
        self.status_store.patch_section("lighting", last_color=[r, g, b])

    async def clear(self) -> None:
        await self.fill(0, 0, 0)


def _clamp_color(value: int) -> int:
    return max(0, min(255, int(value)))
