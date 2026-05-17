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

## Brand Images

This repository ships local Home Assistant brand images in:

```text
custom_components/anker_prime_charger_a2345/brand/
```

The icon and logo are original project artwork. They do not use official Anker logo assets.

## Installation with HACS

1. Add this repository as a HACS custom repository.
2. Category: Integration.
3. Install `Anker Prime Charger (A2345)`.
4. Restart Home Assistant.
5. Add the integration from Settings > Devices & services.

Use a separate Anker account where possible. Anker Cloud sessions can be sensitive to concurrent app and integration logins.

## Releases

HACS uses GitHub releases for versioned installs.

To publish a new release:

1. Update `version` in `custom_components/anker_prime_charger_a2345/manifest.json`.
2. Commit the change.
3. Create and push a matching tag, for example:

```bash
git tag v0.1.0
git push origin main
git push origin v0.1.0
```

The GitHub Actions release workflow validates the integration and creates the GitHub release. The tag version must match the `manifest.json` version.

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
