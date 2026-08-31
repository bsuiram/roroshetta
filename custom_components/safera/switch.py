"""Switch platform for Safera Sense auto modes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    AUTO_MASK_FAN,
    AUTO_MASK_LIGHT,
    CMD_LIGHT_AUTO_MODE,
    CMD_MOTOR_AUTO_MODE,
)
from .coordinator import SaferaConfigEntry, SaferaDataUpdateCoordinator
from .entity import SaferaEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SaferaAutoSwitchDescription(SwitchEntityDescription):
    """Describes one bit of the auto-mode bitmask in byte 60."""

    mask: int
    command: int


SWITCHES: tuple[SaferaAutoSwitchDescription, ...] = (
    SaferaAutoSwitchDescription(
        key="fan_auto",
        name="Fan auto mode",
        mask=AUTO_MASK_FAN,
        command=CMD_MOTOR_AUTO_MODE,
    ),
    SaferaAutoSwitchDescription(
        key="light_auto",
        name="Light auto mode",
        mask=AUTO_MASK_LIGHT,
        command=CMD_LIGHT_AUTO_MODE,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SaferaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the auto-mode switches."""
    async_add_entities(
        SaferaAutoSwitch(entry.runtime_data, description)
        for description in SWITCHES
    )


class SaferaAutoSwitch(SaferaEntity, SwitchEntity):
    """One auto mode, backed by a bit of byte 60.

    The hood starts the fan and the light by itself when it detects cooking.
    Byte 60 reports whether each of those is armed, and **any manual command
    disarms the corresponding one** — from Home Assistant, the Safera app or the
    hood's own controls alike. So turning on the light here will switch its auto
    mode off, and this switch is how to arm it again.
    """

    entity_description: SaferaAutoSwitchDescription

    def __init__(
        self,
        coordinator: SaferaDataUpdateCoordinator,
        description: SaferaAutoSwitchDescription,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Whether this auto mode is armed, from its bit in byte 60."""
        flags = self.coordinator.data.auto_flags
        if flags is None:
            return None
        return bool(flags & self.entity_description.mask)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Arm this auto mode."""
        await self.coordinator.async_send_command(self.entity_description.command, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disarm this auto mode."""
        await self.coordinator.async_send_command(self.entity_description.command, 0)
