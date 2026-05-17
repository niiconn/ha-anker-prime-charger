# Contributing

Contributions should stay focused on the Anker Prime Charger A2345.

Useful contributions include:

- A2345 MQTT payload captures with sensitive values redacted
- Decoder fixes for confirmed A2345 fields
- Stability fixes for MQTT reconnect and realtime refresh behavior
- Documentation improvements

Before opening a pull request:

1. Keep changes scoped to the A2345 integration.
2. Do not add support for unrelated Solix devices.
3. Do not log credentials, tokens, MQTT certificates, private keys or account IDs.
4. Run:

```bash
python3 -m compileall -q custom_components/anker_prime_charger_a2345
python3 -m json.tool custom_components/anker_prime_charger_a2345/manifest.json
python3 -m json.tool custom_components/anker_prime_charger_a2345/strings.json
```

Contributions are licensed under the MIT License.
