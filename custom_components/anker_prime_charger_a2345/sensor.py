"""Sensors for Anker Prime Charger A2345."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SHOW_UNKNOWN_FIELDS
from .coordinator import AnkerPrimeChargerCoordinator
from .entity import AnkerPrimeChargerEntity


@dataclass(frozen=True, kw_only=True)
class PrimeSensorDescription(SensorEntityDescription):
    """Describe one Prime Charger sensor."""

    source_key: str | None = None


STATIC_SENSORS: tuple[PrimeSensorDescription, ...] = (
    PrimeSensorDescription(
        key="total_power",
        name="Total power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PrimeSensorDescription(key="last_seen", name="Last seen", device_class=SensorDeviceClass.TIMESTAMP),
    PrimeSensorDescription(key="last_payload_time", name="Last payload time", device_class=SensorDeviceClass.TIMESTAMP),
    PrimeSensorDescription(key="firmware_version", name="Firmware version"),
    PrimeSensorDescription(key="device_information", name="Geräteinformationen"),
    PrimeSensorDescription(key="realtime_status", name="Realtime status"),
    PrimeSensorDescription(
        key="mqtt_reconnect_count",
        name="MQTT reconnect count",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    PrimeSensorDescription(
        key="mqtt_recovery_count",
        name="MQTT recovery count",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    PrimeSensorDescription(key="mqtt_last_error", name="MQTT last error"),
    PrimeSensorDescription(
        key="last_realtime_trigger",
        name="Last realtime trigger",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    PrimeSensorDescription(
        key="last_status_request",
        name="Last status request",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    PrimeSensorDescription(
        key="unknown_payload_field_count",
        name="Unknown payload field count",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PrimeSensorDescription(key="unknown_payload_fields", name="Unknown payload fields"),
)

PORTS = ("usbc_1", "usbc_2", "usbc_3", "usbc_4", "usba_1", "usba_2")
PORT_STATUS_MAP = {
    0: "inactive",
    1: "active",
    2: "charging",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator: AnkerPrimeChargerCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        AnkerPrimeChargerSensor(coordinator, description)
        for description in STATIC_SENSORS
    ]
    for port in PORTS:
        label = port.upper().replace("_", "-")
        entities.extend(
            [
                AnkerPrimeChargerSensor(
                    coordinator,
                    PrimeSensorDescription(
                        key=f"{port}_power",
                        name=f"{label} power",
                        native_unit_of_measurement=UnitOfPower.WATT,
                        device_class=SensorDeviceClass.POWER,
                        state_class=SensorStateClass.MEASUREMENT,
                    ),
                ),
                AnkerPrimeChargerSensor(
                    coordinator,
                    PrimeSensorDescription(
                        key=f"{port}_voltage",
                        name=f"{label} voltage",
                        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
                        device_class=SensorDeviceClass.VOLTAGE,
                        state_class=SensorStateClass.MEASUREMENT,
                    ),
                ),
                AnkerPrimeChargerSensor(
                    coordinator,
                    PrimeSensorDescription(
                        key=f"{port}_current",
                        name=f"{label} current",
                        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                        device_class=SensorDeviceClass.CURRENT,
                        state_class=SensorStateClass.MEASUREMENT,
                    ),
                ),
                AnkerPrimeChargerSensor(
                    coordinator,
                    PrimeSensorDescription(
                        key=f"{port}_status",
                        name=f"{label} status",
                    ),
                ),
                AnkerPrimeChargerSensor(
                    coordinator,
                    PrimeSensorDescription(
                        key=f"{port}_device_information",
                        name=f"{label} device information",
                    ),
                ),
            ]
        )

    if entry.options.get(CONF_SHOW_UNKNOWN_FIELDS):
        known = {entity.entity_description.key for entity in entities}
        debug_keys = set(coordinator.data or {})
        unknown_fields = (coordinator.data or {}).get("unknown_payload_fields")
        if isinstance(unknown_fields, str):
            debug_keys.update(
                f"unknown_{key.strip()}"
                for key in unknown_fields.split(",")
                if key.strip()
            )
        for key in sorted(debug_keys - known):
            if key.startswith("unknown_"):
                entities.append(
                    AnkerPrimeChargerSensor(
                        coordinator,
                        PrimeSensorDescription(
                            key=key,
                            name=key.replace("_", " "),
                        ),
                    )
                )

    async_add_entities(entities)


class AnkerPrimeChargerSensor(AnkerPrimeChargerEntity, SensorEntity):
    """A2345 sensor entity."""

    entity_description: PrimeSensorDescription

    def __init__(
        self,
        coordinator: AnkerPrimeChargerCoordinator,
        description: PrimeSensorDescription,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, description.key, description.name or description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return sensor value."""
        data = self.coordinator.data or {}
        value = data.get(self.entity_description.source_key or self.entity_description.key)
        if self.entity_description.key.endswith("_status"):
            return PORT_STATUS_MAP.get(value, value)
        return value
