"""Fan platform for Roroshetta Sense."""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .const import CMD_MOTOR_RAW_SPEED, FAN_SPEED_RANGE
from .coordinator import RoroshettaConfigEntry, RoroshettaDataUpdateCoordinator
from .entity import RoroshettaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoroshettaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the hood fan."""
    async_add_entities([RoroshettaFan(entry.runtime_data)])


class RoroshettaFan(RoroshettaEntity, FanEntity):
    """The hood's extraction fan.

    ``CMD_MOTOR_RAW_SPEED`` takes 0-255 and byte 57 reports the actual motor
    speed in the same units, so unlike the light this has real feedback rather
    than optimistic state. Confirmed by a commanded sweep on 2026-08-28.

    Note byte 56, which the fan *sensor* exposes, is a different thing: it is a
    level index the hood's own controller maintains and it stays at 0 while a
    BLE speed command is driving the motor.
    """

    _attr_name = "Fan"
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: RoroshettaDataUpdateCoordinator) -> None:
        """Initialise the fan."""
        super().__init__(coordinator, "fan")

    @property
    def is_on(self) -> bool | None:
        """Whether the motor is turning, from byte 57."""
        speed = self.coordinator.data.fan_speed
        if speed is None:
            return None
        return speed > 0

    @property
    def percentage(self) -> int | None:
        """Current speed as a percentage of the raw 1-255 range."""
        speed = self.coordinator.data.fan_speed
        if speed is None:
            return None
        if speed == 0:
            return 0
        # Never round a turning motor down to 0%: Home Assistant reads 0% as
        # off, which would contradict is_on and make the entity flicker.
        return max(1, ranged_value_to_percentage(FAN_SPEED_RANGE, speed))

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the motor speed. 0 stops it."""
        if percentage == 0:
            raw = 0
        else:
            raw = math.ceil(percentage_to_ranged_value(FAN_SPEED_RANGE, percentage))
        await self.coordinator.async_send_command(CMD_MOTOR_RAW_SPEED, raw)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Start the fan, defaulting to full speed."""
        await self.async_set_percentage(percentage if percentage is not None else 100)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the fan."""
        await self.async_set_percentage(0)
