"""Coordinator for Roroshetta Sense."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import BEEF_CHARACTERISTIC, DOMAIN, UPDATE_INTERVAL

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


class RoroshettaDataUpdateCoordinator(
    ActiveBluetoothDataUpdateCoordinator[RoroshettaData]
):
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
            address=ble_device.address,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_update,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            connectable=True,
        )
        self.ble_device = ble_device
        self.entry = entry
        self.data = RoroshettaData()
        self._client: BleakClient | None = None
        self._notification_received = asyncio.Event()
        _LOGGER.debug("Roroshetta coordinator initialized successfully")

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_poll: float | None,
    ) -> bool:
        """Return True if we need to poll."""
        needs_poll = (
            self.hass.state is CoreState.running
            and (
                seconds_since_last_poll is None
                or seconds_since_last_poll >= UPDATE_INTERVAL
            )
            and bool(
                bluetooth.async_ble_device_from_address(
                    self.hass, service_info.device.address, connectable=True
                )
            )
        )
        available_device = bluetooth.async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        )
        _LOGGER.debug(
            "Roroshetta device %s needs poll: %s (seconds since last poll: %s, device available: %s)",
            service_info.device.address,
            needs_poll,
            seconds_since_last_poll,
            available_device is not None,
        )
        return needs_poll

    async def _async_update(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> RoroshettaData:
        """Poll the device."""
        _LOGGER.debug(
            "Starting data update for Roroshetta device at %s",
            service_info.device.address,
        )

        # Check if device is available before attempting connection
        available_device = bluetooth.async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        )
        if not available_device:
            error_msg = f"Roroshetta device at {service_info.device.address} is not available for connection"
            _LOGGER.warning(error_msg)
            raise UpdateFailed(error_msg)

        _LOGGER.debug("Device is available, proceeding with connection")
        self._notification_received.clear()

        # Retry connection up to 3 times with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                _LOGGER.debug(
                    "Connection attempt %d/%d for Roroshetta device at %s (with pairing enabled)",
                    attempt + 1,
                    max_retries,
                    service_info.device.address,
                )

                # Use shorter timeout for initial connection and enable pairing
                async with BleakClient(
                    service_info.device, timeout=10.0, pair=True
                ) as client:
                    self._client = client
                    _LOGGER.debug(
                        "Connected to Roroshetta device at %s",
                        service_info.device.address,
                    )

                    def handle_notify(sender, data):
                        """Handle notification from device."""
                        _LOGGER.debug(
                            "Received notification from Roroshetta device: %s bytes",
                            len(data),
                        )
                        self._parse_data(data)
                        self._notification_received.set()

                    await client.start_notify(BEEF_CHARACTERISTIC, handle_notify)
                    _LOGGER.debug(
                        "Started notification listener for characteristic %s",
                        BEEF_CHARACTERISTIC,
                    )

                    # Wait for notification with shorter timeout
                    try:
                        await asyncio.wait_for(
                            self._notification_received.wait(), timeout=8.0
                        )
                        _LOGGER.debug(
                            "Successfully received notification from Roroshetta device"
                        )
                    except asyncio.TimeoutError:
                        _LOGGER.warning(
                            "Timeout waiting for notification from Roroshetta device at %s",
                            service_info.device.address,
                        )

                    await client.stop_notify(BEEF_CHARACTERISTIC)
                    _LOGGER.debug("Stopped notification listener")
                    break  # Success, exit retry loop

            except BleakError as err:
                error_type = "Bluetooth connection error"
                if "ESP_GATT_CONN_FAIL_ESTABLISH" in str(err):
                    error_type = "GATT connection establishment failed (device may be busy or out of range)"
                elif "Device not found" in str(err):
                    error_type = "Device not found"
                elif "timeout" in str(err).lower():
                    error_type = "Connection timeout"

                error_msg = f"{error_type} for Roroshetta device at {service_info.device.address} (attempt {attempt + 1}/{max_retries}): {err}"
                _LOGGER.warning(error_msg)

                # If this is the last attempt, raise the error
                if attempt == max_retries - 1:
                    _LOGGER.error(
                        "All connection attempts failed for Roroshetta device at %s",
                        service_info.device.address,
                    )
                    raise UpdateFailed(error_msg) from err

                # Wait before retrying with exponential backoff
                wait_time = 2**attempt  # 1s, 2s, 4s
                _LOGGER.debug(
                    "Waiting %d seconds before retry for Roroshetta device at %s",
                    wait_time,
                    service_info.device.address,
                )
                await asyncio.sleep(wait_time)

            except Exception as err:
                error_msg = f"Unexpected error polling Roroshetta device at {service_info.device.address} (attempt {attempt + 1}/{max_retries}): {err}"
                _LOGGER.error(error_msg)

                # For unexpected errors, don't retry
                raise UpdateFailed(error_msg) from err

        self._client = None

        parsed_data = self.data
        _LOGGER.debug("Returning parsed data from Roroshetta device: %s", parsed_data)
        return parsed_data

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

    @callback
    def _async_handle_unavailable(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Handle the device going unavailable."""
        super()._async_handle_unavailable(service_info)
        _LOGGER.info("Roroshetta device %s is unavailable", service_info.device.address)

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle a Bluetooth event."""
        self.ble_device = service_info.device
        super()._async_handle_bluetooth_event(service_info, change)
