"""
Mood Detector - Phase 3: Stimmungs-, Stress- und Muedigkeitserkennung.

Analysiert User-Interaktionsmuster und erkennt:
- Stimmung (gut, neutral, gestresst, frustriert, muede)
- Stress (schnelle aufeinanderfolgende Befehle, ungeduldige Sprache)
- Muedigkeit (spaete Uhrzeit + kurze Nachrichten + muede Keywords)
- Frustration (Wiederholungen, negative Keywords, Ausrufezeichen)

Nutzt Redis fuer die Interaktions-History und Pattern-Erkennung.
"""

import logging
import time
from collections import deque
from datetime import datetime
from typing import Optional

import redis.asyncio as redis

from .config import yaml_config

logger = logging.getLogger(__name__)

# Stimmungs-Zust{ae}nde
MOOD_GOOD = "good"
MOOD_NEUTRAL = "neutral"
MOOD_STRESSED = "stressed"
MOOD_FRUSTRATED = "frustrated"
MOOD_TIRED = "tired"

# Keywords fuer Stimmungserkennung
POSITIVE_KEYWORDS = [
    "danke", "super", "perfekt", "toll", "geil", "nice", "cool", "genau",
    "klasse", "wunderbar", "prima", "top", "gut gemacht", "laeuft",
    "haha", "lol", "witzig", "lustig", "freut mich", "ja gerne",
]

NEGATIVE_KEYWORDS = [
    "nein", "falsch", "nicht das", "stimmt nicht", "geht nicht",
    "funktioniert nicht", "kaputt", "nervig", "nervt", "schlecht",
    "mist", "verdammt", "scheisse", "bloed", "egal",
]

IMPATIENT_KEYWORDS = [
    "schnell", "sofort", "jetzt", "los", "mach schon", "beeil dich",
    "endlich", "nochmal", "schon wieder", "hab ich doch gesagt",
    "zum dritten mal", "wie oft noch", "kapierst du",
]

TIRED_KEYWORDS = [
    "muede", "schlafen", "bett", "gute nacht", "nacht",
    "gaehn", "erschoepft", "fertig", "genug fuer heute",
    "schluss fuer heute", "feierabend", "ins bett",
]

FRUSTRATED_PREFIXES = [
    "nein ", "nein!", "nein,", "falsch!", "nicht!", "stopp!",
]


class MoodDetector:
    """Erkennt Stimmung, Stress und Muedigkeit aus User-Interaktionen."""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None

        # In-Memory Ring-Buffer fuer schnelle Pattern-Erkennung
        self._interaction_times: deque[float] = deque(maxlen=20)
        self._interaction_lengths: deque[int] = deque(maxlen=20)
        self._interaction_sentiments: deque[str] = deque(maxlen=10)
        self._last_texts: deque[str] = deque(maxlen=5)

        # Aktueller Zustand
        self._current_mood: str = MOOD_NEUTRAL
        self._stress_level: float = 0.0  # 0.0 = entspannt, 1.0 = maximal gestresst
        self._tiredness_level: float = 0.0  # 0.0 = wach, 1.0 = sehr muede
        self._frustration_count: int = 0
        self._positive_count: int = 0

        # Konfiguration
        mood_cfg = yaml_config.get("mood", {})
        self.rapid_command_threshold = mood_cfg.get("rapid_command_seconds", 5)
        self.stress_decay_seconds = mood_cfg.get("stress_decay_seconds", 300)
        self.frustration_threshold = mood_cfg.get("frustration_threshold", 3)
        self.tired_hour_start = mood_cfg.get("tired_hour_start", 23)
        self.tired_hour_end = mood_cfg.get("tired_hour_end", 5)

        self._last_decay_time = time.time()

    async def initialize(self, redis_client: Optional[redis.Redis] = None):
        """Initialisiert mit Redis."""
        self.redis = redis_client

        # Vorherigen Zustand aus Redis laden
        if self.redis:
            try:
                saved = await self.redis.hgetall("mha:mood:state")
                if saved:
                    self._current_mood = saved.get("mood", MOOD_NEUTRAL)
                    self._stress_level = float(saved.get("stress", 0.0))
                    self._tiredness_level = float(saved.get("tiredness", 0.0))
            except Exception as e:
                logger.debug("Mood-State nicht geladen: %s", e)

        logger.info("MoodDetector initialisiert (Stimmung: %s)", self._current_mood)

    async def analyze(self, text: str, person: str = "") -> dict:
        """
        Analysiert eine User-Eingabe und aktualisiert die Stimmung.

        Args:
            text: User-Text
            person: Name der Person

        Returns:
            Dict mit mood, stress_level, tiredness_level, signals
        """
        now = time.time()
        self._apply_decay(now)

        signals = []

        # 1. Zeitliches Muster: Schnelle aufeinanderfolgende Befehle = Stress
        if self._interaction_times:
            time_since_last = now - self._interaction_times[-1]
            if time_since_last < self.rapid_command_threshold:
                self._stress_level = min(1.0, self._stress_level + 0.15)
                signals.append("rapid_commands")

        # 2. Text-Analyse
        text_lower = text.lower().strip()
        text_len = len(text.split())

        # Positive Signale
        if any(kw in text_lower for kw in POSITIVE_KEYWORDS):
            self._positive_count += 1
            self._stress_level = max(0.0, self._stress_level - 0.1)
            self._frustration_count = max(0, self._frustration_count - 1)
            signals.append("positive_language")

        # Negative/frustrierte Signale
        if any(kw in text_lower for kw in NEGATIVE_KEYWORDS):
            self._frustration_count += 1
            self._stress_level = min(1.0, self._stress_level + 0.1)
            signals.append("negative_language")

        # Ungeduldige Signale
        if any(kw in text_lower for kw in IMPATIENT_KEYWORDS):
            self._stress_level = min(1.0, self._stress_level + 0.2)
            self._frustration_count += 1
            signals.append("impatient_language")

        # Muedigkeits-Keywords
        if any(kw in text_lower for kw in TIRED_KEYWORDS):
            self._tiredness_level = min(1.0, self._tiredness_level + 0.3)
            signals.append("tired_keywords")

        # Frustrierte Wiederholung (gleicher/aehnlicher Text wie vorher)
        if self._last_texts and self._is_repetition(text_lower):
            self._frustration_count += 2
            self._stress_level = min(1.0, self._stress_level + 0.15)
            signals.append("repetition")

        # Ausrufezeichen = Ungeduld/Frustration
        exclamation_count = text.count("!")
        if exclamation_count >= 2:
            self._stress_level = min(1.0, self._stress_level + 0.1)
            signals.append("exclamation_marks")

        # Frustrierter Anfang
        if any(text_lower.startswith(p) for p in FRUSTRATED_PREFIXES):
            self._frustration_count += 1
            signals.append("frustrated_prefix")

        # Sehr kurze Nachrichten spaet abends = muede
        hour = datetime.now().hour
        is_late = hour >= self.tired_hour_start or hour < self.tired_hour_end
        if is_late:
            self._tiredness_level = min(1.0, self._tiredness_level + 0.05)
            if text_len <= 3:
                self._tiredness_level = min(1.0, self._tiredness_level + 0.1)
                signals.append("short_late_message")

        # Interaktion aufzeichnen
        self._interaction_times.append(now)
        self._interaction_lengths.append(text_len)
        self._last_texts.append(text_lower)

        # 3. Gesamt-Stimmung bestimmen
        self._current_mood = self._determine_mood()

        # 4. In Redis speichern
        await self._save_state()

        result = {
            "mood": self._current_mood,
            "stress_level": round(self._stress_level, 2),
            "tiredness_level": round(self._tiredness_level, 2),
            "frustration_count": self._frustration_count,
            "signals": signals,
        }

        if signals:
            logger.info(
                "Mood: %s (Stress: %.2f, Muede: %.2f, Signale: %s)",
                self._current_mood, self._stress_level,
                self._tiredness_level, ", ".join(signals),
            )

        return result

    def get_current_mood(self) -> dict:
        """Gibt den aktuellen Stimmungszustand zurueck."""
        return {
            "mood": self._current_mood,
            "stress_level": round(self._stress_level, 2),
            "tiredness_level": round(self._tiredness_level, 2),
            "frustration_count": self._frustration_count,
            "positive_count": self._positive_count,
        }

    def _determine_mood(self) -> str:
        """Bestimmt die Gesamt-Stimmung aus allen Signalen."""
        # Muedigkeit hat Vorrang wenn sehr hoch
        if self._tiredness_level >= 0.6:
            return MOOD_TIRED

        # Frustration wenn mehrfach hintereinander negativ
        if self._frustration_count >= self.frustration_threshold:
            return MOOD_FRUSTRATED

        # Stress wenn Stresslevel hoch
        if self._stress_level >= 0.5:
            return MOOD_STRESSED

        # Gute Stimmung wenn positive Signale ueberwiegen
        if self._positive_count >= 2 and self._frustration_count == 0:
            return MOOD_GOOD

        return MOOD_NEUTRAL

    def _is_repetition(self, text: str) -> bool:
        """Prueft ob der Text eine Wiederholung ist."""
        for prev in self._last_texts:
            # Exakte Wiederholung
            if text == prev:
                return True
            # Aehnliche Wiederholung (gleiche Woerter)
            words = set(text.split())
            prev_words = set(prev.split())
            if len(words) > 1 and len(words & prev_words) / max(len(words), 1) > 0.7:
                return True
        return False

    def _apply_decay(self, now: float):
        """Laesst Stress und Frustration ueber Zeit abklingen."""
        elapsed = now - self._last_decay_time
        if elapsed > 60:  # Alle 60 Sekunden Decay
            decay_factor = elapsed / self.stress_decay_seconds
            self._stress_level = max(0.0, self._stress_level - decay_factor * 0.3)
            self._tiredness_level = max(0.0, self._tiredness_level - decay_factor * 0.1)
            if elapsed > 600:  # Nach 10 Minuten Pause: Frustration reset
                self._frustration_count = max(0, self._frustration_count - 1)
                self._positive_count = max(0, self._positive_count - 1)
            self._last_decay_time = now

    async def _save_state(self):
        """Speichert den aktuellen Zustand in Redis."""
        if not self.redis:
            return
        try:
            await self.redis.hset("mha:mood:state", mapping={
                "mood": self._current_mood,
                "stress": str(self._stress_level),
                "tiredness": str(self._tiredness_level),
                "frustration": str(self._frustration_count),
                "positive": str(self._positive_count),
                "updated": datetime.now().isoformat(),
            })
            # 1h TTL - Reset nach laengerer Inaktivitaet
            await self.redis.expire("mha:mood:state", 3600)
        except Exception as e:
            logger.debug("Mood-State nicht gespeichert: %s", e)
