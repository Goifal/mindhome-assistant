"""
Context Builder - Sammelt alle relevanten Daten fuer den LLM-Prompt.
Holt Daten von Home Assistant, MindHome und Semantic Memory via REST API.
"""

import logging
from datetime import datetime
from typing import Optional

from .ha_client import HomeAssistantClient
from .semantic_memory import SemanticMemory

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
        self.semantic: Optional[SemanticMemory] = None
        self._activity_engine = None

    def set_semantic_memory(self, semantic: SemanticMemory):
        """Setzt die Referenz zum Semantic Memory."""
        self.semantic = semantic

    def set_activity_engine(self, activity_engine):
        """Setzt die Referenz zur Activity Engine (Phase 6)."""
        self._activity_engine = activity_engine

    async def build(
        self, trigger: str = "voice", user_text: str = "", person: str = ""
    ) -> dict:
        """
        Sammelt den kompletten Kontext.

        Args:
            trigger: Was den Kontext ausloest ("voice", "proactive", "api")
            user_text: User-Eingabe fuer semantische Suche
            person: Name der Person

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

        # Aktivitaets-Erkennung (Phase 6)
        if self._activity_engine:
            try:
                detection = await self._activity_engine.detect_activity()
                context["activity"] = {
                    "current": detection["activity"],
                    "confidence": detection["confidence"],
                }
            except Exception as e:
                logger.debug("Activity Engine Fehler: %s", e)

        # Warnungen
        context["alerts"] = self._extract_alerts(states or [])

        # Semantisches Gedaechtnis - relevante Fakten zur Anfrage
        if self.semantic and user_text:
            context["memories"] = await self._get_relevant_memories(
                user_text, person
            )

        return context

    async def _get_relevant_memories(
        self, user_text: str, person: str = ""
    ) -> dict:
        """Holt relevante Fakten aus dem semantischen Gedaechtnis."""
        memories = {"relevant_facts": [], "person_facts": []}

        if not self.semantic:
            return memories

        try:
            # Fakten die zur aktuellen Anfrage passen
            relevant = await self.semantic.search_facts(
                query=user_text, limit=3, person=person or None
            )
            memories["relevant_facts"] = [
                f["content"] for f in relevant if f.get("relevance", 0) > 0.3
            ]

            # Allgemeine Fakten ueber die Person (Praeferenzen)
            if person:
                person_facts = await self.semantic.get_facts_by_person(person)
                # Top-5 mit hoechster Confidence
                memories["person_facts"] = [
                    f["content"] for f in person_facts[:5]
                    if f.get("confidence", 0) >= 0.6
                ]
        except Exception as e:
            logger.error("Fehler beim Laden semantischer Erinnerungen: %s", e)

        return memories

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
