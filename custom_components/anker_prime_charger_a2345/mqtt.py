"""Robust MQTT/realtime handling for Anker Prime Charger A2345."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
import logging
from typing import Any

from .api import AnkerPrimeChargerApi
from .const import MODEL_A2345
from .solixapi.mqtt import AnkerSolixMqttSession

_LOGGER = logging.getLogger(__name__)

MqttUpdateCallback = Callable[[dict[str, Any]], None]


class PrimeChargerMqttManager:
    """Own the AWS IoT MQTT session and A2345 realtime recovery loop."""

    def __init__(
        self,
        api: AnkerPrimeChargerApi,
        device: dict[str, Any],
        on_update: MqttUpdateCallback,
        realtime_interval: int,
        keepalive: int,
        stale_after: int,
        debug_logging: bool,
    ) -> None:
        """Initialize MQTT manager."""
        self.api = api
        self.device = device
        self.device_sn = device["device_sn"]
        self.on_update = on_update
        self.realtime_interval = realtime_interval
        self.keepalive = keepalive
        self.stale_after = stale_after
        self.debug_logging = debug_logging
        self.session: AnkerSolixMqttSession | None = None
        self.task: asyncio.Task | None = None
        self.running = False
        self.connected = False
        self.reconnect_count = 0
        self.last_payload_time: datetime | None = None
        self.last_seen: datetime | None = None
        self.last_payload: dict[str, Any] | None = None
        self.payload_history: deque[dict[str, Any]] = deque(maxlen=50)
        self.last_values: dict[str, Any] = {}
        self.realtime_status = "stopped"
        self.last_realtime_trigger: datetime | None = None
        self.last_status_request: datetime | None = None
        self.last_error: str | None = None
        self.recovery_count = 0
        self._stale_recovery_attempts = 0

    async def async_start(self) -> None:
        """Start MQTT loop."""
        if self.task:
            return
        self.running = True
        self.task = asyncio.create_task(self._run(), name="a2345_mqtt")

    async def async_stop(self) -> None:
        """Stop MQTT loop and clean up paho resources."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        if self.session:
            await asyncio.to_thread(self.session.cleanup)
            self.session = None
        self.connected = False
        self.realtime_status = "stopped"
        self._publish_state()

    async def async_trigger_realtime(self) -> None:
        """Send realtime trigger if connected."""
        if not self.session or not self.session.is_connected():
            return
        try:
            await asyncio.to_thread(
                self.session.realtime_trigger,
                self.device,
                10,
                2,
            )
            self.last_realtime_trigger = datetime.now(UTC)
            self.realtime_status = "triggered"
        except Exception as err:  # noqa: BLE001
            self.realtime_status = "trigger_failed"
            self.last_error = str(err)
            _LOGGER.debug("A2345 realtime trigger failed: %s", err)
        finally:
            self._publish_state()

    async def async_status_request(self) -> None:
        """Send MQTT status request if connected."""
        if not self.session or not self.session.is_connected():
            return
        try:
            await asyncio.to_thread(self.session.status_request, self.device, 2)
            self.last_status_request = datetime.now(UTC)
            self.realtime_status = "status_requested"
        except Exception as err:  # noqa: BLE001
            self.last_error = str(err)
            _LOGGER.debug("A2345 MQTT status request failed: %s", err)
        finally:
            self._publish_state()

    async def _run(self) -> None:
        """Maintain MQTT connection with backoff and periodic realtime refresh."""
        backoff = 5
        next_realtime = 0.0
        next_status_request = 0.0
        while self.running:
            try:
                await self._ensure_connected()
                now = asyncio.get_running_loop().time()
                if now >= next_realtime:
                    await self.async_trigger_realtime()
                    next_realtime = now + self.realtime_interval
                if self._payload_stale():
                    self.realtime_status = "stale_payload"
                    self._stale_recovery_attempts += 1
                    if now >= next_status_request:
                        await self.async_trigger_realtime()
                        await self.async_status_request()
                        next_status_request = now + min(60, self.stale_after)
                    next_realtime = min(next_realtime, now + 30)
                    if self._should_reconnect_for_stale_payload():
                        self.recovery_count += 1
                        raise RuntimeError("MQTT payload watchdog forced reconnect")
                    self._publish_state()
                else:
                    self._stale_recovery_attempts = 0
                backoff = 5
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                self.connected = False
                self.realtime_status = "reconnecting"
                self.reconnect_count += 1
                self.last_error = str(err)
                self._publish_state()
                _LOGGER.warning(
                    "A2345 MQTT loop failed, reconnecting in %ss: %s", backoff, err
                )
                if self.session:
                    await asyncio.to_thread(self.session.cleanup)
                    self.session = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)

    async def _ensure_connected(self) -> None:
        """Create, connect and subscribe the MQTT session."""
        if self.session and self.session.is_connected():
            if not self.connected:
                self.connected = True
                self.reconnect_count += 1
                await self.async_trigger_realtime()
                self._publish_state()
            return

        if self.session:
            if self.connected:
                self.connected = False
                self.realtime_status = "disconnected"
                self._publish_state()
            await asyncio.to_thread(self.session.cleanup)
        self.session = AnkerSolixMqttSession(self.api.session)
        self.session.message_callback(self._handle_message)
        client = await self.session.connect_client_async(keepalive=self.keepalive)
        if not client or not client.is_connected():
            raise RuntimeError("MQTT connection was not established")
        topic = f"{self.session.get_topic_prefix(self.device)}#"
        self.session.subscribe(topic)
        self.connected = True
        self.reconnect_count += 1
        self.realtime_status = "connected"
        self.last_error = None
        await self.async_trigger_realtime()
        self._publish_state()

    def _handle_message(
        self,
        _session: Any,
        topic: str,
        message: Any,
        data: bytes | dict[str, Any],
        model: str,
        device_sn: str,
        extracted_values: dict[str, Any],
    ) -> None:
        """Handle decoded MQTT callback from paho thread."""
        if device_sn != self.device_sn or model != MODEL_A2345:
            return
        now = datetime.now(UTC)
        self.last_seen = now
        self.last_payload_time = now
        self._stale_recovery_attempts = 0
        self.last_payload = {
            "topic": topic,
            "message": _safe_message(message) if self.debug_logging else "<hidden>",
            "data_type": type(data).__name__,
            "values": extracted_values,
            "received_at": now,
        }
        self.payload_history.append(self.last_payload)
        if self.debug_logging:
            _LOGGER.debug("A2345 raw MQTT payload on %s: %s", topic, _safe_message(message))
        self._apply_port_switch_echo(extracted_values)
        self.last_values.update(extracted_values)
        self.realtime_status = "receiving"
        self._publish_state()

    def _apply_port_switch_echo(self, values: dict[str, Any]) -> None:
        """Map A2345 0302 switch echo fields back to stable switch keys."""
        if "set_port_switch_select" not in values or "set_port_switch" not in values:
            return
        port_map = {
            0: "usbc_1_switch",
            1: "usbc_2_switch",
            2: "usbc_3_switch",
            3: "usbc_4_switch",
            4: "usba_switch",
        }
        try:
            selected = int(values["set_port_switch_select"])
        except (TypeError, ValueError):
            return
        if key := port_map.get(selected):
            values[key] = values["set_port_switch"]

    def _payload_stale(self) -> bool:
        """Return true when no recent realtime payload was received."""
        if not self.last_payload_time:
            return True
        age = (datetime.now(UTC) - self.last_payload_time).total_seconds()
        return age > self.stale_after

    def _should_reconnect_for_stale_payload(self) -> bool:
        """Return true when soft recovery attempts did not restart payload flow."""
        if not self.last_payload_time:
            return self._stale_recovery_attempts >= 3
        age = (datetime.now(UTC) - self.last_payload_time).total_seconds()
        return age > max(self.stale_after * 3, self.realtime_interval + 60)

    def _publish_state(self) -> None:
        """Publish manager state to coordinator."""
        values = dict(self.last_values)
        values.update(
            {
                "mqtt_connected": self.connected,
                "mqtt_reconnect_count": self.reconnect_count,
                "last_seen": self.last_seen,
                "last_payload_time": self.last_payload_time,
                "realtime_status": self.realtime_status,
                "last_realtime_trigger": self.last_realtime_trigger,
                "last_status_request": self.last_status_request,
                "mqtt_recovery_count": self.recovery_count,
                "mqtt_last_error": self.last_error,
            }
        )
        self.on_update(values)


def _safe_message(message: Any) -> Any:
    """Return MQTT message envelope with obvious sensitive fields redacted."""
    if isinstance(message, dict):
        redacted = {}
        for key, value in message.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("token", "certificate", "private", "password")):
                redacted[key] = "**REDACTED**"
            elif isinstance(value, dict):
                redacted[key] = _safe_message(value)
            else:
                redacted[key] = value
        return redacted
    return message
