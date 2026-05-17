"""Anker Prime Charger Home Assistant integration."""

from __future__ import annotations

import importlib
import importlib.util
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from .const import (
    ATTR_DEVICE_SN,
    ATTR_INCLUDE_RAW,
    CONF_COUNTRY,
    CONF_DEBUG_LOGGING,
    CONF_DEVICE_NAME,
    CONF_DEVICE_SN,
    CONF_MQTT_KEEPALIVE,
    CONF_OFFLINE_TIMEOUT,
    CONF_POLLING_FALLBACK,
    CONF_POLLING_INTERVAL,
    CONF_REALTIME_REFRESH_INTERVAL,
    CONF_SHOW_UNKNOWN_FIELDS,
    DEFAULT_COUNTRY,
    DEFAULT_DEBUG_LOGGING,
    DEFAULT_MQTT_KEEPALIVE,
    DEFAULT_OFFLINE_TIMEOUT,
    DEFAULT_POLLING_FALLBACK,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_REALTIME_REFRESH_INTERVAL,
    DEFAULT_SHOW_UNKNOWN_FIELDS,
    DOMAIN,
    MANUFACTURER,
    MODEL_A2345,
    NAME,
    PLATFORMS,
    SERVICE_DUMP_LAST_PAYLOAD,
    SERVICE_DUMP_PAYLOAD_HISTORY,
)

if TYPE_CHECKING:
    from .coordinator import AnkerPrimeChargerCoordinator

_LOGGER = logging.getLogger(__name__)

AnkerPrimeConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: AnkerPrimeConfigEntry) -> bool:
    """Set up Anker Prime Charger from a config entry."""
    from .api import AnkerPrimeChargerApi
    from .coordinator import AnkerPrimeChargerCoordinator

    options = _merged_options(entry)
    if options[CONF_DEBUG_LOGGING]:
        _LOGGER.setLevel(logging.DEBUG)

    api = AnkerPrimeChargerApi(
        hass=hass,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        country=entry.data.get(CONF_COUNTRY, DEFAULT_COUNTRY),
    )
    coordinator = AnkerPrimeChargerCoordinator(
        hass=hass,
        entry=entry,
        api=api,
        device_sn=entry.data[CONF_DEVICE_SN],
        device_name=entry.data.get(CONF_DEVICE_NAME) or NAME,
        options=options,
    )
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_start()
    entry.runtime_data = coordinator

    importlib.invalidate_caches()
    await hass.config_entries.async_forward_entry_setups(
        entry, _available_platforms()
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_register_services(hass)
    _register_device(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AnkerPrimeConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = entry.runtime_data
    await coordinator.async_shutdown()
    return await hass.config_entries.async_unload_platforms(
        entry, _available_platforms()
    )


async def _async_update_listener(
    hass: HomeAssistant, entry: AnkerPrimeConfigEntry
) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _merged_options(entry: ConfigEntry) -> dict[str, Any]:
    """Return integration options with defaults applied."""
    return {
        CONF_REALTIME_REFRESH_INTERVAL: entry.options.get(
            CONF_REALTIME_REFRESH_INTERVAL, DEFAULT_REALTIME_REFRESH_INTERVAL
        ),
        CONF_OFFLINE_TIMEOUT: entry.options.get(
            CONF_OFFLINE_TIMEOUT, DEFAULT_OFFLINE_TIMEOUT
        ),
        CONF_MQTT_KEEPALIVE: entry.options.get(
            CONF_MQTT_KEEPALIVE, DEFAULT_MQTT_KEEPALIVE
        ),
        CONF_POLLING_FALLBACK: entry.options.get(
            CONF_POLLING_FALLBACK, DEFAULT_POLLING_FALLBACK
        ),
        CONF_POLLING_INTERVAL: entry.options.get(
            CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
        ),
        CONF_DEBUG_LOGGING: entry.options.get(
            CONF_DEBUG_LOGGING, DEFAULT_DEBUG_LOGGING
        ),
        CONF_SHOW_UNKNOWN_FIELDS: entry.options.get(
            CONF_SHOW_UNKNOWN_FIELDS, DEFAULT_SHOW_UNKNOWN_FIELDS
        ),
    }


def _available_platforms() -> list[Platform]:
    """Return platforms with importable modules."""
    platforms: list[Platform] = []
    for platform in PLATFORMS:
        module_name = f"{__package__}.{platform}"
        if importlib.util.find_spec(module_name) is None:
            _LOGGER.error("Platform module %s is missing, skipping setup", module_name)
            continue
        platforms.append(Platform(platform))
    return platforms


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    async def dump_last_payload(call: ServiceCall) -> None:
        device_sn = call.data.get(ATTR_DEVICE_SN)
        include_raw = bool(call.data.get(ATTR_INCLUDE_RAW))
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator = getattr(entry, "runtime_data", None)
            if not coordinator:
                continue
            if device_sn and coordinator.device_sn != device_sn:
                continue
            await coordinator.async_dump_last_payload(include_raw=include_raw)

    async def dump_payload_history(call: ServiceCall) -> None:
        device_sn = call.data.get(ATTR_DEVICE_SN)
        include_raw = bool(call.data.get(ATTR_INCLUDE_RAW))
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator = getattr(entry, "runtime_data", None)
            if not coordinator:
                continue
            if device_sn and coordinator.device_sn != device_sn:
                continue
            await coordinator.async_dump_payload_history(include_raw=include_raw)

    if not hass.services.has_service(DOMAIN, SERVICE_DUMP_LAST_PAYLOAD):
        hass.services.async_register(
            DOMAIN, SERVICE_DUMP_LAST_PAYLOAD, dump_last_payload
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DUMP_PAYLOAD_HISTORY):
        hass.services.async_register(
            DOMAIN, SERVICE_DUMP_PAYLOAD_HISTORY, dump_payload_history
        )


def _register_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create the device registry entry early."""
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_DEVICE_SN])},
        manufacturer=MANUFACTURER,
        model=MODEL_A2345,
        name=entry.data.get(CONF_DEVICE_NAME) or NAME,
        serial_number=entry.data[CONF_DEVICE_SN],
    )
