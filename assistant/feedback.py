"""
Feedback Tracker - Phase 5: Der MindHome Assistant lernt aus Reaktionen.

Verfolgt wie der Benutzer auf proaktive Meldungen reagiert und passt
das Verhalten entsprechend an:
- Oft ignorierte Meldungen -> seltener senden
- Geschaetzte Meldungen -> haeufiger senden
- Adaptiver Cooldown pro Event-Typ
- Auto-Timeout: Keine Reaktion = "ignored"
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import redis.asyncio as redis

from .config import yaml_config

logger = logging.getLogger(__name__)

# Feedback-Typen und ihre Score-Deltas
FEEDBACK_DELTAS = {
    "ignored": -0.05,    # Keine Reaktion (Auto-Timeout)
    "dismissed": -0.10,  # Aktiv weggeklickt
    "acknowledged": 0.05,  # Zur Kenntnis genommen
    "engaged": 0.10,     # Drauf eingegangen
    "thanked": 0.20,     # Bedankt
}

# Standard-Score fuer neue Event-Typen
DEFAULT_SCORE = 0.5

# Score-Grenzen fuer Entscheidungen
SCORE_SUPPRESS = 0.15     # Unter diesem Wert: nicht mehr senden
SCORE_REDUCE = 0.30       # Unter diesem Wert: laengerer Cooldown
SCORE_NORMAL = 0.50       # Normaler Cooldown
SCORE_BOOST = 0.70        # Ueber diesem Wert: kuerzerer Cooldown


class FeedbackTracker:
    """Verfolgt und lernt aus Benutzer-Feedback auf proaktive Meldungen."""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None

        # Pending notifications: warten auf Feedback
        # {notification_id: {"event_type": str, "sent_at": datetime}}
        self._pending: dict[str, dict] = {}

        # Auto-Timeout Task
        self._timeout_task: Optional[asyncio.Task] = None
        self._running = False

        # Konfiguration aus YAML laden
        feedback_cfg = yaml_config.get("feedback", {})
        self.auto_timeout_seconds = feedback_cfg.get("auto_timeout_seconds", 120)
        self.base_cooldown_seconds = feedback_cfg.get("base_cooldown_seconds", 300)

    async def initialize(self, redis_client: Optional[redis.Redis] = None):
        """Initialisiert den Tracker mit Redis-Verbindung."""
        self.redis = redis_client
        self._running = True
        self._timeout_task = asyncio.create_task(self._auto_timeout_loop())
        logger.info("FeedbackTracker initialisiert")

    async def stop(self):
        """Stoppt den Auto-Timeout Loop."""
        self._running = False
        if self._timeout_task:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass

    # ----- Notification Tracking -----

    async def track_notification(self, notification_id: str, event_type: str):
        """Registriert eine gesendete proaktive Meldung (wartet auf Feedback)."""
        self._pending[notification_id] = {
            "event_type": event_type,
            "sent_at": datetime.now(),
        }

        # Gesamt-Zaehler erhoehen
        await self._increment_counter(event_type, "total_sent")

        logger.debug(
            "Notification tracked: %s (type: %s)", notification_id, event_type
        )

    async def record_feedback(
        self, notification_id: str, feedback_type: str
    ) -> Optional[dict]:
        """
        Verarbeitet Feedback auf eine proaktive Meldung.

        Args:
            notification_id: ID der Meldung (oder event_type als Fallback)
            feedback_type: ignored, dismissed, acknowledged, engaged, thanked

        Returns:
            Dict mit neuem Score und event_type, oder None bei Fehler.
        """
        if feedback_type not in FEEDBACK_DELTAS:
            logger.warning("Unbekannter Feedback-Typ: %s", feedback_type)
            return None

        # Event-Typ ermitteln
        event_type = None
        if notification_id in self._pending:
            event_type = self._pending.pop(notification_id)["event_type"]
        else:
            # Fallback: notification_id ist der event_type
            event_type = notification_id

        if not event_type:
            return None

        delta = FEEDBACK_DELTAS[feedback_type]

        # Score aktualisieren
        new_score = await self._update_score(event_type, delta)

        # Feedback-History speichern
        await self._store_feedback_entry(event_type, feedback_type, delta)

        # Zaehler aktualisieren
        await self._increment_counter(event_type, feedback_type)

        logger.info(
            "Feedback [%s] fuer '%s': %+.2f -> Score: %.2f",
            feedback_type, event_type, delta, new_score,
        )

        return {
            "event_type": event_type,
            "feedback_type": feedback_type,
            "delta": delta,
            "new_score": new_score,
        }

    # ----- Score & Entscheidungen -----

    async def get_score(self, event_type: str) -> float:
        """Holt den aktuellen Feedback-Score fuer einen Event-Typ."""
        if not self.redis:
            return DEFAULT_SCORE
        score = await self.redis.get(f"mha:feedback:score:{event_type}")
        return float(score) if score else DEFAULT_SCORE

    async def should_notify(self, event_type: str, urgency: str) -> dict:
        """
        Entscheidet ob eine proaktive Meldung gesendet werden soll.

        Returns:
            Dict mit:
                allow: bool - Meldung senden?
                reason: str - Begruendung
                cooldown: int - Empfohlener Cooldown in Sekunden
        """
        # Critical immer durchlassen
        if urgency == "critical":
            return {
                "allow": True,
                "reason": "critical_always_allowed",
                "cooldown": 0,
            }

        score = await self.get_score(event_type)

        # HIGH: nur unterdruecken wenn Score sehr niedrig
        if urgency == "high":
            if score < SCORE_SUPPRESS:
                return {
                    "allow": False,
                    "reason": f"score_too_low ({score:.2f})",
                    "cooldown": 0,
                }
            return {
                "allow": True,
                "reason": "high_priority",
                "cooldown": self._calculate_cooldown(score),
            }

        # MEDIUM: unterdruecken wenn Score niedrig
        if urgency == "medium":
            if score < SCORE_REDUCE:
                return {
                    "allow": False,
                    "reason": f"score_too_low ({score:.2f})",
                    "cooldown": 0,
                }
            return {
                "allow": True,
                "reason": "score_ok",
                "cooldown": self._calculate_cooldown(score),
            }

        # LOW: strenger filtern
        if score < SCORE_NORMAL:
            return {
                "allow": False,
                "reason": f"low_priority_score_insufficient ({score:.2f})",
                "cooldown": 0,
            }

        return {
            "allow": True,
            "reason": "score_ok",
            "cooldown": self._calculate_cooldown(score),
        }

    def _calculate_cooldown(self, score: float) -> int:
        """Berechnet den adaptiven Cooldown basierend auf dem Score."""
        if score >= SCORE_BOOST:
            # Guter Score -> kuerzerer Cooldown (60% der Basis)
            return int(self.base_cooldown_seconds * 0.6)
        elif score >= SCORE_NORMAL:
            # Normaler Score -> Standard-Cooldown
            return self.base_cooldown_seconds
        elif score >= SCORE_REDUCE:
            # Niedriger Score -> laengerer Cooldown (200% der Basis)
            return int(self.base_cooldown_seconds * 2.0)
        else:
            # Sehr niedrig -> sehr langer Cooldown (500% der Basis)
            return int(self.base_cooldown_seconds * 5.0)

    # ----- Statistiken -----

    async def get_stats(self, event_type: Optional[str] = None) -> dict:
        """Holt Feedback-Statistiken (gesamt oder pro Event-Typ)."""
        if not self.redis:
            return {"error": "redis_unavailable"}

        if event_type:
            return await self._get_event_stats(event_type)

        # Alle Event-Typen sammeln
        keys = []
        cursor = 0
        while True:
            cursor, batch = await self.redis.scan(
                cursor, match="mha:feedback:score:*", count=100
            )
            keys.extend(batch)
            if cursor == 0:
                break

        stats = {}
        for key in keys:
            et = key.replace("mha:feedback:score:", "")
            stats[et] = await self._get_event_stats(et)

        return {
            "event_types": stats,
            "total_types": len(stats),
            "pending_notifications": len(self._pending),
        }

    async def _get_event_stats(self, event_type: str) -> dict:
        """Holt detaillierte Statistiken fuer einen Event-Typ."""
        score = await self.get_score(event_type)
        counters = await self._get_counters(event_type)
        recent = await self._get_recent_feedback(event_type, limit=5)
        cooldown = self._calculate_cooldown(score)

        return {
            "score": score,
            "cooldown_seconds": cooldown,
            "counters": counters,
            "recent_feedback": recent,
        }

    async def get_all_scores(self) -> dict[str, float]:
        """Holt alle Feedback-Scores."""
        if not self.redis:
            return {}

        scores = {}
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor, match="mha:feedback:score:*", count=100
            )
            for key in keys:
                et = key.replace("mha:feedback:score:", "")
                val = await self.redis.get(key)
                scores[et] = float(val) if val else DEFAULT_SCORE
            if cursor == 0:
                break

        return scores

    # ----- Private Hilfsmethoden -----

    async def _update_score(self, event_type: str, delta: float) -> float:
        """Aktualisiert den Score und gibt den neuen Wert zurueck."""
        if not self.redis:
            return DEFAULT_SCORE

        current = await self.get_score(event_type)
        new_score = max(0.0, min(1.0, current + delta))
        await self.redis.set(f"mha:feedback:score:{event_type}", str(new_score))
        return new_score

    async def _increment_counter(self, event_type: str, counter_name: str):
        """Erhoeht einen Zaehler fuer einen Event-Typ."""
        if not self.redis:
            return
        await self.redis.hincrby(
            f"mha:feedback:counters:{event_type}", counter_name, 1
        )

    async def _get_counters(self, event_type: str) -> dict:
        """Holt alle Zaehler fuer einen Event-Typ."""
        if not self.redis:
            return {}
        data = await self.redis.hgetall(f"mha:feedback:counters:{event_type}")
        return {k: int(v) for k, v in data.items()}

    async def _store_feedback_entry(
        self, event_type: str, feedback_type: str, delta: float
    ):
        """Speichert einen Feedback-Eintrag in der History."""
        if not self.redis:
            return

        entry = json.dumps({
            "type": feedback_type,
            "delta": delta,
            "timestamp": datetime.now().isoformat(),
        })

        key = f"mha:feedback:history:{event_type}"
        await self.redis.lpush(key, entry)
        # Nur die letzten 50 Eintraege behalten
        await self.redis.ltrim(key, 0, 49)

    async def _get_recent_feedback(
        self, event_type: str, limit: int = 5
    ) -> list[dict]:
        """Holt die letzten Feedback-Eintraege fuer einen Event-Typ."""
        if not self.redis:
            return []

        key = f"mha:feedback:history:{event_type}"
        entries = await self.redis.lrange(key, 0, limit - 1)
        return [json.loads(e) for e in entries]

    async def _auto_timeout_loop(self):
        """Prueft periodisch auf Meldungen ohne Feedback (Auto-Timeout)."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Alle 30 Sekunden pruefen
                await self._check_timeouts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Fehler im Auto-Timeout Loop: %s", e)

    async def _check_timeouts(self):
        """Markiert alte Meldungen ohne Feedback als 'ignored'."""
        now = datetime.now()
        timeout = timedelta(seconds=self.auto_timeout_seconds)

        expired = []
        for nid, info in self._pending.items():
            if now - info["sent_at"] > timeout:
                expired.append(nid)

        for nid in expired:
            info = self._pending.pop(nid)
            await self._update_score(info["event_type"], FEEDBACK_DELTAS["ignored"])
            await self._store_feedback_entry(
                info["event_type"], "ignored", FEEDBACK_DELTAS["ignored"]
            )
            await self._increment_counter(info["event_type"], "ignored")
            logger.debug(
                "Auto-Timeout: '%s' als ignored markiert", info["event_type"]
            )
