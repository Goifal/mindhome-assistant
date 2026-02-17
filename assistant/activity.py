"""
Activity Engine + Silence Matrix - Phase 6: Perfektes Timing, nie stoeren.

Erkennt die aktuelle Aktivitaet des Benutzers anhand von HA-Sensoren
und entscheidet WIE eine Meldung zugestellt werden soll.

Aktivitaeten:
  sleeping    - Schlaeft (Nacht + Bett belegt + Lichter aus)
  in_call     - In einem Anruf/Zoom (Mikrofon aktiv)
  watching    - Schaut Film/TV (Media Player aktiv)
  focused     - Arbeitet konzentriert (PC aktiv, wenig Bewegung)
  guests      - Gaeste anwesend (mehrere Personen zu Hause)
  relaxing    - Entspannt (Standard-Aktivitaet)
  away        - Nicht zu Hause

Zustellmethoden:
  tts_loud    - Volle Lautstaerke
  tts_quiet   - Leise TTS
  led_blink   - Nur LED-Signal (kein Ton)
  suppress    - Gar nicht zustellen
"""

import logging
from datetime import datetime
from typing import Optional

from .config import yaml_config
from .ha_client import HomeAssistantClient

logger = logging.getLogger(__name__)


# Erkannte Aktivitaeten
SLEEPING = "sleeping"
IN_CALL = "in_call"
WATCHING = "watching"
FOCUSED = "focused"
GUESTS = "guests"
RELAXING = "relaxing"
AWAY = "away"

# Zustellmethoden
TTS_LOUD = "tts_loud"
TTS_QUIET = "tts_quiet"
LED_BLINK = "led_blink"
SUPPRESS = "suppress"

# Stille-Matrix: Aktivitaet x Urgency -> Zustellmethode
# Format: {activity: {urgency: delivery_method}}
SILENCE_MATRIX = {
    SLEEPING: {
        "critical": TTS_LOUD,
        "high": LED_BLINK,
        "medium": SUPPRESS,
        "low": SUPPRESS,
    },
    IN_CALL: {
        "critical": LED_BLINK,
        "high": LED_BLINK,
        "medium": SUPPRESS,
        "low": SUPPRESS,
    },
    WATCHING: {
        "critical": TTS_LOUD,
        "high": LED_BLINK,
        "medium": SUPPRESS,
        "low": SUPPRESS,
    },
    FOCUSED: {
        "critical": TTS_LOUD,
        "high": TTS_QUIET,
        "medium": TTS_QUIET,
        "low": SUPPRESS,
    },
    GUESTS: {
        "critical": TTS_LOUD,
        "high": TTS_QUIET,
        "medium": TTS_QUIET,
        "low": SUPPRESS,
    },
    RELAXING: {
        "critical": TTS_LOUD,
        "high": TTS_LOUD,
        "medium": TTS_LOUD,
        "low": TTS_QUIET,
    },
    AWAY: {
        "critical": TTS_LOUD,  # Wird an Handy weitergeleitet (spaeter)
        "high": SUPPRESS,
        "medium": SUPPRESS,
        "low": SUPPRESS,
    },
}


class ActivityEngine:
    """Erkennt die aktuelle Aktivitaet des Benutzers."""

    def __init__(self, ha_client: HomeAssistantClient):
        self.ha = ha_client

        # Konfiguration aus YAML
        activity_cfg = yaml_config.get("activity", {})

        # Entity-IDs (konfigurierbar pro Installation)
        entities = activity_cfg.get("entities", {})
        self.media_players = entities.get("media_players", [
            "media_player.wohnzimmer",
            "media_player.fernseher",
            "media_player.tv",
        ])
        self.mic_sensors = entities.get("mic_sensors", [
            "binary_sensor.mic_active",
            "binary_sensor.microphone",
        ])
        self.bed_sensors = entities.get("bed_sensors", [
            "binary_sensor.bed_occupancy",
            "binary_sensor.bett",
        ])
        self.pc_sensors = entities.get("pc_sensors", [
            "binary_sensor.pc_active",
            "binary_sensor.computer",
            "switch.pc",
        ])

        # Schwellwerte
        thresholds = activity_cfg.get("thresholds", {})
        self.night_start = thresholds.get("night_start", 22)
        self.night_end = thresholds.get("night_end", 7)
        self.guest_person_count = thresholds.get("guest_person_count", 2)
        self.focus_min_minutes = thresholds.get("focus_min_minutes", 30)

        # Cache: letzte erkannte Aktivitaet
        self._last_activity = RELAXING
        self._last_detection = None

    async def detect_activity(self) -> dict:
        """
        Erkennt die aktuelle Aktivitaet.

        Returns:
            Dict mit:
                activity: str - Erkannte Aktivitaet
                confidence: float - Wie sicher (0.0-1.0)
                signals: dict - Erkannte Signale
                delivery: str - Nicht gesetzt (wird von SilenceMatrix bestimmt)
        """
        signals = {}
        states = await self.ha.get_states()

        if not states:
            return {
                "activity": self._last_activity,
                "confidence": 0.3,
                "signals": {"ha_unavailable": True},
            }

        # Signale sammeln
        signals["away"] = self._check_away(states)
        signals["media_playing"] = self._check_media_playing(states)
        signals["in_call"] = self._check_in_call(states)
        signals["sleeping"] = self._check_sleeping(states)
        signals["pc_active"] = self._check_pc_active(states)
        signals["guests"] = self._check_guests(states)
        signals["lights_off"] = self._check_lights_off(states)

        # Aktivitaet klassifizieren (Prioritaet: hoehere ueberschreiben niedrigere)
        activity, confidence = self._classify(signals)

        self._last_activity = activity
        self._last_detection = datetime.now()

        logger.debug(
            "Aktivitaet erkannt: %s (confidence: %.2f, signals: %s)",
            activity, confidence, signals,
        )

        return {
            "activity": activity,
            "confidence": confidence,
            "signals": signals,
        }

    def get_delivery_method(self, activity: str, urgency: str) -> str:
        """
        Bestimmt die Zustellmethode anhand der Stille-Matrix.

        Args:
            activity: Erkannte Aktivitaet
            urgency: Dringlichkeit (critical, high, medium, low)

        Returns:
            Zustellmethode (tts_loud, tts_quiet, led_blink, suppress)
        """
        activity_row = SILENCE_MATRIX.get(activity, SILENCE_MATRIX[RELAXING])
        return activity_row.get(urgency, TTS_LOUD)

    async def should_deliver(self, urgency: str) -> dict:
        """
        Kombinierte Methode: Erkennt Aktivitaet und bestimmt Zustellmethode.

        Returns:
            Dict mit:
                activity: str - Erkannte Aktivitaet
                delivery: str - Zustellmethode
                suppress: bool - Soll die Meldung unterdrueckt werden?
                confidence: float - Sicherheit der Erkennung
        """
        detection = await self.detect_activity()
        activity = detection["activity"]
        delivery = self.get_delivery_method(activity, urgency)

        return {
            "activity": activity,
            "delivery": delivery,
            "suppress": delivery == SUPPRESS,
            "confidence": detection["confidence"],
            "signals": detection["signals"],
        }

    # ----- Signal-Erkennung -----

    def _check_away(self, states: list[dict]) -> bool:
        """Prueft ob niemand zu Hause ist."""
        for state in states:
            if state.get("entity_id", "").startswith("person."):
                if state.get("state") == "home":
                    return False
        return True

    def _check_media_playing(self, states: list[dict]) -> bool:
        """Prueft ob ein Media Player aktiv ist (TV, Film)."""
        for state in states:
            entity_id = state.get("entity_id", "")
            if entity_id.startswith("media_player."):
                if state.get("state") == "playing":
                    return True
        return False

    def _check_in_call(self, states: list[dict]) -> bool:
        """Prueft ob ein Mikrofon aktiv ist (Call/Zoom)."""
        for state in states:
            entity_id = state.get("entity_id", "")
            if entity_id in self.mic_sensors:
                if state.get("state") == "on":
                    return True
        return False

    def _check_sleeping(self, states: list[dict]) -> bool:
        """Prueft ob der Benutzer schlaeft (Nacht + Bett + Lichter aus)."""
        now = datetime.now()
        is_night = now.hour >= self.night_start or now.hour < self.night_end

        if not is_night:
            return False

        # Bett belegt?
        bed_occupied = False
        for state in states:
            if state.get("entity_id", "") in self.bed_sensors:
                if state.get("state") == "on":
                    bed_occupied = True
                    break

        # Lichter aus?
        lights_off = self._check_lights_off(states)

        # Schlaf: Nacht + (Bett belegt ODER alle Lichter aus)
        return bed_occupied or lights_off

    def _check_pc_active(self, states: list[dict]) -> bool:
        """Prueft ob der PC aktiv ist (Arbeit/Fokus)."""
        for state in states:
            entity_id = state.get("entity_id", "")
            if entity_id in self.pc_sensors:
                if state.get("state") in ("on", "active"):
                    return True
        return False

    def _check_guests(self, states: list[dict]) -> bool:
        """Prueft ob Gaeste anwesend sind (mehrere Personen zu Hause)."""
        persons_home = 0
        for state in states:
            if state.get("entity_id", "").startswith("person."):
                if state.get("state") == "home":
                    persons_home += 1
        return persons_home >= self.guest_person_count

    def _check_lights_off(self, states: list[dict]) -> bool:
        """Prueft ob alle Lichter aus sind."""
        any_light = False
        for state in states:
            entity_id = state.get("entity_id", "")
            if entity_id.startswith("light."):
                any_light = True
                if state.get("state") == "on":
                    return False
        # Nur True wenn es ueberhaupt Lichter gibt
        return any_light

    # ----- Klassifikation -----

    def _classify(self, signals: dict) -> tuple[str, float]:
        """
        Klassifiziert die Aktivitaet basierend auf gesammelten Signalen.
        Prioritaet: away > sleeping > in_call > watching > guests > focused > relaxing
        """
        # Niemand zu Hause
        if signals.get("away"):
            return AWAY, 0.95

        # Schlaf hat hoechste Prioritaet (nach away)
        if signals.get("sleeping"):
            confidence = 0.90 if signals.get("lights_off") else 0.70
            return SLEEPING, confidence

        # Anruf hat hohe Prioritaet (darf nicht gestoert werden)
        if signals.get("in_call"):
            return IN_CALL, 0.95

        # TV/Film schauen
        if signals.get("media_playing"):
            return WATCHING, 0.85

        # Gaeste anwesend
        if signals.get("guests"):
            return GUESTS, 0.80

        # PC aktiv = Arbeitsmodus
        if signals.get("pc_active"):
            return FOCUSED, 0.70

        # Standard: Entspannt
        return RELAXING, 0.60
