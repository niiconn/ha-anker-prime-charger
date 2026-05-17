"""Config flow for Anker Prime Charger."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from .const import (
    CONF_COUNTRY,
    CONF_DEBUG_LOGGING,
    CONF_DEVICE_NAME,
    CONF_DEVICE_SN,
    CONF_MANUAL_DEVICE,
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
    MAX_OFFLINE_TIMEOUT,
    MAX_REALTIME_REFRESH_INTERVAL,
    MIN_OFFLINE_TIMEOUT,
    MIN_REALTIME_REFRESH_INTERVAL,
    NAME,
)
from .solixapi.apitypes import API_COUNTRIES

_LOGGER = logging.getLogger(__name__)


class AnkerPrimeChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Anker Prime Charger config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._user_input: dict[str, Any] = {}
        self._devices: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect Anker credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._user_input = dict(user_input)
            try:
                self._devices = await self._async_discover_devices(user_input)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("A2345 login/discovery failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                if not self._devices:
                    return await self.async_step_manual()
                elif len(self._devices) == 1:
                    return await self._async_create_entry(self._devices[0])
                else:
                    return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_COUNTRY, default=self._default_country()): str,
                }
            ),
            errors=errors,
        )

    async def _async_discover_devices(self, user_input: dict[str, Any]) -> list[dict[str, Any]]:
        """Discover devices and retry once with an alternate API region."""
        from .api import AnkerPrimeChargerApi

        requested_country = str(user_input.get(CONF_COUNTRY) or self._default_country()).upper()
        countries = [requested_country]
        for fallback in self._fallback_countries(requested_country):
            if fallback not in countries:
                countries.append(fallback)

        last_error: Exception | None = None
        for idx, country in enumerate(countries):
            api = AnkerPrimeChargerApi(
                hass=self.hass,
                email=user_input[CONF_EMAIL],
                password=user_input[CONF_PASSWORD],
                country=country,
            )
            try:
                devices = await api.async_get_devices(restart_login=True)
            except Exception as err:  # noqa: BLE001
                last_error = err
                _LOGGER.debug("A2345 discovery failed for country %s: %s", country, err)
                continue
            if devices:
                self._user_input[CONF_COUNTRY] = country
                if idx:
                    _LOGGER.info(
                        "A2345 discovery succeeded with fallback country/region %s",
                        country,
                    )
                return devices
        if last_error:
            _LOGGER.debug("A2345 discovery exhausted region fallbacks: %s", last_error)
        self._user_input[CONF_COUNTRY] = requested_country
        return []

    def _default_country(self) -> str:
        """Return HA country as default when available."""
        country = getattr(self.hass.config, "country", None)
        return str(country or DEFAULT_COUNTRY).upper()

    def _fallback_countries(self, country: str) -> list[str]:
        """Return conservative API-region fallback countries."""
        country = country.upper()
        if country in API_COUNTRIES.get("com", []):
            return [self._default_country(), "CH", "DE"]
        if country in API_COUNTRIES.get("eu", []):
            return ["US"]
        return [self._default_country(), "CH", "US"]

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Let the user choose one A2345 when multiple exist."""
        if user_input is not None:
            selected_sn = user_input[CONF_DEVICE_SN]
            device = next(
                device
                for device in self._devices
                if device["device_sn"] == selected_sn
            )
            return await self._async_create_entry(device)

        choices = {
            device["device_sn"]: f"{device.get('device_name') or NAME} ({device['device_sn']})"
            for device in self._devices
        }
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_SN): vol.In(choices)}),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Allow manual A2345 serial entry when cloud discovery is incomplete."""
        errors: dict[str, str] = {}
        if user_input is not None:
            device_sn = str(user_input[CONF_DEVICE_SN]).strip()
            if not device_sn:
                errors[CONF_DEVICE_SN] = "required"
            else:
                from .api import AnkerPrimeChargerApi

                api = AnkerPrimeChargerApi(
                    hass=self.hass,
                    email=self._user_input[CONF_EMAIL],
                    password=self._user_input[CONF_PASSWORD],
                    country=self._user_input.get(CONF_COUNTRY, DEFAULT_COUNTRY),
                )
                try:
                    await api.async_login(restart=True)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("A2345 manual setup login failed: %s", err)
                    errors["base"] = "cannot_connect"
                    return self.async_show_form(
                        step_id="manual",
                        data_schema=self._manual_schema(),
                        errors=errors,
                    )
                device = api.build_manual_device(
                    device_sn=device_sn,
                    name=user_input.get(CONF_DEVICE_NAME) or NAME,
                )
                return await self._async_create_entry(device)

        return self.async_show_form(
            step_id="manual",
            data_schema=self._manual_schema(),
            errors=errors,
        )

    def _manual_schema(self) -> vol.Schema:
        """Return manual entry schema."""
        return vol.Schema(
            {
                vol.Required(CONF_DEVICE_SN): str,
                vol.Optional(CONF_DEVICE_NAME, default=NAME): str,
            }
        )

    async def _async_create_entry(
        self, device: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Create config entry for one charger."""
        await self.async_set_unique_id(device["device_sn"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=device.get("device_name") or NAME,
            data={
                CONF_EMAIL: self._user_input[CONF_EMAIL],
                CONF_PASSWORD: self._user_input[CONF_PASSWORD],
                CONF_COUNTRY: self._user_input.get(CONF_COUNTRY, DEFAULT_COUNTRY),
                CONF_DEVICE_SN: device["device_sn"],
                CONF_DEVICE_NAME: device.get("device_name") or NAME,
                CONF_MANUAL_DEVICE: bool((device.get("raw") or {}).get("manual")),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> AnkerPrimeChargerOptionsFlow:
        """Return options flow."""
        return AnkerPrimeChargerOptionsFlow(config_entry)


class AnkerPrimeChargerOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Anker Prime Charger."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_REALTIME_REFRESH_INTERVAL,
                        default=options.get(
                            CONF_REALTIME_REFRESH_INTERVAL,
                            DEFAULT_REALTIME_REFRESH_INTERVAL,
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_REALTIME_REFRESH_INTERVAL,
                            max=MAX_REALTIME_REFRESH_INTERVAL,
                        ),
                    ),
                    vol.Required(
                        CONF_OFFLINE_TIMEOUT,
                        default=options.get(
                            CONF_OFFLINE_TIMEOUT, DEFAULT_OFFLINE_TIMEOUT
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_OFFLINE_TIMEOUT, max=MAX_OFFLINE_TIMEOUT),
                    ),
                    vol.Required(
                        CONF_MQTT_KEEPALIVE,
                        default=options.get(CONF_MQTT_KEEPALIVE, DEFAULT_MQTT_KEEPALIVE),
                    ): vol.All(vol.Coerce(int), vol.Range(min=30, max=300)),
                    vol.Required(
                        CONF_POLLING_FALLBACK,
                        default=options.get(
                            CONF_POLLING_FALLBACK, DEFAULT_POLLING_FALLBACK
                        ),
                    ): bool,
                    vol.Required(
                        CONF_POLLING_INTERVAL,
                        default=options.get(
                            CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=120, max=1800)),
                    vol.Required(
                        CONF_DEBUG_LOGGING,
                        default=options.get(CONF_DEBUG_LOGGING, DEFAULT_DEBUG_LOGGING),
                    ): bool,
                    vol.Required(
                        CONF_SHOW_UNKNOWN_FIELDS,
                        default=options.get(
                            CONF_SHOW_UNKNOWN_FIELDS, DEFAULT_SHOW_UNKNOWN_FIELDS
                        ),
                    ): bool,
                }
            ),
        )
