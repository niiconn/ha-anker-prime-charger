"""Diagnostics for Anker Prime Charger."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {
    "email",
    "password",
    "auth_token",
    "gtoken",
    "private_key",
    "certificate_pem",
    "aws_root_ca1_pem",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with secrets redacted."""
    coordinator = entry.runtime_data
    data = dict(coordinator.data or {})
    payload = coordinator.mqtt.last_payload if coordinator.mqtt else None
    if isinstance(payload, dict):
        payload = {key: value for key, value in payload.items() if key != "message"}
    mqtt_info = {}
    if coordinator.mqtt:
        mqtt_info = {
            "connected": coordinator.mqtt.connected,
            "reconnect_count": coordinator.mqtt.reconnect_count,
            "recovery_count": coordinator.mqtt.recovery_count,
            "realtime_status": coordinator.mqtt.realtime_status,
            "last_realtime_trigger": coordinator.mqtt.last_realtime_trigger,
            "last_status_request": coordinator.mqtt.last_status_request,
            "last_error": coordinator.mqtt.last_error,
            "payload_history_size": len(coordinator.mqtt.payload_history),
            "subscriptions": sorted(
                coordinator.mqtt.session.subscriptions
                if coordinator.mqtt.session
                else []
            ),
        }
    return {
        "domain": DOMAIN,
        "entry": {key: _redact(key, value) for key, value in entry.data.items()},
        "options": dict(entry.options),
        "device_sn": coordinator.device_sn,
        "device": _redact_nested(coordinator.device),
        "mqtt": mqtt_info,
        "data": {key: _redact(key, value) for key, value in data.items()},
        "last_payload": payload,
    }


def _redact(key: str, value: Any) -> Any:
    """Redact sensitive values."""
    if key in TO_REDACT:
        return "**REDACTED**"
    return value


def _redact_nested(value: Any) -> Any:
    """Redact nested diagnostic structures."""
    if isinstance(value, dict):
        return {key: _redact(key, _redact_nested(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_nested(item) for item in value]
    return value
