"""Coordinator for Roroshetta Sense."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
try:
    from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
except ImportError:  # pragma: no cover - fallback for environments without the helper
    BleakClientWithServiceCache = BleakClient  # type: ignore[misc,assignment]
    establish_connection = None

from homeassistant.components import bluetooth
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    BEEF_CHARACTERISTIC,
    DATA_PAIRED_ONCE,
    DEVICE_WAIT_SECONDS,
    DOMAIN,
    MAX_BACKOFF_SECONDS,
    PAIRING_WINDOW_SECONDS,
    STALE_AFTER_SECONDS,
    STOP_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

type RoroshettaConfigEntry = ConfigEntry[RoroshettaDataUpdateCoordinator]


@dataclass
class RoroshettaData:
    """Data from Roroshetta Sense device."""

    temperature: float | None = None
    heat_index: float | None = None
    humidity: float | None = None
    co2: int | None = None
    tvoc: int | None = None
    pm25: float | None = None
    aqi: int | None = None
    grease_filter: int | None = None
    light: float | None = None
    fan: float | None = None
    activity: int | None = None
    alarm_level: int | None = None
    power: int | None = None
    uptime: int | None = None


class RoroshettaDataUpdateCoordinator(DataUpdateCoordinator[RoroshettaData]):
    """Class to manage fetching Roroshetta data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        ble_device: BLEDevice,
        entry: RoroshettaConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        _LOGGER.debug(
            "Initializing Roroshetta coordinator for device %s", ble_device.address
        )
        super().__init__(
            hass=hass,
            logger=logger,
            name=DOMAIN,
            update_interval=None,
        )
        self.ble_device = ble_device
        self.entry = entry
        self.data = RoroshettaData()
        self._client: BleakClient | None = None
        self._paired_once = bool(entry.data.get(DATA_PAIRED_ONCE))
        self._pairing_delay_done = False
        self._stop_event = asyncio.Event()
        self._connection_task: asyncio.Task[None] | None = None
        self._connected = False
        self._last_notification: float | None = None
        _LOGGER.debug("Roroshetta coordinator initialized successfully")

    @property
    def device_available(self) -> bool:
        """Whether we are connected and the data is still fresh.

        The coordinator never polls, so ``last_update_success`` is meaningless
        here: it stays True forever and would leave stale values looking live.
        """
        if not self._connected or self._last_notification is None:
            return False
        age = self.hass.loop.time() - self._last_notification
        return age < STALE_AFTER_SECONDS

    def _set_connected(self, connected: bool) -> None:
        """Update connection state and push availability to entities."""
        if self._connected == connected:
            return
        self._connected = connected
        _LOGGER.debug("Roroshetta connection state: %s", connected)
        self.async_update_listeners()

    async def async_start_notify(self) -> None:
        """Start the continuous notification connection loop."""
        if self._connection_task and not self._connection_task.done():
            return
        self._stop_event.clear()
        self._connection_task = self.hass.async_create_task(self._run_notify_loop())

    async def async_stop(self) -> None:
        """Stop the continuous notification connection loop."""
        self._stop_event.set()
        task = self._connection_task
        self._connection_task = None
        if task is None:
            return

        # Give the loop a moment to disconnect cleanly, then force it down so an
        # unload can never block on an in-flight backoff.
        try:
            async with asyncio.timeout(STOP_TIMEOUT_SECONDS):
                await task
        except TimeoutError:
            _LOGGER.debug("Notify loop did not stop in time, cancelling it")
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _sleep_or_stop(self, seconds: float) -> bool:
        """Sleep, waking early if a stop was requested. True if we should stop."""
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(seconds):
                await self._stop_event.wait()
        return self._stop_event.is_set()

    async def _run_notify_loop(self) -> None:
        """Maintain a connection and stream notifications."""
        address = self.entry.unique_id
        assert address is not None
        attempt = 0

        while not self._stop_event.is_set():
            available_device = bluetooth.async_ble_device_from_address(
                self.hass, address
            )
            if not available_device:
                _LOGGER.debug(
                    "Roroshetta device at %s is not available in the Bluetooth cache",
                    address,
                )
                if await self._sleep_or_stop(DEVICE_WAIT_SECONDS):
                    break
                continue

            if not self._paired_once and not self._pairing_delay_done:
                _LOGGER.debug(
                    "Waiting %d seconds for pairing window before first connection",
                    PAIRING_WINDOW_SECONDS,
                )
                if await self._sleep_or_stop(PAIRING_WINDOW_SECONDS):
                    break
                self._pairing_delay_done = True

            client: BleakClient | None = None
            disconnect_event = asyncio.Event()
            notified = False

            try:
                _LOGGER.debug(
                    "Connecting to Roroshetta device at %s (attempt %d)",
                    address,
                    attempt + 1,
                )

                def on_disconnect(_client: BleakClient) -> None:
                    """Wake the loop so it reconnects."""
                    _LOGGER.debug(
                        "Roroshetta device at %s disconnected", address
                    )
                    self.hass.loop.call_soon_threadsafe(disconnect_event.set)

                # bleak removed set_disconnected_callback; the callback has to be
                # handed to the client at construction time or it is never fired.
                if establish_connection is not None:
                    client = await establish_connection(
                        BleakClientWithServiceCache,
                        available_device,
                        address,
                        disconnected_callback=on_disconnect,
                        timeout=10.0,
                    )
                else:
                    client = BleakClient(
                        available_device,
                        timeout=10.0,
                        disconnected_callback=on_disconnect,
                    )
                    await client.connect()

                self._client = client

                _LOGGER.debug("Connected to Roroshetta device at %s", address)

                if not self._paired_once and hasattr(client, "pair"):
                    await client.pair()

                def handle_notify(sender, data):
                    """Handle notification from device."""
                    _LOGGER.debug(
                        "Received notification from Roroshetta device: %s bytes",
                        len(data),
                    )
                    self._last_notification = self.hass.loop.time()
                    self._parse_data(data)
                    self.async_set_updated_data(self.data)

                await client.start_notify(BEEF_CHARACTERISTIC, handle_notify)
                notified = True
                self._set_connected(True)
                _LOGGER.debug(
                    "Started notification listener for characteristic %s",
                    BEEF_CHARACTERISTIC,
                )

                if not self._paired_once:
                    self._paired_once = True
                    data = {**self.entry.data, DATA_PAIRED_ONCE: True}
                    self.hass.config_entries.async_update_entry(
                        self.entry, data=data
                    )

                attempt = 0

                # asyncio.wait() requires tasks; passing bare coroutines raises
                # TypeError on Python 3.11+.
                waiters = [
                    asyncio.create_task(self._stop_event.wait()),
                    asyncio.create_task(disconnect_event.wait()),
                ]
                try:
                    await asyncio.wait(
                        waiters, return_when=asyncio.FIRST_COMPLETED
                    )
                finally:
                    for waiter in waiters:
                        waiter.cancel()

            except BleakError as err:
                error_type = "Bluetooth connection error"
                if "ESP_GATT_CONN_FAIL_ESTABLISH" in str(err):
                    error_type = (
                        "GATT connection establishment failed (device may be busy or out of range)"
                    )
                elif "Device not found" in str(err):
                    error_type = "Device not found"
                elif "timeout" in str(err).lower():
                    error_type = "Connection timeout"

                _LOGGER.warning(
                    "%s for Roroshetta device at %s (attempt %d): %s",
                    error_type,
                    address,
                    attempt + 1,
                    err,
                )
            except Exception as err:
                _LOGGER.error(
                    "Unexpected error streaming notifications for Roroshetta device at %s (attempt %d): %s",
                    address,
                    attempt + 1,
                    err,
                )
            finally:
                if client is not None:
                    try:
                        if notified:
                            await client.stop_notify(BEEF_CHARACTERISTIC)
                    except Exception:
                        pass
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                self._client = None
                self._set_connected(False)

            if self._stop_event.is_set():
                break

            wait_time = min(MAX_BACKOFF_SECONDS, 2**attempt)
            _LOGGER.debug(
                "Reconnecting to Roroshetta device at %s in %d seconds",
                address,
                wait_time,
            )
            if await self._sleep_or_stop(wait_time):
                break
            attempt += 1

    def _parse_data(self, data: bytes) -> None:
        """Parse the data from the device."""
        _LOGGER.debug("Parsing data from Roroshetta device: %s bytes", len(data))
        if len(data) < 60:
            _LOGGER.warning("Received data too short: %d bytes", len(data))
            return

        def get_u16_le(offset: int, length: int = 2) -> int:
            return int.from_bytes(data[offset : offset + length], "little")

        # Parse sensor data as in the test.py
        self.data.temperature = (get_u16_le(0, 2) + 10000) / 100 - 150
        self.data.heat_index = (get_u16_le(2, 2) + 10000) / 100 - 150
        self.data.humidity = get_u16_le(4, 2) / 100
        self.data.aqi = get_u16_le(10, 2)
        self.data.pm25 = get_u16_le(13, 2) / 1000
        self.data.co2 = get_u16_le(15, 2)
        self.data.tvoc = get_u16_le(17, 2)
        self.data.uptime = get_u16_le(36, 3)
        self.data.alarm_level = get_u16_le(44, 1)
        self.data.activity = get_u16_le(45, 1)
        self.data.power = get_u16_le(46, 2)
        self.data.light = get_u16_le(53, 1) / 30
        self.data.fan = get_u16_le(56, 1) / 30
        self.data.grease_filter = get_u16_le(59, 1)

        _LOGGER.debug(
            "Parsed Roroshetta data: temperature=%.2f°C, humidity=%.1f%%, CO2=%d ppm, TVOC=%d ppb, PM2.5=%.2f µg/m³, uptime=%d s",
            self.data.temperature,
            self.data.humidity,
            self.data.co2,
            self.data.tvoc,
            self.data.pm25,
            self.data.uptime,
        )
