"""Sensor platform for Roroshetta Sense."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN
from .coordinator import (
    RoroshettaConfigEntry,
    RoroshettaDataUpdateCoordinator,
    RoroshettaData,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class RoroshettaSensorEntityDescription(SensorEntityDescription):
    """Describes Roroshetta sensor entity."""

    value_fn: Callable[[RoroshettaDataUpdateCoordinator], StateType]


SENSORS: tuple[RoroshettaSensorEntityDescription, ...] = (
    RoroshettaSensorEntityDescription(
        key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.temperature,
    ),
    RoroshettaSensorEntityDescription(
        key="heat_index",
        name="Heat Index",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.heat_index,
    ),
    RoroshettaSensorEntityDescription(
        key="humidity",
        name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.humidity,
    ),
    RoroshettaSensorEntityDescription(
        key="co2",
        name="CO₂",
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.co2,
    ),
    RoroshettaSensorEntityDescription(
        key="tvoc",
        name="tVOC",
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.tvoc,
    ),
    RoroshettaSensorEntityDescription(
        key="pm25",
        name="PM2.5",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.pm25,
    ),
    RoroshettaSensorEntityDescription(
        key="aqi",
        name="Air Quality Index",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.aqi,
    ),
    RoroshettaSensorEntityDescription(
        key="grease_filter",
        name="Grease Filter",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.grease_filter,
    ),
    RoroshettaSensorEntityDescription(
        key="light",
        name="Light Level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.light,
    ),
    RoroshettaSensorEntityDescription(
        key="fan",
        name="Fan Level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.fan,
    ),
    RoroshettaSensorEntityDescription(
        key="activity",
        name="Activity",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.activity,
    ),
    RoroshettaSensorEntityDescription(
        key="alarm_level",
        name="Alarm Level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.alarm_level,
    ),
    RoroshettaSensorEntityDescription(
        key="power",
        name="Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data.power,
    ),
    RoroshettaSensorEntityDescription(
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
    entry: RoroshettaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Roroshetta sensors."""
    _LOGGER.debug("Setting up Roroshetta sensors for entry: %s", entry.entry_id)
    coordinator = entry.runtime_data

    sensors = [RoroshettaSensor(coordinator, description) for description in SENSORS]
    _LOGGER.debug("Created %d Roroshetta sensor entities", len(sensors))
    async_add_entities(sensors)
    _LOGGER.debug("Added Roroshetta sensor entities to Home Assistant")


class RoroshettaSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Roroshetta sensor."""

    entity_description: RoroshettaSensorEntityDescription

    def __init__(
        self,
        coordinator: RoroshettaDataUpdateCoordinator,
        description: RoroshettaSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        _LOGGER.debug(
            "Initializing Roroshetta sensor: %s for device %s",
            description.key,
            coordinator.ble_device.address,
        )
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.ble_device.address}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.ble_device.address)},
            name="Roroshetta Sense",
            manufacturer="Roroshetta",
            model="Sense",
        )

    @property
    def native_value(self) -> StateType:
        """Return the native value of the sensor."""
        value = self.entity_description.value_fn(self.coordinator)
        _LOGGER.debug(
            "Roroshetta sensor %s native value: %s", self.entity_description.key, value
        )
        return value

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.available
