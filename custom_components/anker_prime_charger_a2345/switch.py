"""Switches for Anker Prime Charger A2345."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AnkerPrimeChargerCoordinator
from .entity import AnkerPrimeChargerEntity
from .solixapi.mqttcmdmap import SolixMqttCommands


@dataclass(frozen=True, kw_only=True)
class PrimeSwitchDescription(SwitchEntityDescription):
    """Describe one A2345 switch."""

    command: str
    state_key: str
    port_select: int


SWITCHES: tuple[PrimeSwitchDescription, ...] = (
    PrimeSwitchDescription(
        key="usbc_1_switch",
        name="USB-C 1",
        command=SolixMqttCommands.usbc_1_port_switch,
        state_key="usbc_1_switch",
        port_select=0,
    ),
    PrimeSwitchDescription(
        key="usbc_2_switch",
        name="USB-C 2",
        command=SolixMqttCommands.usbc_2_port_switch,
        state_key="usbc_2_switch",
        port_select=1,
    ),
    PrimeSwitchDescription(
        key="usbc_3_switch",
        name="USB-C 3",
        command=SolixMqttCommands.usbc_3_port_switch,
        state_key="usbc_3_switch",
        port_select=2,
    ),
    PrimeSwitchDescription(
        key="usbc_4_switch",
        name="USB-C 4",
        command=SolixMqttCommands.usbc_4_port_switch,
        state_key="usbc_4_switch",
        port_select=3,
    ),
    PrimeSwitchDescription(
        key="usba_switch",
        name="USB-A ports",
        command=SolixMqttCommands.usba_port_switch,
        state_key="usba_switch",
        port_select=4,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator: AnkerPrimeChargerCoordinator = entry.runtime_data
    async_add_entities(
        AnkerPrimeChargerSwitch(coordinator, description) for description in SWITCHES
    )


class AnkerPrimeChargerSwitch(AnkerPrimeChargerEntity, SwitchEntity):
    """A2345 safe known MQTT command switch."""

    entity_description: PrimeSwitchDescription

    def __init__(
        self,
        coordinator: AnkerPrimeChargerCoordinator,
        description: PrimeSwitchDescription,
    ) -> None:
        """Initialize switch."""
        super().__init__(coordinator, description.key, description.name or description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return switch state."""
        value = (self.coordinator.data or {}).get(self.entity_description.state_key)
        if value is None:
            return None
        return bool(value)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on switch."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off switch."""
        await self._async_set(False)

    async def _async_set(self, enabled: bool) -> None:
        """Send known A2345 MQTT switch command."""
        if not self.coordinator.mqtt or not self.coordinator.mqtt.session:
            return
        self.coordinator.async_set_port_switch_state(
            self.entity_description.state_key,
            enabled,
        )
        await self._async_publish_switch_command(enabled)
        await asyncio.sleep(1.5)
        await self._async_publish_switch_command(enabled)
        if self.coordinator.mqtt:
            await self.coordinator.mqtt.async_trigger_realtime()
            await asyncio.sleep(2)
            await self.coordinator.mqtt.async_status_request()

    async def _async_publish_switch_command(self, enabled: bool) -> None:
        """Publish one A2345 USB port switch command."""
        if not self.coordinator.mqtt or not self.coordinator.mqtt.session:
            return
        session = self.coordinator.mqtt.session
        hexdata = session.get_command_data(
            command=self.entity_description.command,
            parameters={
                "set_port_switch_select": self.entity_description.port_select,
                "set_port_switch": 1 if enabled else 0,
            },
            model=self.coordinator.device.get("device_pn", "A2345"),
        )
        if not hexdata:
            return
        _message, response = session.publish(self.coordinator.device, hexdata)
        await self.hass.async_add_executor_job(response.wait_for_publish, 5)
