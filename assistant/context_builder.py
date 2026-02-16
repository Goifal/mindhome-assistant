"""
Context Builder - Sammelt alle relevanten Daten fuer den LLM-Prompt.
Holt Daten von Home Assistant und MindHome via REST API.
"""

import logging
from datetime import datetime
from typing import Optional

from .ha_client import HomeAssistantClient

logger = logging.getLogger(__name__)

# Relevante Entity-Typen fuer den Kontext
RELEVANT_DOMAINS = [
    "light", "climate", "cover", "scene", "person",
    "weather", "sensor", "binary_sensor", "media_player",
    "lock", "alarm_control_panel",
]


class ContextBuilder:
    """Baut den vollstaendigen Kontext fuer das LLM zusammen."""

    def __init__(self, ha_client: HomeAssistantClient):
        self.ha = ha_client

    async def build(self, trigger: str = "voice") -> dict:
        """
        Sammelt den kompletten Kontext.

        Args:
            trigger: Was den Kontext ausloest ("voice", "proactive", "api")

        Returns:
            Strukturierter Kontext als Dict
        """
        context = {}

        # Zeitkontext
        now = datetime.now()
        context["time"] = {
            "datetime": now.strftime("%Y-%m-%d %H:%M"),
            "weekday": self._weekday_german(now.weekday()),
            "time_of_day": self._get_time_of_day(now.hour),
        }

        # Haus-Status von HA
        states = await self.ha.get_states()
        if states:
            context["house"] = self._extract_house_status(states)
            context["person"] = self._extract_person(states)
            context["room"] = self._guess_current_room(states)

        # MindHome-Daten (optional, falls MindHome installiert)
        mindhome_data = await self._get_mindhome_data()
        if mindhome_data:
            context["mindhome"] = mindhome_data

        # Warnungen
        context["alerts"] = self._extract_alerts(states or [])

        return context

    def _extract_house_status(self, states: list[dict]) -> dict:
        """Extrahiert den Haus-Status aus HA States."""
        house = {
            "temperatures": {},
            "lights": [],
            "presence": {"home": [], "away": []},
            "weather": {},
            "active_scenes": [],
            "security": "unknown",
            "media": [],
        }

        for state in states:
            entity_id = state.get("entity_id", "")
            s = state.get("state", "")
            attrs = state.get("attributes", {})
            domain = entity_id.split(".")[0] if "." in entity_id else ""

            # Temperaturen
            if domain == "climate":
                room = attrs.get("friendly_name", entity_id)
                house["temperatures"][room] = {
                    "current": attrs.get("current_temperature"),
                    "target": attrs.get("temperature"),
                    "mode": s,
                }

            # Lichter (nur die an sind)
            elif domain == "light" and s == "on":
                name = attrs.get("friendly_name", entity_id)
                brightness = attrs.get("brightness")
                if brightness:
                    pct = round(brightness / 255 * 100)
                    house["lights"].append(f"{name}: {pct}%")
                else:
                    house["lights"].append(f"{name}: an")

            # Personen
            elif domain == "person":
                name = attrs.get("friendly_name", entity_id)
                if s == "home":
                    house["presence"]["home"].append(name)
                else:
                    house["presence"]["away"].append(name)

            # Wetter
            elif domain == "weather" and not house["weather"]:
                house["weather"] = {
                    "temp": attrs.get("temperature"),
                    "condition": s,
                    "humidity": attrs.get("humidity"),
                }

            # Alarm
            elif domain == "alarm_control_panel":
                house["security"] = s

            # Medien
            elif domain == "media_player" and s == "playing":
                name = attrs.get("friendly_name", entity_id)
                title = attrs.get("media_title", "")
                house["media"].append(f"{name}: {title}" if title else name)

        return house

    def _extract_person(self, states: list[dict]) -> dict:
        """Findet die aktive Person."""
        for state in states:
            if state.get("entity_id", "").startswith("person."):
                if state.get("state") == "home":
                    return {
                        "name": state.get("attributes", {}).get(
                            "friendly_name", "User"
                        ),
                        "last_room": "unbekannt",
                    }
        return {"name": "User", "last_room": "unbekannt"}

    def _guess_current_room(self, states: list[dict]) -> str:
        """Versucht den aktuellen Raum zu erraten (letzte Bewegung)."""
        latest_motion = None
        latest_room = "unbekannt"

        for state in states:
            entity_id = state.get("entity_id", "")
            if (
                "motion" in entity_id
                and state.get("state") == "on"
            ):
                last_changed = state.get("last_changed", "")
                if not latest_motion or last_changed > latest_motion:
                    latest_motion = last_changed
                    name = state.get("attributes", {}).get(
                        "friendly_name", entity_id
                    )
                    latest_room = name.replace("Bewegung ", "").replace(" Motion", "")

        return latest_room

    def _extract_alerts(self, states: list[dict]) -> list[str]:
        """Extrahiert aktive Warnungen."""
        alerts = []
        for state in states:
            entity_id = state.get("entity_id", "")
            s = state.get("state", "")

            # Rauchmelder, Wassermelder, etc.
            if any(x in entity_id for x in ["smoke", "water_leak", "gas"]):
                if s == "on":
                    name = state.get("attributes", {}).get(
                        "friendly_name", entity_id
                    )
                    alerts.append(f"ALARM: {name}")

            # Fenster/Tueren offen bei Alarm
            if "door" in entity_id or "window" in entity_id:
                if s == "on":
                    name = state.get("attributes", {}).get(
                        "friendly_name", entity_id
                    )
                    alerts.append(f"Offen: {name}")

        return alerts

    async def _get_mindhome_data(self) -> Optional[dict]:
        """Holt optionale MindHome-Daten."""
        try:
            data = {}
            presence = await self.ha.get_presence()
            if presence:
                data["presence"] = presence
            energy = await self.ha.get_energy()
            if energy:
                data["energy"] = energy
            return data if data else None
        except Exception as e:
            logger.debug("MindHome nicht verfuegbar: %s", e)
            return None

    @staticmethod
    def _get_time_of_day(hour: int) -> str:
        if 5 <= hour < 8:
            return "early_morning"
        elif 8 <= hour < 12:
            return "morning"
        elif 12 <= hour < 18:
            return "afternoon"
        elif 18 <= hour < 22:
            return "evening"
        return "night"

    @staticmethod
    def _weekday_german(weekday: int) -> str:
        days = [
            "Montag", "Dienstag", "Mittwoch", "Donnerstag",
            "Freitag", "Samstag", "Sonntag",
        ]
        return days[weekday]
