"""Base entity helpers for Anker Prime Charger."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_A2345
from .coordinator import AnkerPrimeChargerCoordinator


class AnkerPrimeChargerEntity(CoordinatorEntity[AnkerPrimeChargerCoordinator]):
    """Base entity for A2345 entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AnkerPrimeChargerCoordinator,
        key: str,
        name: str,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self.key = key
        self._attr_translation_key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.device_sn}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_sn)},
            manufacturer=MANUFACTURER,
            model=MODEL_A2345,
            name=self.coordinator.device_name,
            serial_number=self.coordinator.device_sn,
            sw_version=self.coordinator.data.get("firmware_version")
            if self.coordinator.data
            else None,
        )

    @property
    def available(self) -> bool:
        """Keep entities available through short cloud/MQTT gaps."""
        if self.key in {"online", "mqtt_connected", "mqtt_reconnect_count"}:
            return True
        return bool((self.coordinator.data or {}).get("online"))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return basic debug attributes."""
        data = self.coordinator.data or {}
        return {
            "device_sn": self.coordinator.device_sn,
            "realtime_status": data.get("realtime_status"),
        }
