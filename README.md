# Anker Prime Charger (A2345)

Dedicated Home Assistant custom integration for the Anker Prime Charger A2345 / 250W Desktop Charger.

This project is a focused fork of `ha-anker-solix`. It keeps the Anker Cloud login, token handling, AWS IoT MQTT connection, MQTT command generation and A2345 payload decoding concepts, but exposes them as a standalone charger integration instead of a broad Solix integration.

## Project Status

This integration is experimental and focused only on the Anker Prime Charger A2345 / 250W Desktop Charger.

The Anker Cloud APIs and MQTT payloads are unofficial and can change without notice. Use this integration at your own risk.

## Attribution

This project is a dedicated fork of:

- `ha-anker-solix`: https://github.com/thomluther/ha-anker-solix

The original project is licensed under the MIT License. This fork keeps attribution in `LICENSE` and `NOTICE.md`.

## Disclaimer

This custom integration is independent and is not affiliated with Anker.

Any trademarks, product names or logos belong to their respective owners.

The integration uses unofficial Anker Cloud and MQTT behavior. Cloud APIs, MQTT message formats, authentication and device commands may change or break at any time. Commands are intentionally limited to A2345 USB port controls that are known from the upstream Solix MQTT maps.

## Phase 1 scope

- UI config flow with Anker email, password and country/region.
- Discovery and selection of compatible A2345 devices.
- AWS IoT MQTT connection using Anker-provided certificates.
- Subscription to A2345 MQTT topics.
- Realtime trigger on startup and periodic refresh.
- Automatic reconnect with exponential backoff.
- Fallback MQTT status request when payloads stop arriving.
- Base entities:
  - Online status
  - MQTT connected
  - Last seen
  - Last payload time
  - Total power
  - Realtime status
  - MQTT reconnect count

## Phase 2 scope

The integration now also exposes expanded A2345 entities when the decoded MQTT payloads contain the matching fields:

- USB-C 1-4:
  - Power
  - Voltage
  - Current
  - Status
  - Active binary sensor
- USB-A 1-2:
  - Power
  - Voltage
  - Current
  - Status
  - Active binary sensor
- Firmware version from cloud `main_version` or MQTT `sw_version`
- Geräteinformationen from the A2345 mini-power device identity endpoints when Anker Cloud returns connected-device names
- Realtime status
- MQTT reconnect count
- Last payload time

AC outlet, WiFi/RSSI, and charging protocol entities are intentionally omitted because they do not provide useful stable values for the A2345 charger in current payload captures.

## Phase 3 stability behavior

The runtime now has a dedicated recovery loop for the charger:

- MQTT auto-reconnect with exponential backoff up to 5 minutes.
- Realtime trigger after every new MQTT connection.
- Periodic realtime refresh using the configured interval.
- Soft recovery when payloads become stale: send realtime trigger, then MQTT status request.
- Hard recovery when stale payloads continue: rebuild MQTT session and resubscribe.
- Offline grace period based on `last_seen`, recalculated every 30 seconds even when no new payload arrives.
- Cloud polling fallback on the configured interval.
- Clean unload/reload: timers are removed and the MQTT session is closed.
- Recovery observability through:
  - MQTT recovery count
  - MQTT last error
  - Last realtime trigger
  - Last status request

## Installation with HACS

1. Add this repository as a HACS custom repository.
2. Category: Integration.
3. Install `Anker Prime Charger (A2345)`.
4. Restart Home Assistant.
5. Add the integration from Settings > Devices & services.

Use a separate Anker account where possible. Anker Cloud sessions can be sensitive to concurrent app and integration logins.

## Manual Installation

Copy the integration folder into Home Assistant:

```text
custom_components/anker_prime_charger_a2345/
```

Restart Home Assistant and add `Anker Prime Charger (A2345)` from Settings > Devices & services.

## Configuration

The config flow asks for:

- Email
- Password
- Country/region code, for example `US`, `DE`, `CH`
- A2345 device selection when more than one compatible charger is found

Credentials are stored in Home Assistant's config entry storage. The integration avoids logging credentials, auth tokens and MQTT certificates.

## Folder and Domain

The Home Assistant integration folder and domain are:

```text
custom_components/anker_prime_charger_a2345/
```

The integration domain is `anker_prime_charger_a2345`.

## Options

- Realtime refresh interval: default 300 seconds.
- Offline timeout: default 180 seconds.
- MQTT keepalive: default 60 seconds.
- Polling fallback: enabled by default.
- Polling interval: default 300 seconds.
- Debug logging: logs raw MQTT payload envelopes when enabled.
- Show unknown payload fields: reserved for reverse-engineering builds.

## MQTT and realtime behavior

The A2345 publishes useful values only after a realtime trigger. This integration sends a trigger after MQTT connect, repeats it periodically, and sends a status request if payloads become stale. On disconnect, MQTT is recreated with backoff and realtime is triggered again after reconnection.

Known A2345 MQTT payloads adapted from `ha-anker-solix`:

- `0303`: realtime port consumption, about 1 second interval after trigger.
- `0a00`: status/settings plus port values, requested by status command.
- `020b`: A2345-specific realtime trigger without the generic timeout fields.
- `0200`: status request.
- `0207`: known USB port switch command.

## Exposed port values

The integration creates USB-C and USB-A sensors for decoded values when available:

- Power
- Voltage
- Current
- Status
- Active state through binary/status fields where decoded

AC outlet, WiFi/RSSI, and charging protocol entities are intentionally not exposed. The broader Solix mapping includes related command shapes for other charger models, but this project avoids surfacing fields that are not useful for the A2345 workflow.

## Debugging

Enable debug logging in the integration options and set this logger in Home Assistant:

```yaml
logger:
  logs:
    custom_components.anker_prime_charger_a2345: debug
```

Use the service `anker_prime_charger_a2345.dump_last_payload` to write the most recent decoded MQTT payload to:

```text
config/anker_prime_charger_a2345_last_payload.json
```

Use `anker_prime_charger_a2345.dump_payload_history` to write the recent in-memory payload history to:

```text
config/anker_prime_charger_a2345_payload_history.json
```

Both services accept:

- `device_sn`: optional serial number filter.
- `include_raw`: include the MQTT envelope when debug data exists. Obvious secret keys are redacted.

Diagnostics include sanitized device data, MQTT connection state, subscriptions, reconnect/recovery counters and the last decoded payload. Credentials, auth tokens and certificate fields are redacted.

When `Show unknown payload fields` is enabled, the coordinator also exposes:

- Unknown payload field count
- Unknown payload fields
- Individual `unknown_*` debug sensors for unknown fields that are already known when entities are set up

## Known limitations

- Anker Cloud APIs are unofficial and can change.
- Discovery is intentionally conservative and only accepts product code `A2345`.
- Initial entity coverage focuses on stable sensors and known USB switch commands.
- Additional port metadata needs confirmed A2345 payload captures before entities are enabled.
- Unknown payload fields are not promoted automatically unless the debug option is enabled and the fields are present in decoded data.

## Reverse-engineering notes

The relevant source areas from `ha-anker-solix` are:

- `solixapi/session.py`: Anker Cloud login, token refresh and MQTT certificate endpoint.
- `solixapi/mqtt.py`: AWS IoT MQTT client, topic construction, publish envelope and realtime/status commands.
- `solixapi/mqtttypes.py`: binary payload field decoding.
- `solixapi/mqttcmdmap.py`: command descriptions and command byte generation.
- `solixapi/mqttmap.py`: A2345 message maps for `0303`, `0a00`, `0200`, `0207`, `020b`.
- `solixapi/mqtt_charger.py`: charger model command family, including A2345.
- `solixapi/mqtt_device.py`: generic command validation/control model.
- `solixapi/mqtt_factory.py`: routes charger product codes to the charger MQTT handler.

The implementation should continue incrementally: first validate stable realtime data, then expand sensors, then enable more controls only when payload captures prove command safety.
