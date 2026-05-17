"""Binary sensors for Anker Prime Charger A2345."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AnkerPrimeChargerCoordinator
from .entity import AnkerPrimeChargerEntity


@dataclass(frozen=True, kw_only=True)
class PrimeBinarySensorDescription(BinarySensorEntityDescription):
    """Describe one binary sensor."""

    source_key: str | None = None


SENSORS: tuple[PrimeBinarySensorDescription, ...] = (
    PrimeBinarySensorDescription(
        key="online",
        name="Online status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    PrimeBinarySensorDescription(
        key="mqtt_connected",
        name="MQTT connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)

PORTS = ("usbc_1", "usbc_2", "usbc_3", "usbc_4", "usba_1", "usba_2")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator: AnkerPrimeChargerCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        AnkerPrimeChargerBinarySensor(coordinator, description)
        for description in SENSORS
    ]
    for port in PORTS:
        label = port.upper().replace("_", "-")
        entities.append(
            AnkerPrimeChargerBinarySensor(
                coordinator,
                PrimeBinarySensorDescription(
                    key=f"{port}_active",
                    name=f"{label} output active",
                    source_key=f"{port}_status",
                    device_class=BinarySensorDeviceClass.POWER,
                ),
            )
        )
    async_add_entities(entities)


class AnkerPrimeChargerBinarySensor(AnkerPrimeChargerEntity, BinarySensorEntity):
    """A2345 binary sensor."""

    entity_description: PrimeBinarySensorDescription

    def __init__(
        self,
        coordinator: AnkerPrimeChargerCoordinator,
        description: PrimeBinarySensorDescription,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator, description.key, description.name or description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return current state."""
        data = self.coordinator.data or {}
        return bool(data.get(self.entity_description.source_key or self.entity_description.key))
