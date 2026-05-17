"""Data coordinator for Anker Prime Charger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AnkerPrimeChargerApi
from .const import (
    CONF_DEBUG_LOGGING,
    CONF_DEVICE_NAME,
    CONF_DEVICE_SN,
    CONF_MANUAL_DEVICE,
    CONF_SHOW_UNKNOWN_FIELDS,
    CONF_MQTT_KEEPALIVE,
    CONF_OFFLINE_TIMEOUT,
    CONF_POLLING_FALLBACK,
    CONF_POLLING_INTERVAL,
    CONF_REALTIME_REFRESH_INTERVAL,
    DOMAIN,
    NAME,
)
from .mqtt import PrimeChargerMqttManager

_LOGGER = logging.getLogger(__name__)

KNOWN_PAYLOAD_KEYS = {
    "device_name",
    "device_sn",
    "firmware_version",
    "last_cloud_poll",
    "last_payload_time",
    "last_realtime_trigger",
    "last_seen",
    "last_status_request",
    "model",
    "mqtt_connected",
    "mqtt_last_error",
    "mqtt_reconnect_count",
    "mqtt_recovery_count",
    "online",
    "realtime_status",
    "sw_version",
    "temperature",
    "total_power",
    "total_output",
    "device_information",
    "wifi_rssi",
    "rssi",
    "wifi_signal",
    "wireless_signal",
}
for _port in ("usbc_1", "usbc_2", "usbc_3", "usbc_4", "usba_1", "usba_2", "ac_1", "ac_2"):
    KNOWN_PAYLOAD_KEYS.update(
        {
            f"{_port}_current",
            f"{_port}_power",
            f"{_port}_protocol",
            f"{_port}_status",
            f"{_port}_switch",
            f"{_port}_voltage",
            f"{_port}_device_information",
        }
    )
KNOWN_PAYLOAD_KEYS.update({"usba_switch", "msg_timestamp", "topics", "last_message"})


class AnkerPrimeChargerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator fed by MQTT push data with cloud polling fallback."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: AnkerPrimeChargerApi,
        device_sn: str,
        device_name: str,
        options: dict[str, Any],
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{NAME} {device_sn}",
            update_interval=None,
        )
        self.entry = entry
        self.api = api
        self.device_sn = device_sn
        self.device_name = device_name
        self.options = options
        self.device: dict[str, Any] = {}
        self.mqtt: PrimeChargerMqttManager | None = None
        self._last_poll: datetime | None = None
        self._unsub_timers: list[Callable[[], None]] = []
        self._pending_switch_states: dict[str, tuple[int, datetime]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Initial setup refresh and later manual fallback refresh."""
        try:
            if self.entry.data.get(CONF_MANUAL_DEVICE):
                await self.api.async_login(restart=True)
                self.device = self.api.build_manual_device(
                    device_sn=self.entry.data[CONF_DEVICE_SN],
                    name=self.entry.data.get(CONF_DEVICE_NAME) or self.device_name,
                )
                self.api.devices[self.device_sn] = self.device
            else:
                devices = await self.api.async_get_devices(restart_login=True)
                self.device = next(
                    (device for device in devices if device["device_sn"] == self.device_sn),
                    {},
                )
                if not self.device:
                    self.device = self.api.build_manual_device(
                        device_sn=self.entry.data[CONF_DEVICE_SN],
                        name=self.entry.data.get(CONF_DEVICE_NAME) or self.device_name,
                    )
                    self.api.devices[self.device_sn] = self.device
            if not self.device:
                raise UpdateFailed(f"A2345 device {self.device_sn} not found")
            data = dict(self.data or {})
            data.update(
                {
                    "device_sn": self.device_sn,
                    "device_name": self.device_name,
                    "model": self.device.get("device_pn"),
                    "firmware_version": self.device.get("main_version"),
                    "mqtt_connected": False,
                    "mqtt_reconnect_count": 0,
                    "realtime_status": "starting",
                }
            )
            return self._augment_data(data)
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(str(err)) from err

    async def async_start(self) -> None:
        """Start MQTT manager after the first refresh."""
        if self.mqtt:
            return
        self.mqtt = PrimeChargerMqttManager(
            api=self.api,
            device=self.device,
            on_update=self._handle_mqtt_update,
            realtime_interval=int(self.options[CONF_REALTIME_REFRESH_INTERVAL]),
            keepalive=int(self.options[CONF_MQTT_KEEPALIVE]),
            stale_after=min(90, int(self.options[CONF_OFFLINE_TIMEOUT]) // 2),
            debug_logging=bool(self.options[CONF_DEBUG_LOGGING]),
        )
        await self.mqtt.async_start()
        self._unsub_timers.append(
            async_track_time_interval(
                self.hass,
                self._async_refresh_availability,
                timedelta(seconds=30),
            )
        )
        if self.options[CONF_POLLING_FALLBACK]:
            self._unsub_timers.append(
                async_track_time_interval(
                    self.hass,
                    self._async_poll_fallback,
                    timedelta(seconds=int(self.options[CONF_POLLING_INTERVAL])),
                )
            )
        self._unsub_timers.append(
            async_track_time_interval(
                self.hass,
                self._async_refresh_device_information,
                timedelta(minutes=5),
            )
        )
        self._unsub_timers.append(
            async_track_time_interval(
                self.hass,
                self._async_status_refresh,
                timedelta(seconds=60),
            )
        )
        await self._async_refresh_device_information(None)

    async def async_shutdown(self) -> None:
        """Stop runtime resources."""
        while self._unsub_timers:
            self._unsub_timers.pop()()
        if self.mqtt:
            await self.mqtt.async_stop()
            self.mqtt = None

    def _handle_mqtt_update(self, values: dict[str, Any]) -> None:
        """Merge MQTT values and notify entities from the HA loop."""
        self.hass.loop.call_soon_threadsafe(self._async_apply_mqtt_update, values)

    def _async_apply_mqtt_update(self, values: dict[str, Any]) -> None:
        """Apply an MQTT update in the event loop."""
        data = dict(self.data or {})
        values = self._filter_pending_switch_states(values)
        data.update(values)
        self.async_set_updated_data(self._augment_data(data))

    async def _async_poll_fallback(self, _now: datetime) -> None:
        """Request cloud fallback status when payloads are stale."""
        if self._has_recent_payload():
            return
        self._last_poll = datetime.now(UTC)
        try:
            payload = await self.api.async_status_request(self.device_sn)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("A2345 cloud fallback polling failed: %s", err)
            payload = None
        if payload:
            data = dict(self.data or {})
            data["last_cloud_poll"] = self._last_poll
            if isinstance(payload, dict):
                data.update(_flatten_known(payload))
            self.async_set_updated_data(self._augment_data(data))
        if self.mqtt:
            await self.mqtt.async_status_request()

    async def _async_refresh_device_information(self, _now: datetime | None) -> None:
        """Refresh app-style connected device identity information."""
        try:
            info = await self.api.async_get_connected_device_information(self.device_sn)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("A2345 device information refresh failed: %s", err)
            return
        if not info:
            return
        data = dict(self.data or {})
        data.update(info)
        self.async_set_updated_data(self._augment_data(data))

    async def _async_status_refresh(self, _now: datetime) -> None:
        """Request full status periodically to catch app-side switch changes."""
        if not self.mqtt:
            return
        await self.mqtt.async_status_request()

    async def _async_refresh_availability(self, _now: datetime) -> None:
        """Recompute grace-period availability even when no payload arrives."""
        data = dict(self.data or {})
        if self.mqtt:
            data.update(
                {
                    "mqtt_connected": self.mqtt.connected,
                    "mqtt_reconnect_count": self.mqtt.reconnect_count,
                    "mqtt_recovery_count": self.mqtt.recovery_count,
                    "mqtt_last_error": self.mqtt.last_error,
                    "realtime_status": self.mqtt.realtime_status,
                    "last_realtime_trigger": self.mqtt.last_realtime_trigger,
                    "last_status_request": self.mqtt.last_status_request,
                }
            )
        self.async_set_updated_data(self._augment_data(data))

    async def async_dump_last_payload(self, include_raw: bool = False) -> None:
        """Write the last MQTT payload to Home Assistant storage for diagnostics."""
        if not self.mqtt or not self.mqtt.last_payload:
            _LOGGER.info("No A2345 MQTT payload has been received yet")
            return
        path = Path(self.hass.config.path("anker_prime_charger_a2345_last_payload.json"))
        payload = _prepare_payload_dump(self.mqtt.last_payload, include_raw)
        text = json.dumps(payload, default=str, indent=2)
        await self.hass.async_add_executor_job(path.write_text, text, "utf-8")
        _LOGGER.info("A2345 last MQTT payload dumped to %s", path)

    async def async_dump_payload_history(self, include_raw: bool = False) -> None:
        """Write recent MQTT payload history to Home Assistant storage."""
        if not self.mqtt or not self.mqtt.payload_history:
            _LOGGER.info("No A2345 MQTT payload history has been received yet")
            return
        path = Path(self.hass.config.path("anker_prime_charger_a2345_payload_history.json"))
        history = [
            _prepare_payload_dump(payload, include_raw)
            for payload in self.mqtt.payload_history
        ]
        text = json.dumps(history, default=str, indent=2)
        await self.hass.async_add_executor_job(path.write_text, text, "utf-8")
        _LOGGER.info("A2345 MQTT payload history dumped to %s", path)

    def _has_recent_payload(self) -> bool:
        """Return true if payloads are still inside the offline timeout."""
        last_payload = (self.data or {}).get("last_payload_time")
        if not isinstance(last_payload, datetime):
            return False
        return (
            datetime.now(UTC) - last_payload
        ).total_seconds() < self.options[CONF_OFFLINE_TIMEOUT]

    def _augment_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add derived values used by entities."""
        now = datetime.now(UTC)
        last_seen = data.get("last_seen")
        online = False
        if isinstance(last_seen, datetime):
            online = (
                now - last_seen
            ).total_seconds() <= self.options[CONF_OFFLINE_TIMEOUT]
        data["online"] = online
        data["firmware_version"] = (
            data.get("firmware_version")
            or data.get("sw_version")
            or self.device.get("main_version")
        )
        data["wifi_rssi"] = (
            data.get("wifi_rssi")
            or data.get("rssi")
            or data.get("wifi_signal")
            or data.get("wireless_signal")
        )
        total_output = _sum_number_values(
            data,
            (
                "usbc_1_power",
                "usbc_2_power",
                "usbc_3_power",
                "usbc_4_power",
                "usba_1_power",
                "usba_2_power",
            ),
        )
        data["total_output"] = total_output
        data["total_power"] = total_output
        self._derive_switch_states_from_activity(data)
        unknown = sorted(
            key
            for key, value in data.items()
            if key not in KNOWN_PAYLOAD_KEYS
            and not key.startswith("unknown_")
            and isinstance(value, int | float | str | bool | type(None))
        )
        data["unknown_payload_field_count"] = len(unknown)
        data["unknown_payload_fields"] = ", ".join(unknown)
        if self.options.get(CONF_SHOW_UNKNOWN_FIELDS):
            for key in unknown:
                data[f"unknown_{key}"] = data.get(key)
        return data

    def async_set_port_switch_state(self, key: str, enabled: bool) -> None:
        """Apply a local USB port switch state while waiting for MQTT confirmation."""
        state = 1 if enabled else 0
        data = dict(self.data or {})
        data[key] = state
        self._pending_switch_states[key] = (state, datetime.now(UTC) + timedelta(seconds=45))
        if self.mqtt:
            self.mqtt.last_values[key] = state
        self.async_set_updated_data(self._augment_data(data))

    def _filter_pending_switch_states(self, values: dict[str, Any]) -> dict[str, Any]:
        """Ignore briefly stale switch states after local commands."""
        if not self._pending_switch_states:
            return values
        now = datetime.now(UTC)
        filtered = dict(values)
        for key, (desired, deadline) in list(self._pending_switch_states.items()):
            incoming = filtered.get(key)
            if incoming is None:
                if now >= deadline:
                    self._pending_switch_states.pop(key, None)
                continue
            try:
                incoming_state = int(incoming)
            except (TypeError, ValueError):
                self._pending_switch_states.pop(key, None)
                continue
            if incoming_state == desired or now >= deadline:
                self._pending_switch_states.pop(key, None)
                continue
            filtered.pop(key, None)
        return filtered

    def _derive_switch_states_from_activity(self, data: dict[str, Any]) -> None:
        """Treat externally reactivated ports as enabled when activity is decoded."""
        for port in ("usbc_1", "usbc_2", "usbc_3", "usbc_4"):
            switch_key = f"{port}_switch"
            if self._has_pending_switch_off(switch_key):
                continue
            if _port_has_activity(data, port):
                data[switch_key] = 1
        if self._has_pending_switch_off("usba_switch"):
            return
        if _port_has_activity(data, "usba_1") or _port_has_activity(data, "usba_2"):
            data["usba_switch"] = 1

    def _has_pending_switch_off(self, key: str) -> bool:
        """Return true while a local off command is waiting for confirmation."""
        pending = self._pending_switch_states.get(key)
        if not pending:
            return False
        desired, deadline = pending
        if datetime.now(UTC) >= deadline:
            self._pending_switch_states.pop(key, None)
            return False
        return desired == 0


def _sum_number_values(data: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    """Sum numeric values from decoded MQTT data."""
    values = [data[key] for key in keys if isinstance(data.get(key), int | float)]
    if not values:
        return None
    return round(sum(float(value) for value in values), 2)


def _port_has_activity(data: dict[str, Any], port: str) -> bool:
    """Return true if decoded status or power shows live port activity."""
    status = data.get(f"{port}_status")
    power = data.get(f"{port}_power")
    return (
        isinstance(status, int | float)
        and status > 0
        or isinstance(power, int | float)
        and power > 0
    )


def _flatten_known(value: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten simple values from cloud fallback payloads."""
    output: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            output.update(_flatten_known(child, f"{prefix}{key}_"))
    elif isinstance(value, int | float | str | bool) or value is None:
        output[prefix[:-1]] = value
    return output


def _prepare_payload_dump(payload: dict[str, Any], include_raw: bool) -> dict[str, Any]:
    """Prepare a payload dump with raw envelope excluded unless requested."""
    prepared = dict(payload)
    if not include_raw:
        prepared.pop("message", None)
    return prepared
