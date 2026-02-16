"""
Proactive Manager - Der MindHome Assistant spricht von sich aus.
Hoert auf Events von Home Assistant / MindHome und entscheidet ob
eine proaktive Meldung sinnvoll ist.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import aiohttp

from .config import settings, yaml_config
from .websocket import emit_proactive

logger = logging.getLogger(__name__)


# Event-Prioritaeten
CRITICAL = "critical"  # Immer melden (Alarm, Rauch, Wasser)
HIGH = "high"          # Melden wenn wach
MEDIUM = "medium"      # Melden wenn passend
LOW = "low"            # Melden wenn entspannt


class ProactiveManager:
    """Verwaltet proaktive Meldungen basierend auf HA-Events."""

    def __init__(self, brain):
        self.brain = brain
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Konfiguration
        proactive_cfg = yaml_config.get("proactive", {})
        self.enabled = proactive_cfg.get("enabled", True)
        self.cooldown = proactive_cfg.get("cooldown_seconds", 300)
        self.silence_scenes = set(proactive_cfg.get("silence_scenes", []))

        # Event-Mapping: HA Event -> Prioritaet + Beschreibung
        self.event_handlers = {
            # CRITICAL - Immer melden
            "alarm_triggered": (CRITICAL, "Alarm ausgeloest"),
            "smoke_detected": (CRITICAL, "Rauch erkannt"),
            "water_leak": (CRITICAL, "Wasseraustritt erkannt"),

            # HIGH - Melden wenn wach
            "motion_detected_night": (HIGH, "Naechtliche Bewegung"),

            # MEDIUM - Melden wenn passend
            "person_arrived": (MEDIUM, "Person angekommen"),
            "person_left": (MEDIUM, "Person gegangen"),
            "washer_done": (MEDIUM, "Waschmaschine fertig"),
            "dryer_done": (MEDIUM, "Trockner fertig"),
            "doorbell": (MEDIUM, "Jemand hat geklingelt"),

            # LOW - Melden wenn entspannt
            "energy_price_low": (LOW, "Strom ist guenstig"),
            "weather_warning": (LOW, "Wetterwarnung"),
        }

    async def start(self):
        """Startet den Event Listener."""
        if not self.enabled:
            logger.info("Proaktive Meldungen deaktiviert")
            return

        self._running = True
        self._task = asyncio.create_task(self._listen_ha_events())
        logger.info("Proactive Manager gestartet")

    async def stop(self):
        """Stoppt den Event Listener."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Proactive Manager gestoppt")

    async def _listen_ha_events(self):
        """Hoert auf Home Assistant Events via WebSocket."""
        ha_url = settings.ha_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ha_url}/api/websocket"

        while self._running:
            try:
                await self._connect_and_listen(ws_url)
            except Exception as e:
                logger.error("HA WebSocket Fehler: %s", e)
                if self._running:
                    await asyncio.sleep(10)  # Reconnect nach 10s

    async def _connect_and_listen(self, ws_url: str):
        """Verbindet sich mit HA WebSocket und verarbeitet Events."""
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                # Auth
                auth_msg = await ws.receive_json()
                if auth_msg.get("type") == "auth_required":
                    await ws.send_json({
                        "type": "auth",
                        "access_token": settings.ha_token,
                    })
                    auth_result = await ws.receive_json()
                    if auth_result.get("type") != "auth_ok":
                        logger.error("HA WebSocket Auth fehlgeschlagen")
                        return

                logger.info("HA WebSocket verbunden")

                # Events abonnieren
                await ws.send_json({
                    "id": 1,
                    "type": "subscribe_events",
                    "event_type": "state_changed",
                })

                # MindHome Events abonnieren
                await ws.send_json({
                    "id": 2,
                    "type": "subscribe_events",
                    "event_type": "mindhome_event",
                })

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "event":
                            await self._handle_event(data.get("event", {}))
                    elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                        break

    async def _handle_event(self, event: dict):
        """Verarbeitet ein HA Event und entscheidet ob gemeldet werden soll."""
        event_type = event.get("event_type", "")
        event_data = event.get("data", {})

        if event_type == "state_changed":
            await self._handle_state_change(event_data)
        elif event_type == "mindhome_event":
            await self._handle_mindhome_event(event_data)

    async def _handle_state_change(self, data: dict):
        """Verarbeitet HA State-Change Events."""
        entity_id = data.get("entity_id", "")
        new_state = data.get("new_state", {})
        old_state = data.get("old_state", {})

        if not new_state or not old_state:
            return

        new_val = new_state.get("state", "")
        old_val = old_state.get("state", "")

        if new_val == old_val:
            return

        # Alarmsystem
        if entity_id.startswith("alarm_control_panel.") and new_val == "triggered":
            await self._notify("alarm_triggered", CRITICAL, {
                "entity": entity_id,
                "state": new_val,
            })

        # Rauchmelder
        elif entity_id.startswith("binary_sensor.smoke") and new_val == "on":
            await self._notify("smoke_detected", CRITICAL, {
                "entity": entity_id,
            })

        # Wassersensor
        elif entity_id.startswith("binary_sensor.water") and new_val == "on":
            await self._notify("water_leak", CRITICAL, {
                "entity": entity_id,
            })

        # Tuerklingel
        elif "doorbell" in entity_id and new_val == "on":
            await self._notify("doorbell", MEDIUM, {
                "entity": entity_id,
            })

        # Person tracker
        elif entity_id.startswith("person."):
            name = new_state.get("attributes", {}).get("friendly_name", entity_id)
            if new_val == "home" and old_val != "home":
                await self._notify("person_arrived", MEDIUM, {
                    "person": name,
                })
            elif old_val == "home" and new_val != "home":
                await self._notify("person_left", MEDIUM, {
                    "person": name,
                })

        # Waschmaschine/Trockner (Power-Sensor faellt unter Schwellwert)
        elif "washer" in entity_id or "waschmaschine" in entity_id:
            if entity_id.startswith("sensor.") and new_val.replace(".", "").isdigit():
                if float(old_val or "0") > 10 and float(new_val) < 5:
                    await self._notify("washer_done", MEDIUM, {})

    async def _handle_mindhome_event(self, data: dict):
        """Verarbeitet MindHome-spezifische Events."""
        event_name = data.get("event", "")
        urgency = data.get("urgency", MEDIUM)
        await self._notify(event_name, urgency, data)

    async def _notify(self, event_type: str, urgency: str, data: dict):
        """Prueft ob gemeldet werden soll und erzeugt Meldung."""

        # Autonomie-Level pruefen
        if urgency != CRITICAL:
            level = self.brain.autonomy.current_level
            if level < 2:  # Level 1 = nur Befehle
                return

        # Cooldown pruefen
        if urgency not in (CRITICAL, HIGH):
            last_time = await self.brain.memory.get_last_notification_time(event_type)
            if last_time:
                last_dt = datetime.fromisoformat(last_time)
                if datetime.now() - last_dt < timedelta(seconds=self.cooldown):
                    return

        # Feedback-Score pruefen (zu oft ignoriert?)
        if urgency == LOW:
            score = await self.brain.memory.get_feedback_score(event_type)
            if score < 0.2:
                return

        # Aktive Stille-Szene pruefen
        if urgency != CRITICAL:
            context = await self.brain.context_builder.build()
            active_scenes = context.get("house", {}).get("active_scenes", [])
            if any(s.lower() in self.silence_scenes for s in active_scenes):
                return

        # Meldung generieren
        description = self.event_handlers.get(event_type, (MEDIUM, event_type))[1]
        prompt = self._build_notification_prompt(event_type, description, data, urgency)

        try:
            response = await self.brain.ollama.chat(
                messages=[
                    {"role": "system", "content": self._get_notification_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                model=settings.model_fast,
            )

            text = response.get("message", {}).get("content", description)

            # WebSocket: Proaktive Meldung senden
            await emit_proactive(text, event_type, urgency)

            # Cooldown setzen
            await self.brain.memory.set_last_notification_time(event_type)

            logger.info("Proaktive Meldung [%s/%s]: %s", event_type, urgency, text)

        except Exception as e:
            logger.error("Fehler bei proaktiver Meldung: %s", e)

    def _get_notification_system_prompt(self) -> str:
        return """Du bist der MindHome Assistant. Formuliere eine KURZE proaktive Meldung.
Maximal 1-2 Saetze. Direkt, keine Floskeln. Deutsch.
Beispiele:
- "Jemand hat geklingelt."
- "Waschmaschine ist fertig."
- "Lisa ist gerade angekommen."
- "Achtung: Rauch im Keller erkannt!"
"""

    def _build_notification_prompt(
        self, event_type: str, description: str, data: dict, urgency: str
    ) -> str:
        parts = [f"Event: {description}"]

        if "person" in data:
            parts.append(f"Person: {data['person']}")
        if "entity" in data:
            parts.append(f"Entity: {data['entity']}")

        parts.append(f"Dringlichkeit: {urgency}")
        parts.append("Formuliere eine kurze Meldung fuer den Bewohner.")

        return "\n".join(parts)
