"""Button platform for Roroshetta Sense."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CMD_FILTER_CHANGED
from .coordinator import RoroshettaConfigEntry, RoroshettaDataUpdateCoordinator
from .entity import RoroshettaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoroshettaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the hood buttons."""
    async_add_entities([RoroshettaFilterResetButton(entry.runtime_data)])


class RoroshettaFilterResetButton(RoroshettaEntity, ButtonEntity):
    """Reset the grease filter counter after cleaning the filter.

    Verified on 2026-08-28: the counter dropped from 22 to 0 within four
    seconds of this command, which also confirmed that byte 59 is the filter
    counter rather than something that merely looked like one.
    """

    _attr_name = "Reset grease filter"

    def __init__(self, coordinator: RoroshettaDataUpdateCoordinator) -> None:
        """Initialise the button."""
        super().__init__(coordinator, "reset_grease_filter")

    async def async_press(self) -> None:
        """Reset the filter counter to zero."""
        await self.coordinator.async_send_command(CMD_FILTER_CHANGED, 0)
