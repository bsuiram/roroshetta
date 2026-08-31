"""Shared entity base for the controllable Safera platforms."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SaferaDataUpdateCoordinator, format_sw_version


class SaferaEntity(CoordinatorEntity[SaferaDataUpdateCoordinator]):
    """Common device wiring for light, fan and button entities.

    ``sensor.py`` deliberately does not use this: its entities predate it and
    switching them over would risk changing their unique ids or names, which
    would orphan history. New platforms should use this.
    """

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SaferaDataUpdateCoordinator, key: str
    ) -> None:
        """Initialise shared identity and device info."""
        super().__init__(coordinator)
        address = coordinator.device_identifier
        self._attr_unique_id = f"{address}_{key}"

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
    def available(self) -> bool:
        """Follow the coordinator's connection state, not last_update_success."""
        return self.coordinator.device_available
