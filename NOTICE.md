# Notices

This project is a focused fork of:

- `ha-anker-solix`: https://github.com/thomluther/ha-anker-solix

The original project is licensed under the MIT License.

The following technical areas were adapted from `ha-anker-solix` and narrowed to the Anker Prime Charger A2345:

- Anker Cloud login and token handling
- MQTT certificate retrieval
- AWS IoT MQTT session handling
- MQTT topic construction and publish envelopes
- A2345 MQTT payload decoding maps
- A2345 MQTT command generation

This fork removes broad Solix device support and keeps only the A2345-specific integration surface.
