"""Sensor platform for Safera Sense."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfDensity,
    UnitOfPower,
    UnitOfRatio,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DEVICE_STATES, DOMAIN
from .coordinator import (
    SaferaConfigEntry,
    SaferaDataUpdateCoordinator,
    SaferaData,
    format_sw_version,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SaferaSensorEntityDescription(SensorEntityDescription):
    """Describes Safera sensor entity."""

    value_fn: Callable[[SaferaDataUpdateCoordinator], StateType | datetime]


SENSORS: tuple[SaferaSensorEntityDescription, ...] = (
    SaferaSensorEntityDescription(
        key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.temperature,
    ),
    SaferaSensorEntityDescription(
        key="heat_index",
        name="Heat Index",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.heat_index,
    ),
    SaferaSensorEntityDescription(
        key="humidity",
        name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.humidity,
    ),
    SaferaSensorEntityDescription(
        key="co2",
        name="CO₂",
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.co2,
    ),
    SaferaSensorEntityDescription(
        key="tvoc",
        name="tVOC",
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.tvoc,
    ),
    SaferaSensorEntityDescription(
        key="pm25",
        name="PM2.5",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.pm25,
    ),
    SaferaSensorEntityDescription(
        key="aqi",
        name="Air Quality Index",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.aqi,
    ),
    SaferaSensorEntityDescription(
        key="grease_filter",
        name="Grease Filter",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.grease_filter,
    ),
    SaferaSensorEntityDescription(
        key="light",
        name="Light Level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.light,
    ),
    SaferaSensorEntityDescription(
        key="fan",
        name="Fan Level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.fan,
    ),
    SaferaSensorEntityDescription(
        key="activity",
        name="Activity",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.activity,
    ),
    SaferaSensorEntityDescription(
        key="alarm_level",
        name="Alarm Level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.alarm_level,
    ),
    SaferaSensorEntityDescription(
        key="power",
        name="Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.power,
    ),
    SaferaSensorEntityDescription(
        key="last_ok_press",
        name="Last OK pressed",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda coordinator: coordinator.last_ok_press,
    ),
    SaferaSensorEntityDescription(
        key="device_state",
        name="Device state",
        device_class=SensorDeviceClass.ENUM,
        options=list(DEVICE_STATES.values()),
        value_fn=lambda coordinator: DEVICE_STATES.get(
            coordinator.data.device_state
        ),
    ),
    SaferaSensorEntityDescription(
        key="uptime",
        name="Uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda coordinator: coordinator.data.uptime,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SaferaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Safera sensors."""
    _LOGGER.debug("Setting up Safera sensors for entry: %s", entry.entry_id)
    coordinator = entry.runtime_data

    sensors = [SaferaSensor(coordinator, description) for description in SENSORS]
    _LOGGER.debug("Created %d Safera sensor entities", len(sensors))
    async_add_entities(sensors)
    _LOGGER.debug("Added Safera sensor entities to Home Assistant")


class SaferaSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Safera sensor."""

    entity_description: SaferaSensorEntityDescription

    def __init__(
        self,
        coordinator: SaferaDataUpdateCoordinator,
        description: SaferaSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        _LOGGER.debug(
            "Initializing Safera sensor: %s for device %s",
            description.key,
            coordinator.address,
        )
        super().__init__(coordinator)
        self.entity_description = description
        address = coordinator.device_identifier
        self._attr_unique_id = f"{address}_{description.key}"
        # Read from the hood's Device Information Service and cached in the
        # config entry; empty only on the very first run, before the first
        # connection, after which the coordinator updates the registry itself.
        info = coordinator.device_info_values
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(address))},
            name="Safera Sense",
            manufacturer=info.get("manufacturer", "Safera Oy"),
            model=info.get("model", "Sense"),
            serial_number=info.get("serial_number"),
            hw_version=info.get("hw_version"),
            sw_version=format_sw_version(info),
        )

    @property
    def native_value(self) -> StateType | datetime:
        """Return the native value of the sensor."""
        return self.entity_description.value_fn(self.coordinator)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.device_available
