"""Coordinator for Safera Sense."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.exc import BleakError
try:
    from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
except ImportError:  # pragma: no cover - fallback for environments without the helper
    BleakClientWithServiceCache = BleakClient  # type: ignore[misc,assignment]
    establish_connection = None

from homeassistant.components import bluetooth
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    ABBA_CHARACTERISTIC,
    ABBA_HANDLE,
    ABCF_CHARACTERISTIC,
    ABCF_HANDLE,
    BABE_CHARACTERISTIC,
    BABE_HANDLE,
    DCBA_CHARACTERISTIC,
    DCBA_HANDLE,
    EVENT_RECORD_SIZE,
    BEEF_CHARACTERISTIC,
    COMMAND_MIN_INTERVAL_SECONDS,
    COMMAND_TIMEOUT_SECONDS,
    SETTINGS_LENGTH,
    DATA_DEVICE_INFO,
    DATA_PAIRED_ONCE,
    DEVICE_WAIT_SECONDS,
    DIS_FIRMWARE_REV,
    DIS_HARDWARE_REV,
    DIS_MANUFACTURER,
    DIS_MODEL,
    DIS_SERIAL,
    DIS_SOFTWARE_REV,
    DOMAIN,
    MAX_BACKOFF_SECONDS,
    PAIRING_WINDOW_SECONDS,
    STALE_AFTER_SECONDS,
    STOP_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

# Raw frames on their own logger so they can be captured without turning on
# debug for everything else:
#   action: logger.set_level
#   data: {"custom_components.safera.coordinator.frames": "debug"}
# Emits one hex line per frame (~1/second), for mapping the payload offsets
# that are still unknown. See CLAUDE.md.
_FRAME_LOGGER = logging.getLogger(f"{__name__}.frames")

# Device events on their own logger, at **warning**: they are rare, each one
# matters, and Home Assistant's default level here hides info. An alarm trip has
# never been captured, so the codes are unmapped — see captures/gatt.md.
_EVENT_LOGGER = logging.getLogger(f"{__name__}.events")

type SaferaConfigEntry = ConfigEntry[SaferaDataUpdateCoordinator]


# Device Information Service fields read on connect, in read order.
DIS_FIELDS: tuple[tuple[str, str], ...] = (
    ("manufacturer", DIS_MANUFACTURER),
    ("model", DIS_MODEL),
    ("serial_number", DIS_SERIAL),
    ("hw_version", DIS_HARDWARE_REV),
    ("firmware_rev", DIS_FIRMWARE_REV),
    ("software_rev", DIS_SOFTWARE_REV),
)


def format_sw_version(values: dict[str, str]) -> str | None:
    """Combine the two revision strings the hood reports into one label.

    The Device Information Service exposes Firmware Revision and Software
    Revision separately, but ``DeviceInfo`` only has ``sw_version``.
    """
    firmware = values.get("firmware_rev")
    software = values.get("software_rev")
    if firmware and software:
        return f"{firmware} (software {software})"
    return firmware or software or None


@dataclass
class SaferaData:
    """Data from Safera Sense device."""

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
    # Raw bytes behind the two scaled fields above, all confirmed 1:1 against
    # commanded values: @53 on/off, @54 brightness, @55 colour (warm to cool),
    # @57 the actual motor speed in the same 0-255 units the fan command takes.
    # @54 and @55 both read 0 while the lamp is off.
    light_raw: int | None = None
    light_brightness: int | None = None
    light_color: int | None = None
    fan_speed: int | None = None
    auto_flags: int | None = None
    activity: int | None = None
    alarm_level: int | None = None
    power: int | None = None
    uptime: int | None = None


class SaferaDataUpdateCoordinator(DataUpdateCoordinator[SaferaData]):
    """Class to manage fetching Safera data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        entry: SaferaConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        address = entry.unique_id
        assert address is not None
        _LOGGER.debug("Initializing Safera coordinator for device %s", address)
        super().__init__(
            hass=hass,
            logger=logger,
            name=DOMAIN,
            update_interval=None,
        )
        self.address = address
        self.entry = entry
        self.data = SaferaData()
        self._client: BleakClient | None = None
        self._paired_once = bool(entry.data.get(DATA_PAIRED_ONCE))
        self._device_info: dict[str, str] = dict(
            entry.data.get(DATA_DEVICE_INFO) or {}
        )
        self._pairing_delay_done = False
        self._stop_event = asyncio.Event()
        self._connection_task: asyncio.Task[None] | None = None
        self._connected = False
        self._last_notification: float | None = None
        self._command_char: object | int | None = None
        self._settings_write_char: object | int | None = None
        self._settings_read_char: object | int | None = None
        self._settings: bytes | None = None
        self._events: list[tuple[int, int]] = []
        self._command_lock = asyncio.Lock()
        self._last_command: float | None = None
        _LOGGER.debug("Safera coordinator initialized successfully")

    @property
    def device_identifier(self) -> str:
        """Stable id used for the device registry entry and unique ids."""
        return (
            self.entry.unique_id
            or self.entry.data.get(CONF_ADDRESS)
            or self.address
            or self.entry.entry_id
        )

    @property
    def device_info_values(self) -> dict[str, str]:
        """Cached Device Information Service strings, empty until first read."""
        return self._device_info

    async def _async_read_device_info(self, client: BleakClient) -> None:
        """Read the Device Information Service once and cache it.

        These strings never change for a given hood, so this runs only until it
        succeeds; afterwards the values come from the config entry and are
        available at setup, before any connection exists.
        """
        # Retry while anything is still missing, so a flaky link that yielded
        # only some fields heals on a later connect, and a cache written by an
        # older version picks up fields added since.
        if all(key in self._device_info for key, _ in DIS_FIELDS):
            return

        values: dict[str, str] = dict(self._device_info)
        for key, uuid in DIS_FIELDS:
            try:
                raw = await client.read_gatt_char(uuid)
            except Exception as err:  # noqa: BLE001 - never block streaming on this
                _LOGGER.debug("Could not read device info %s: %s", key, err)
                continue
            text = raw.decode("utf-8", "replace").replace("\x00", "").strip()
            if text:
                values[key] = text

        if not values:
            return

        self._device_info = values
        _LOGGER.debug("Read device information: %s", values)

        # Preserve every other key, notably DATA_PAIRED_ONCE.
        self.hass.config_entries.async_update_entry(
            self.entry, data={**self.entry.data, DATA_DEVICE_INFO: values}
        )
        self._update_device_registry(values)

    def _update_device_registry(self, values: dict[str, str]) -> None:
        """Push the strings onto the existing device registry entry.

        Entities set ``device_info`` when they are added, which on a first run
        happens before the hood has ever been connected. Without this the real
        values would not appear until the next restart.
        """
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(
            identifiers={(DOMAIN, str(self.device_identifier))}
        )
        if device is None:
            return
        registry.async_update_device(
            device.id,
            manufacturer=values.get("manufacturer"),
            model=values.get("model"),
            serial_number=values.get("serial_number"),
            hw_version=values.get("hw_version"),
            sw_version=format_sw_version(values),
        )

    def _resolve_char(
        self, client: BleakClient, uuid: str, handle: int
    ) -> object | int:
        """Find a characteristic once per connection.

        Looking one up by UUID string at write time has failed with
        ``BleakCharacteristicNotFoundError`` on connections whose cached GATT
        table was incomplete, even while notifications on the same service were
        streaming. Resolving the object up front avoids that, and the handle is
        a last resort if the table really does not list it.
        """
        for service in client.services:
            for characteristic in service.characteristics:
                if characteristic.uuid.lower() == uuid:
                    return characteristic
        _LOGGER.warning(
            "Characteristic %s not in the GATT table; falling back to handle %s",
            uuid,
            handle,
        )
        return handle

    async def async_send_command(self, code: int, param: int = 0) -> None:
        """Write one command to the hood.

        The payload is a 4-byte little-endian code followed by a 4-byte
        little-endian parameter. Raises ``HomeAssistantError`` rather than
        failing silently, so a service call reports the problem to the caller.
        """
        client = self._client
        if client is None or not self._connected or not client.is_connected:
            raise HomeAssistantError(
                "Safera is not connected, so the command was not sent"
            )
        for value, name in ((code, "code"), (param, "parameter")):
            if not 0 <= value <= 0xFFFFFFFF:
                raise HomeAssistantError(
                    f"Command {name} {value} does not fit in 4 bytes"
                )

        payload = code.to_bytes(4, "little") + param.to_bytes(4, "little")

        # Serialise commands and space them out. A burst of writes has dropped
        # the BLE link before, which takes every entity down with it.
        async with self._command_lock:
            if self._last_command is not None:
                gap = self.hass.loop.time() - self._last_command
                if gap < COMMAND_MIN_INTERVAL_SECONDS:
                    await asyncio.sleep(COMMAND_MIN_INTERVAL_SECONDS - gap)

            target = self._command_char
            if target is None:
                target = self._command_char = self._resolve_char(
                    client, BABE_CHARACTERISTIC, BABE_HANDLE
                )

            _LOGGER.debug(
                "Sending command 0x%04x param=%d (%s)", code, param, payload.hex()
            )
            try:
                async with asyncio.timeout(COMMAND_TIMEOUT_SECONDS):
                    await client.write_gatt_char(target, payload, response=True)
            except Exception as err:
                raise HomeAssistantError(
                    f"Failed to send command 0x{code:04x} param={param}: "
                    f"{type(err).__name__}: {err}"
                ) from err
            finally:
                self._last_command = self.hass.loop.time()

        _LOGGER.info(
            "Sent command 0x%04x param=%d; light=%s fan=%s",
            code,
            param,
            self.data.light,
            self.data.fan,
        )

    @staticmethod
    def _parse_event_log(data: bytes) -> list[tuple[int, int]]:
        """Decode the event log: a count, then (code, uptime) records."""
        if len(data) < 2:
            return []
        count = int.from_bytes(data[0:2], "little")
        events: list[tuple[int, int]] = []
        offset = 2
        while offset + EVENT_RECORD_SIZE <= len(data) and len(events) < count:
            code = data[offset]
            timestamp = int.from_bytes(
                data[offset + 1 : offset + EVENT_RECORD_SIZE], "little"
            )
            events.append((code, timestamp))
            offset += EVENT_RECORD_SIZE
        return events

    def _handle_event_log(self, data: bytes) -> None:
        """Log any event the hood has added since we last looked."""
        _EVENT_LOGGER.debug("Event log: %s", data.hex())
        events = self._parse_event_log(data)
        known = set(self._events)
        for code, timestamp in events:
            if (code, timestamp) not in known:
                _EVENT_LOGGER.warning(
                    "Device event: code %d (0x%02x) at uptime %d s", code, code, timestamp
                )
        self._events = events

    @property
    def events(self) -> list[tuple[int, int]]:
        """Most recent device event log, as (code, uptime) pairs."""
        return self._events

    @property
    def settings(self) -> bytes | None:
        """Cached configuration block, or None before the first read.

        Refreshed once per connection and after every write, which is enough:
        nothing changes it except the Safera app, and an edit made there shows
        up on the next reconnect.
        """
        return self._settings

    async def async_read_settings(self) -> bytes:
        """Read the whole configuration block and cache it."""
        client = self._client
        if client is None or not self._connected or not client.is_connected:
            raise HomeAssistantError("Safera is not connected")
        target = self._settings_read_char
        if target is None:
            target = self._settings_read_char = self._resolve_char(
                client, DCBA_CHARACTERISTIC, DCBA_HANDLE
            )
        async with self._command_lock:
            try:
                async with asyncio.timeout(COMMAND_TIMEOUT_SECONDS):
                    self._settings = bytes(await client.read_gatt_char(target))
                    # Logged whole so the block can be diffed around a change
                    # made in the Safera app, which is how every offset in it
                    # has been identified. Contains no personal data.
                    _LOGGER.debug("Settings block: %s", self._settings.hex())
                    return self._settings
            except Exception as err:
                raise HomeAssistantError(
                    f"Failed to read settings: {type(err).__name__}: {err}"
                ) from err

    async def async_write_setting(self, offset: int, value: int) -> int:
        """Write one byte of the configuration block and read it back.

        Writes are two bytes to the settings characteristic — the offset into
        the block, then the value. The block also holds stove-guard
        configuration, so this is deliberately low level and has no notion of
        which offsets are safe to touch; callers are expected to know.

        Returns the value actually stored, read back afterwards, so a caller can
        tell a silently ignored write from one that took.
        """
        client = self._client
        if client is None or not self._connected or not client.is_connected:
            raise HomeAssistantError(
                "Safera is not connected, so the setting was not written"
            )
        if not 0 <= offset < SETTINGS_LENGTH:
            raise HomeAssistantError(
                f"Setting offset {offset} is outside the {SETTINGS_LENGTH}-byte block"
            )
        if not 0 <= value <= 0xFF:
            raise HomeAssistantError(f"Setting value {value} is not a byte")

        async with self._command_lock:
            if self._last_command is not None:
                gap = self.hass.loop.time() - self._last_command
                if gap < COMMAND_MIN_INTERVAL_SECONDS:
                    await asyncio.sleep(COMMAND_MIN_INTERVAL_SECONDS - gap)

            target = self._settings_write_char
            if target is None:
                target = self._settings_write_char = self._resolve_char(
                    client, ABBA_CHARACTERISTIC, ABBA_HANDLE
                )
            _LOGGER.debug("Writing setting @%d = %d", offset, value)
            try:
                async with asyncio.timeout(COMMAND_TIMEOUT_SECONDS):
                    await client.write_gatt_char(
                        target, bytes([offset, value]), response=True
                    )
            except Exception as err:
                raise HomeAssistantError(
                    f"Failed to write setting @{offset}={value}: "
                    f"{type(err).__name__}: {err}"
                ) from err
            finally:
                self._last_command = self.hass.loop.time()

        settings = await self.async_read_settings()
        self.async_update_listeners()
        stored = settings[offset]
        _LOGGER.info(
            "Wrote setting @%d = %d, device reports %d", offset, value, stored
        )
        return stored

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
        _LOGGER.debug("Safera connection state: %s", connected)
        self.async_update_listeners()

    async def async_start_notify(self) -> None:
        """Start the continuous notification connection loop."""
        if self._connection_task and not self._connection_task.done():
            return
        self._stop_event.clear()
        self._connection_task = self.entry.async_create_background_task(
            self.hass, self._run_notify_loop(), name=f"{DOMAIN} notify loop"
        )

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
        address = self.address
        attempt = 0

        while not self._stop_event.is_set():
            available_device = bluetooth.async_ble_device_from_address(
                self.hass, address
            )
            if not available_device:
                _LOGGER.debug(
                    "Safera device at %s is not available in the Bluetooth cache",
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
                    "Connecting to Safera device at %s (attempt %d)",
                    address,
                    attempt + 1,
                )

                def on_disconnect(_client: BleakClient) -> None:
                    """Wake the loop so it reconnects."""
                    _LOGGER.debug(
                        "Safera device at %s disconnected", address
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

                _LOGGER.debug("Connected to Safera device at %s", address)

                await self._async_read_device_info(client)
                self._command_char = self._resolve_char(
                    client, BABE_CHARACTERISTIC, BABE_HANDLE
                )
                self._settings_write_char = self._resolve_char(
                    client, ABBA_CHARACTERISTIC, ABBA_HANDLE
                )
                self._settings_read_char = self._resolve_char(
                    client, DCBA_CHARACTERISTIC, DCBA_HANDLE
                )
                if not self._paired_once and hasattr(client, "pair"):
                    await client.pair()

                def handle_notify(sender, data):
                    """Handle notification from device."""
                    _LOGGER.debug(
                        "Received notification from Safera device: %s bytes",
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

                # The event log is where an alarm should register. Failing to
                # subscribe must never take the sensor stream down with it.
                try:
                    event_char = self._resolve_char(
                        client, ABCF_CHARACTERISTIC, ABCF_HANDLE
                    )
                    self._handle_event_log(
                        bytes(await client.read_gatt_char(event_char))
                    )
                    await client.start_notify(
                        event_char,
                        lambda _sender, data: self._handle_event_log(bytes(data)),
                    )
                    _LOGGER.debug("Subscribed to the device event log")
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("Could not subscribe to the event log: %s", err)

                # After _set_connected, which async_read_settings requires: it
                # refuses to read while the coordinator still counts as
                # disconnected.
                try:
                    await self.async_read_settings()
                    self.async_update_listeners()
                except Exception as err:  # noqa: BLE001 - never block streaming
                    _LOGGER.warning("Could not read the settings block: %s", err)

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
                    "%s for Safera device at %s (attempt %d): %s",
                    error_type,
                    address,
                    attempt + 1,
                    err,
                )
            except Exception as err:
                _LOGGER.error(
                    "Unexpected error streaming notifications for Safera device at %s (attempt %d): %s",
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
                # The characteristic object belongs to this connection's GATT
                # table; keeping it would write through a dead client.
                self._command_char = None
                self._settings_write_char = None
                self._settings_read_char = None
                # Keep the cached block: the numbers stay meaningful across a
                # reconnect, and it is refreshed as soon as we are back.
                self._set_connected(False)

            if self._stop_event.is_set():
                break

            wait_time = min(MAX_BACKOFF_SECONDS, 2**attempt)
            _LOGGER.debug(
                "Reconnecting to Safera device at %s in %d seconds",
                address,
                wait_time,
            )
            if await self._sleep_or_stop(wait_time):
                break
            attempt += 1

    def _parse_data(self, data: bytes) -> None:
        """Parse the data from the device."""
        # Logged before the length check so undersized frames are captured too.
        _FRAME_LOGGER.debug("%d %s", len(data), data.hex())
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
        self.data.light_raw = get_u16_le(53, 1)
        self.data.light_brightness = get_u16_le(54, 1)
        self.data.light_color = get_u16_le(55, 1)
        self.data.fan_speed = get_u16_le(57, 1)
        self.data.auto_flags = get_u16_le(60, 1)
        self.data.grease_filter = get_u16_le(59, 1)

        _LOGGER.debug(
            "Parsed Safera data: temperature=%.2f°C, humidity=%.1f%%, CO2=%d ppm, TVOC=%d µg/m³, PM2.5=%.2f µg/m³, uptime=%d s",
            self.data.temperature,
            self.data.humidity,
            self.data.co2,
            self.data.tvoc,
            self.data.pm25,
            self.data.uptime,
        )
