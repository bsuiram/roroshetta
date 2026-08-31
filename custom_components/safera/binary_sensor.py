"""Binary sensor platform for the Safera Sense stove guard."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEVICE_STATE_ALARM, DEVICE_STATE_PRE_ALARM
from .coordinator import SaferaConfigEntry, SaferaDataUpdateCoordinator
from .entity import SaferaEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SaferaBinarySensorDescription(BinarySensorEntityDescription):
    """A binary sensor derived from the stove-guard state."""

    is_on_fn: Callable[[int | None], bool | None]


def _in_states(*states: int) -> Callable[[int | None], bool | None]:
    def check(value: int | None) -> bool | None:
        if value is None:
            return None
        return value in states

    return check


BINARY_SENSORS: tuple[SaferaBinarySensorDescription, ...] = (
    SaferaBinarySensorDescription(
        key="stove_alarm",
        name="Stove alarm",
        device_class=BinarySensorDeviceClass.SAFETY,
        is_on_fn=_in_states(DEVICE_STATE_PRE_ALARM, DEVICE_STATE_ALARM),
    ),
    SaferaBinarySensorDescription(
        key="cooktop_power_cut",
        name="Cooktop power cut",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=_in_states(DEVICE_STATE_ALARM),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SaferaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the stove-guard binary sensors."""
    async_add_entities(
        SaferaBinarySensor(entry.runtime_data, description)
        for description in BINARY_SENSORS
    )


class SaferaBinarySensor(SaferaEntity, BinarySensorEntity):
    """The stove guard's alarm state, from byte 33.

    Captured during a deliberate trip on 2026-08-31: the state went 2 → 7 when
    ``alarm_level`` reached 100, then 7 → 8 fifteen seconds later as the cooktop
    was cut, and back to 2 when the alarm was acknowledged at the hood.

    "Stove alarm" covers both 7 and 8, so it turns on when the buzzer starts
    rather than only once power has already been cut.
    """

    entity_description: SaferaBinarySensorDescription

    def __init__(
        self,
        coordinator: SaferaDataUpdateCoordinator,
        description: SaferaBinarySensorDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Whether this alarm condition is active."""
        return self.entity_description.is_on_fn(self.coordinator.data.device_state)
