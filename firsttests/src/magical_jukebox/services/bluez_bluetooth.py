from __future__ import annotations

import asyncio
import logging
from asyncio.subprocess import PIPE

from magical_jukebox.core.enums import EventType
from magical_jukebox.core.messages import Event
from magical_jukebox.core.status_store import StatusStore
from magical_jukebox.services.base import BaseEventService

logger = logging.getLogger(__name__)


class BluezBluetoothService(BaseEventService):
    def __init__(self, status_store: StatusStore, poll_interval_s: float = 1.0) -> None:
        super().__init__()
        self.status_store = status_store
        self.poll_interval_s = max(float(poll_interval_s), 0.5)
        self._monitor_task: asyncio.Task[None] | None = None
        self._monitor_stop = asyncio.Event()
        self._last_connected_device: str | None = None

    async def forget_all_pairings(self) -> None:
        paired_output = await self._run_bluetoothctl("paired-devices")
        for line in paired_output.splitlines():
            line = line.strip()
            if not line.startswith("Device "):
                continue
            parts = line.split(maxsplit=2)
            if len(parts) < 2:
                continue
            mac = parts[1]
            await self._run_bluetoothctl("remove", mac)

        self.status_store.patch_section(
            "bluetooth",
            remembered_devices=0,
            connected=False,
            device=None,
        )
        logger.info("Cleared Bluetooth pairings using BlueZ")

    async def start_pairing(self) -> None:
        await self._run_bluetoothctl("power", "on")
        await self._run_bluetoothctl("pairable", "on")
        await self._run_bluetoothctl("discoverable", "on")
        await self._run_bluetoothctl("agent", "on")
        await self._run_bluetoothctl("default-agent")

        self.status_store.patch_section(
            "bluetooth",
            enabled=True,
            pairing=True,
            remembered_devices=self.status_store.snapshot()["bluetooth"].get("remembered_devices", 0),
        )
        await self._ensure_monitoring()
        await self._poll_connected_device_once()
        logger.info("Bluetooth pairing enabled with BlueZ")

    async def stop(self) -> None:
        await self._stop_monitoring()
        await self._run_bluetoothctl("discoverable", "off")
        await self._run_bluetoothctl("pairable", "off")
        self.status_store.patch_section(
            "bluetooth",
            enabled=False,
            pairing=False,
        )

    async def simulate_connected(self, device: str) -> None:
        self.status_store.patch_section(
            "bluetooth",
            enabled=True,
            pairing=False,
            connected=True,
            device=device,
        )
        self._last_connected_device = device
        if self._event_sink:
            await self._event_sink(
                Event(
                    type=EventType.BLUETOOTH_CONNECTED,
                    payload={"device": device},
                    source="bluez_bluetooth",
                )
            )

    async def simulate_disconnected(self) -> None:
        self.status_store.patch_section(
            "bluetooth",
            connected=False,
            device=None,
        )
        self._last_connected_device = None
        if self._event_sink:
            await self._event_sink(
                Event(
                    type=EventType.BLUETOOTH_DISCONNECTED,
                    source="bluez_bluetooth",
                )
            )

    async def _ensure_monitoring(self) -> None:
        if self._monitor_task and not self._monitor_task.done():
            return
        self._monitor_stop = asyncio.Event()
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def _stop_monitoring(self) -> None:
        if self._monitor_task is None:
            return
        self._monitor_stop.set()
        self._monitor_task.cancel()
        try:
            await self._monitor_task
        except asyncio.CancelledError:
            pass
        finally:
            self._monitor_task = None

    async def _monitor_loop(self) -> None:
        while not self._monitor_stop.is_set():
            try:
                await self._poll_connected_device_once()
            except Exception:
                logger.exception("BlueZ monitor loop failed")
            await asyncio.sleep(self.poll_interval_s)

    async def _poll_connected_device_once(self) -> None:
        connected_device = await self._read_connected_device()
        if connected_device == self._last_connected_device:
            return

        self._last_connected_device = connected_device
        if connected_device:
            self.status_store.patch_section(
                "bluetooth",
                connected=True,
                pairing=False,
                device=connected_device,
                enabled=True,
            )
            if self._event_sink:
                await self._event_sink(
                    Event(
                        type=EventType.BLUETOOTH_CONNECTED,
                        payload={"device": connected_device},
                        source="bluez_bluetooth",
                    )
                )
            return

        self.status_store.patch_section(
            "bluetooth",
            connected=False,
            device=None,
        )
        if self._event_sink:
            await self._event_sink(
                Event(
                    type=EventType.BLUETOOTH_DISCONNECTED,
                    source="bluez_bluetooth",
                )
            )

    async def _read_connected_device(self) -> str | None:
        output = await self._run_bluetoothctl("devices", "Connected")
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("Device "):
                continue
            parts = line.split(maxsplit=2)
            if len(parts) == 3 and parts[2].strip():
                return parts[2].strip()
            if len(parts) >= 2:
                return parts[1]
        return None

    async def _run_bluetoothctl(self, *args: str) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                "bluetoothctl",
                *args,
                stdout=PIPE,
                stderr=PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("bluetoothctl command not found on this system") from exc

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=8)
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise RuntimeError(f"bluetoothctl {' '.join(args)} timed out")

        if process.returncode != 0:
            stderr_text = (stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"bluetoothctl {' '.join(args)} failed with code {process.returncode}: {stderr_text}"
            )

        return (stdout or b"").decode("utf-8", errors="replace")
