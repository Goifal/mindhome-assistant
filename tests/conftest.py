"""
Pytest Konfiguration und gemeinsame Fixtures.
"""

import os
import sys

import pytest

# Umgebungsvariablen fuer Tests setzen (BEVOR Settings importiert wird)
os.environ.setdefault("HA_URL", "http://localhost:8123")
os.environ.setdefault("HA_TOKEN", "test_token")
os.environ.setdefault("MINDHOME_URL", "http://localhost:8099")
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("CHROMA_URL", "http://localhost:8100")
os.environ.setdefault("USER_NAME", "TestUser")


@pytest.fixture
def sample_ha_states():
    """Beispiel-States wie sie von HA kommen."""
    return [
        {
            "entity_id": "light.wohnzimmer",
            "state": "on",
            "attributes": {"friendly_name": "Wohnzimmer Licht", "brightness": 200},
        },
        {
            "entity_id": "light.schlafzimmer",
            "state": "off",
            "attributes": {"friendly_name": "Schlafzimmer Licht"},
        },
        {
            "entity_id": "light.buero",
            "state": "on",
            "attributes": {"friendly_name": "B\u00fcro Licht", "brightness": 128},
        },
        {
            "entity_id": "climate.wohnzimmer",
            "state": "heat",
            "attributes": {
                "friendly_name": "Wohnzimmer Thermostat",
                "current_temperature": 21.5,
                "temperature": 22.0,
            },
        },
        {
            "entity_id": "person.max",
            "state": "home",
            "attributes": {"friendly_name": "Max"},
        },
        {
            "entity_id": "person.lisa",
            "state": "not_home",
            "attributes": {"friendly_name": "Lisa"},
        },
        {
            "entity_id": "weather.home",
            "state": "cloudy",
            "attributes": {"temperature": 8, "humidity": 75},
        },
        {
            "entity_id": "binary_sensor.wohnzimmer_motion",
            "state": "on",
            "attributes": {"friendly_name": "Bewegung Wohnzimmer"},
            "last_changed": "2026-02-16T14:30:00",
        },
        {
            "entity_id": "alarm_control_panel.haus",
            "state": "armed_home",
            "attributes": {"friendly_name": "Alarmanlage"},
        },
        {
            "entity_id": "media_player.wohnzimmer",
            "state": "playing",
            "attributes": {"friendly_name": "Sonos Wohnzimmer", "media_title": "Chill Mix"},
        },
        {
            "entity_id": "cover.wohnzimmer",
            "state": "open",
            "attributes": {"friendly_name": "Rollladen Wohnzimmer", "current_position": 100},
        },
        {
            "entity_id": "lock.haustuer",
            "state": "locked",
            "attributes": {"friendly_name": "Haust\u00fcr"},
        },
        {
            "entity_id": "scene.filmabend",
            "state": "scening",
            "attributes": {"friendly_name": "Filmabend"},
        },
        {
            "entity_id": "scene.gute_nacht",
            "state": "scening",
            "attributes": {"friendly_name": "Gute Nacht"},
        },
        {
            "entity_id": "binary_sensor.smoke_keller",
            "state": "off",
            "attributes": {"friendly_name": "Rauchmelder Keller"},
        },
        {
            "entity_id": "input_select.anwesenheit",
            "state": "home",
            "attributes": {"friendly_name": "Anwesenheitsmodus"},
        },
    ]
