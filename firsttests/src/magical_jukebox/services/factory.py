from __future__ import annotations

from pathlib import Path

from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.bluez_bluetooth import BluezBluetoothService
from magical_jukebox.services.interfaces import ServiceBundle
from magical_jukebox.services.mock_audio import MockAudioService
from magical_jukebox.services.mock_bluetooth import MockBluetoothService
from magical_jukebox.services.mock_connectivity import MockConnectivityService
from magical_jukebox.services.mock_hardware import MockHardwareService
from magical_jukebox.services.mock_lighting import MockLightingService
from magical_jukebox.services.pi_rgb_led_strip import PiRgbLedStripService


def build_services(
    *,
    profile: str,
    status_store: StatusStore,
    media_dir: Path,
    bluetooth_poll_interval_s: float = 1.0,
    led_pixel_count: int = 0,
    led_gpio_pin: int = 18,
    led_brightness: int = 64,
    led_dma_channel: int = 10,
    led_frequency_hz: int = 800000,
    led_invert_signal: bool = False,
    led_pwm_channel: int = 0,
) -> ServiceBundle:
    normalized = profile.strip().lower()

    if normalized == "mock":
        status_store.patch_section("system", service_profile=normalized)
        return ServiceBundle(
            bluetooth=MockBluetoothService(status_store),
            audio=MockAudioService(status_store, Path(media_dir)),
            hardware=MockHardwareService(),
            connectivity=MockConnectivityService(status_store, profile=normalized),
            lighting=MockLightingService(status_store),
            media_dir=Path(media_dir),
        )

    if normalized in {"raspberry_pi", "pi", "rpi"}:
        status_store.patch_section("system", service_profile="raspberry_pi")
        return ServiceBundle(
            bluetooth=BluezBluetoothService(
                status_store,
                poll_interval_s=bluetooth_poll_interval_s,
            ),
            audio=MockAudioService(status_store, Path(media_dir)),
            hardware=MockHardwareService(),
            connectivity=MockConnectivityService(status_store, profile="raspberry_pi"),
            lighting=PiRgbLedStripService(
                status_store,
                pixel_count=led_pixel_count,
                gpio_pin=led_gpio_pin,
                brightness=led_brightness,
                dma_channel=led_dma_channel,
                frequency_hz=led_frequency_hz,
                invert_signal=led_invert_signal,
                pwm_channel=led_pwm_channel,
            ),
            media_dir=Path(media_dir),
        )

    raise ValueError(
        f"Unsupported service profile {profile!r}; expected 'mock' or 'raspberry_pi'"
    )
