"""Number platform for Roroshetta Sense preset settings."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    FAN_PRESET_MAX,
    LIGHT_KELVIN_BASE,
    LIGHT_KELVIN_PER_STEP,
    LIGHT_MAX_KELVIN,
    LIGHT_MIN_KELVIN,
    LIGHT_PRESET_BRIGHTNESS_MAX,
    SETTINGS_LIGHT_BRIGHTNESS,
    SETTINGS_LIGHT_COLOR,
    SETTINGS_MOTOR1_PRESETS,
    SETTINGS_VENT_SENSITIVITY,
)
from .coordinator import RoroshettaConfigEntry, RoroshettaDataUpdateCoordinator
from .entity import RoroshettaEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class RoroshettaNumberDescription(NumberEntityDescription):
    """One editable byte of the hood's settings block."""

    offset: int
    to_raw: Callable[[float], int]
    from_raw: Callable[[int], float]


def _pct_to_raw(scale: int) -> Callable[[float], int]:
    return lambda value: max(0, min(scale, round(value * scale / 100)))


def _raw_to_pct(scale: int) -> Callable[[int], float]:
    return lambda raw: round(raw * 100 / scale)


def _kelvin_to_raw(value: float) -> int:
    raw = round((value - LIGHT_KELVIN_BASE) / LIGHT_KELVIN_PER_STEP)
    return max(0, min(255, raw))


def _raw_to_kelvin(raw: int) -> float:
    return LIGHT_KELVIN_BASE + raw * LIGHT_KELVIN_PER_STEP


def _fan_preset(index: int, label: str) -> RoroshettaNumberDescription:
    """Motor 1 ventilation preset. Index 0 is level 0, 5 is boost."""
    return RoroshettaNumberDescription(
        key=f"fan_preset_{label.lower()}",
        name=f"Fan preset {label}",
        offset=SETTINGS_MOTOR1_PRESETS + index,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=None,
        to_raw=_pct_to_raw(FAN_PRESET_MAX),
        from_raw=_raw_to_pct(FAN_PRESET_MAX),
    )


NUMBERS: tuple[RoroshettaNumberDescription, ...] = (
    # How eagerly the hood ramps the fan while cooking. Stored as a plain
    # percentage with no scaling; the app calls 50 the default.
    RoroshettaNumberDescription(
        key="ventilation_sensitivity",
        name="Ventilation sensitivity",
        offset=SETTINGS_VENT_SENSITIVITY,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        to_raw=lambda value: max(0, min(100, round(value))),
        from_raw=lambda raw: raw,
    ),
    _fan_preset(1, "1"),
    _fan_preset(2, "2"),
    _fan_preset(3, "3"),
    _fan_preset(4, "4"),
    _fan_preset(5, "Boost"),
    *(
        RoroshettaNumberDescription(
            key=f"light_preset_{n}_brightness",
            name=f"Light preset {n} brightness",
            offset=SETTINGS_LIGHT_BRIGHTNESS + n - 1,
            native_min_value=0,
            native_max_value=100,
            native_step=1,
            native_unit_of_measurement=PERCENTAGE,
            mode=NumberMode.SLIDER,
            to_raw=_pct_to_raw(LIGHT_PRESET_BRIGHTNESS_MAX),
            from_raw=_raw_to_pct(LIGHT_PRESET_BRIGHTNESS_MAX),
        )
        for n in (1, 2, 3)
    ),
    *(
        RoroshettaNumberDescription(
            key=f"light_preset_{n}_color",
            name=f"Light preset {n} colour",
            offset=SETTINGS_LIGHT_COLOR + n - 1,
            native_min_value=LIGHT_MIN_KELVIN,
            native_max_value=LIGHT_MAX_KELVIN,
            native_step=LIGHT_KELVIN_PER_STEP,
            native_unit_of_measurement=UnitOfTemperature.KELVIN,
            device_class=NumberDeviceClass.TEMPERATURE,
            mode=NumberMode.SLIDER,
            to_raw=_kelvin_to_raw,
            from_raw=_raw_to_kelvin,
        )
        for n in (1, 2, 3)
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoroshettaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the preset number entities."""
    async_add_entities(
        RoroshettaPresetNumber(entry.runtime_data, description)
        for description in NUMBERS
    )


class RoroshettaPresetNumber(RoroshettaEntity, NumberEntity):
    """One byte of the settings block, exposed as an adjustable number.

    These are the same presets the Safera app edits under Cooker Hood Settings.
    They live in the settings block rather than the notify stream, so the value
    comes from a cached read refreshed once per connection and after each write.
    """

    entity_description: RoroshettaNumberDescription

    def __init__(
        self,
        coordinator: RoroshettaDataUpdateCoordinator,
        description: RoroshettaNumberDescription,
    ) -> None:
        """Initialise the number."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Needs the settings block as well as a live connection."""
        return super().available and self.coordinator.settings is not None

    @property
    def native_value(self) -> float | None:
        """Current value, converted from the stored byte."""
        settings = self.coordinator.settings
        if settings is None or self.entity_description.offset >= len(settings):
            return None
        return self.entity_description.from_raw(
            settings[self.entity_description.offset]
        )

    async def async_set_native_value(self, value: float) -> None:
        """Write the byte, which also refreshes the cached block."""
        await self.coordinator.async_write_setting(
            self.entity_description.offset, self.entity_description.to_raw(value)
        )
