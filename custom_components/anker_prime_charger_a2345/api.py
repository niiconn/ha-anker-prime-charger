"""Cloud API adapter for Anker Prime Charger A2345."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import MODEL_A2345
from .solixapi.apitypes import API_ENDPOINTS
from .solixapi.helpers import get_solix_product_code
from .solixapi.session import AnkerSolixClientSession

_LOGGER = logging.getLogger(__name__)


class AnkerPrimeChargerApi:
    """Small A2345-focused adapter around the ha-anker-solix cloud session."""

    def __init__(
        self, hass: HomeAssistant, email: str, password: str, country: str
    ) -> None:
        """Initialize the API wrapper."""
        self.hass = hass
        self.session = AnkerSolixClientSession(
            email=email,
            password=password,
            countryId=country,
            websession=async_get_clientsession(hass),
            logger=_LOGGER,
        )
        self.devices: dict[str, dict[str, Any]] = {}
        self.authorization_errors = 0

    async def async_login(self, restart: bool = False) -> None:
        """Authenticate against Anker Cloud."""
        if not await self.session.async_authenticate(restart=restart):
            raise RuntimeError("Anker authentication failed")

    async def async_get_devices(self, restart_login: bool = False) -> list[dict[str, Any]]:
        """Return compatible A2345 devices found in Anker Cloud data."""
        await self.async_login(restart=restart_login)
        candidates: dict[str, dict[str, Any]] = {}
        endpoint_counts: dict[str, int] = {}
        self.authorization_errors = 0

        for endpoint in (
            "bind_devices",
            "user_devices",
            "charging_devices",
            "homepage",
            "get_auto_upgrade",
        ):
            try:
                response = await self.session.request(
                    "post", API_ENDPOINTS[endpoint]
                )
            except Exception as err:  # noqa: BLE001
                if _is_authorization_error(err):
                    self.authorization_errors += 1
                _LOGGER.debug("A2345 discovery endpoint %s failed: %s", endpoint, err)
                continue
            devices = _walk_devices(response.get("data") or {})
            endpoint_counts[endpoint] = len(devices)
            for device in devices:
                normalized = self._normalize_device(device)
                if normalized:
                    candidates[normalized["device_sn"]] = normalized
        await self._async_discover_site_devices(candidates, endpoint_counts)
        if self.authorization_errors and not candidates:
            raise RuntimeError(
                f"Anker API authorization failed on {self.authorization_errors} discovery endpoint(s)"
            )

        self.devices = candidates
        _LOGGER.info(
            "A2345 discovery finished: %s compatible device(s), scanned candidates by endpoint: %s",
            len(candidates),
            endpoint_counts,
        )
        return list(candidates.values())

    async def _async_discover_site_devices(
        self,
        candidates: dict[str, dict[str, Any]],
        endpoint_counts: dict[str, int],
    ) -> None:
        """Discover devices through site list and scene info."""
        try:
            response = await self.session.request("post", API_ENDPOINTS["site_list"])
        except Exception as err:  # noqa: BLE001
            if _is_authorization_error(err):
                self.authorization_errors += 1
            _LOGGER.debug("A2345 discovery endpoint site_list failed: %s", err)
            return
        sites = (response.get("data") or {}).get("site_list") or []
        endpoint_counts["site_list"] = len(sites)
        for site in sites:
            site_id = site.get("site_id")
            for device in _walk_devices(site):
                normalized = self._normalize_device(device)
                if normalized:
                    candidates[normalized["device_sn"]] = normalized
            if not site_id:
                continue
            for endpoint, payload in (
                ("scene_info", {"site_id": site_id}),
                ("site_detail", {"site_id": site_id}),
            ):
                try:
                    detail = await self.session.request(
                        "post", API_ENDPOINTS[endpoint], json=payload
                    )
                except Exception as err:  # noqa: BLE001
                    if _is_authorization_error(err):
                        self.authorization_errors += 1
                    _LOGGER.debug(
                        "A2345 discovery endpoint %s for site %s failed: %s",
                        endpoint,
                        site_id,
                        err,
                    )
                    continue
                devices = _walk_devices(detail.get("data") or {})
                endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + len(
                    devices
                )
                for device in devices:
                    normalized = self._normalize_device(device)
                    if normalized:
                        candidates[normalized["device_sn"]] = normalized

    async def async_status_request(self, device_sn: str) -> dict[str, Any] | None:
        """Run a lightweight cloud fallback request if the endpoint is available."""
        device = self.devices.get(device_sn, {})
        payload = {"device_sn": device_sn, "device_model": MODEL_A2345}
        if product_code := device.get("device_pn"):
            payload["product_code"] = product_code
        try:
            return (
                await self.session.request(
                    "post",
                    API_ENDPOINTS["charger_get_device_setting"],
                    json=payload,
                )
            ).get("data")
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("A2345 fallback status request failed: %s", err)
            return None

    async def async_get_connected_device_information(
        self, device_sn: str
    ) -> dict[str, Any]:
        """Fetch app-style connected device identity information when available."""
        payloads = (
            {
                "device_sn": device_sn,
                "device_model": MODEL_A2345,
                "product_code": MODEL_A2345,
            },
            {"device_sn": device_sn},
        )
        endpoints = (
            "charger_get_device_identity_status",
            "charger_get_device_identity_default_status",
        )
        collected: dict[str, Any] = {}
        for endpoint in endpoints:
            for payload in payloads:
                try:
                    response = await self.session.request(
                        "post",
                        API_ENDPOINTS[endpoint],
                        json=payload,
                    )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug(
                        "A2345 device information endpoint %s failed: %s",
                        endpoint,
                        err,
                    )
                    continue
                data = response.get("data")
                if data:
                    collected[endpoint] = data
                    break
        return _extract_connected_device_information(collected)

    def _normalize_device(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize one cloud device object and keep only A2345."""
        if not isinstance(raw, dict):
            return None
        device_sn = str(raw.get("device_sn") or raw.get("sn") or "")
        if not device_sn:
            return None
        pn = str(
            raw.get("device_pn")
            or raw.get("product_code")
            or raw.get("device_model")
            or get_solix_product_code(device_sn)
            or ""
        )
        if pn != MODEL_A2345:
            return None
        return {
            "device_sn": device_sn,
            "device_pn": MODEL_A2345,
            "product_code": MODEL_A2345,
            "device_name": raw.get("device_name")
            or raw.get("alias_name")
            or "Anker Prime Charger (A2345)",
            "alias_name": raw.get("alias_name"),
            "device_img": raw.get("device_img") or raw.get("img_url"),
            "main_version": raw.get("main_version") or raw.get("sw_version"),
            "is_admin": raw.get("is_admin", True),
            "mqtt_supported": True,
            "raw": raw,
        }

    def build_manual_device(self, device_sn: str, name: str | None = None) -> dict[str, Any]:
        """Build an A2345 device entry from a manually supplied serial number."""
        return {
            "device_sn": device_sn,
            "device_pn": MODEL_A2345,
            "product_code": MODEL_A2345,
            "device_name": name or "Anker Prime Charger (A2345)",
            "alias_name": name,
            "device_img": None,
            "main_version": None,
            "is_admin": True,
            "mqtt_supported": True,
            "raw": {"manual": True, "device_sn": device_sn, "product_code": MODEL_A2345},
        }


def _walk_devices(value: Any) -> list[dict[str, Any]]:
    """Extract device-shaped dictionaries from nested Anker responses."""
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("device_sn") or value.get("sn"):
            found.append(value)
        for child in value.values():
            found.extend(_walk_devices(child))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_devices(item))
    return found


def _is_authorization_error(err: Exception) -> bool:
    """Return true for Anker auth/token failures."""
    text = str(err).lower()
    return "401" in text or "403" in text or "unauthorized" in text or "token" in text


PORT_ALIASES = {
    "0": "usbc_1",
    "1": "usbc_2",
    "2": "usbc_3",
    "3": "usbc_4",
    "4": "usba",
    "5": "usba_1",
    "6": "usba_2",
    "c1": "usbc_1",
    "c2": "usbc_2",
    "c3": "usbc_3",
    "c4": "usbc_4",
    "usb_c_1": "usbc_1",
    "usb_c_2": "usbc_2",
    "usb_c_3": "usbc_3",
    "usb_c_4": "usbc_4",
    "usbc1": "usbc_1",
    "usbc2": "usbc_2",
    "usbc3": "usbc_3",
    "usbc4": "usbc_4",
    "usba": "usba",
    "usb_a": "usba",
    "usb_a_1": "usba_1",
    "usb_a_2": "usba_2",
    "usba1": "usba_1",
    "usba2": "usba_2",
}

DEVICE_NAME_KEYS = (
    "charging_device_name",
    "device_name",
    "device_model",
    "display_name",
    "identify_name",
    "identity_name",
    "model",
    "product_name",
    "model_name",
    "name",
    "remark",
    "title",
)
PORT_KEYS = (
    "port",
    "port_id",
    "port_index",
    "port_no",
    "port_num",
    "port_type",
    "usb_type",
)


def _extract_connected_device_information(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract human readable connected-device names from unknown API shapes."""
    port_devices: dict[str, str] = {}
    loose_names: list[str] = []
    for item in _walk_dicts(payload):
        name = _first_string(item, DEVICE_NAME_KEYS)
        if not name:
            continue
        port = _normalize_port(_first_value(item, PORT_KEYS))
        if port:
            port_devices[port] = name
        elif name not in loose_names:
            loose_names.append(name)

    summary_parts = [
        f"{_format_port_name(port)}: {name}"
        for port, name in sorted(port_devices.items())
        if name
    ]
    summary_parts.extend(name for name in loose_names if name not in port_devices.values())
    result: dict[str, Any] = {"device_information": ", ".join(summary_parts) or None}
    for port, name in port_devices.items():
        result[f"{port}_device_information"] = name
    return result


def _walk_dicts(value: Any) -> list[dict[str, Any]]:
    """Return all dictionaries contained in a nested response."""
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(_walk_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_dicts(child))
    return found


def _first_string(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty string value for any key suffix."""
    for key, value in item.items():
        lowered = str(key).lower()
        if any(lowered == wanted or lowered.endswith(f"_{wanted}") for wanted in keys):
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _first_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first value matching a likely port key."""
    for key, value in item.items():
        lowered = str(key).lower()
        if any(lowered == wanted or lowered.endswith(f"_{wanted}") for wanted in keys):
            return value
    return None


def _normalize_port(value: Any) -> str | None:
    """Normalize API port hints to integration port keys."""
    if value is None:
        return None
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return PORT_ALIASES.get(key)


def _format_port_name(port: str) -> str:
    """Return a compact user-facing port label."""
    return port.upper().replace("_", "-")
