"""
Function Calling - Definiert und fuehrt Funktionen aus die der Assistent nutzen kann.
MindHome Assistant ruft ueber diese Funktionen Home Assistant Aktionen aus.
"""

import logging
import time
import unicodedata
from typing import Optional

from .ha_client import HomeAssistantClient

logger = logging.getLogger(__name__)


# ----- Umlaut-Normalisierung -----

_UMLAUT_MAP = str.maketrans({
    "\u00e4": "ae", "\u00f6": "oe", "\u00fc": "ue", "\u00df": "ss",
    "\u00c4": "Ae", "\u00d6": "Oe", "\u00dc": "Ue",
})


def normalize_for_search(text: str) -> str:
    """Normalisiert Text fuer Entity-Suche (Umlaute, Spaces, Unicode)."""
    normalized = text.translate(_UMLAUT_MAP)
    normalized = normalized.lower().replace(" ", "_")
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    return normalized


# ----- Entity Cache -----

class EntityCache:
    """TTL-Cache fuer HA Entity States."""

    def __init__(self, ttl: int = 30):
        self._cache: list[dict] = []
        self._timestamp: float = 0
        self._ttl = ttl

    @property
    def is_valid(self) -> bool:
        return bool(self._cache) and (time.monotonic() - self._timestamp) < self._ttl

    def get(self) -> list[dict]:
        return self._cache if self.is_valid else []

    def set(self, states: list[dict]):
        self._cache = states
        self._timestamp = time.monotonic()

    def invalidate(self):
        self._cache = []
        self._timestamp = 0


# ----- Ollama Tool-Definitionen (Qwen 2.5 Function Calling Format) -----

ASSISTANT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_light",
            "description": "Licht in einem Raum ein-/ausschalten oder dimmen",
            "parameters": {
                "type": "object",
                "properties": {
                    "room": {
                        "type": "string",
                        "description": "Raumname (z.B. wohnzimmer, schlafzimmer, buero)",
                    },
                    "state": {
                        "type": "string",
                        "enum": ["on", "off"],
                        "description": "Ein oder aus",
                    },
                    "brightness": {
                        "type": "integer",
                        "description": "Helligkeit 0-100 Prozent (optional)",
                    },
                },
                "required": ["room", "state"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_climate",
            "description": "Temperatur in einem Raum aendern",
            "parameters": {
                "type": "object",
                "properties": {
                    "room": {
                        "type": "string",
                        "description": "Raumname",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Zieltemperatur in Grad Celsius",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["heat", "cool", "auto", "off"],
                        "description": "Heizmodus (optional)",
                    },
                },
                "required": ["room", "temperature"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "activate_scene",
            "description": "Eine Szene aktivieren (z.B. filmabend, gute_nacht, gemuetlich)",
            "parameters": {
                "type": "object",
                "properties": {
                    "scene": {
                        "type": "string",
                        "description": "Name der Szene",
                    },
                },
                "required": ["scene"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_cover",
            "description": "Rollladen oder Jalousie steuern",
            "parameters": {
                "type": "object",
                "properties": {
                    "room": {
                        "type": "string",
                        "description": "Raumname",
                    },
                    "position": {
                        "type": "integer",
                        "description": "Position 0 (zu) bis 100 (offen)",
                    },
                },
                "required": ["room", "position"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_media",
            "description": "Musik oder Medien steuern",
            "parameters": {
                "type": "object",
                "properties": {
                    "room": {
                        "type": "string",
                        "description": "Raumname",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "stop", "next", "previous"],
                        "description": "Medien-Aktion",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "Alarmanlage steuern",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["arm_home", "arm_away", "disarm"],
                        "description": "Alarm-Modus",
                    },
                },
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lock_door",
            "description": "Tuer ver- oder entriegeln",
            "parameters": {
                "type": "object",
                "properties": {
                    "door": {
                        "type": "string",
                        "description": "Name der Tuer",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["lock", "unlock"],
                        "description": "Verriegeln oder entriegeln",
                    },
                },
                "required": ["door", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": "Benachrichtigung senden",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Nachricht",
                    },
                    "target": {
                        "type": "string",
                        "enum": ["phone", "speaker", "dashboard"],
                        "description": "Ziel der Benachrichtigung",
                    },
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_state",
            "description": "Status einer Home Assistant Entity abfragen (z.B. Sensor, Schalter, Thermostat)",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Entity-ID (z.B. sensor.temperatur_buero, switch.steckdose_kueche)",
                    },
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_presence_mode",
            "description": "Anwesenheitsmodus des Hauses setzen",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["home", "away", "sleep", "vacation"],
                        "description": "Anwesenheitsmodus",
                    },
                },
                "required": ["mode"],
            },
        },
    },
]


class FunctionExecutor:
    """Fuehrt Function Calls des Assistenten aus."""

    def __init__(self, ha_client: HomeAssistantClient):
        self.ha = ha_client
        self._cache = EntityCache(ttl=30)

    async def execute(self, function_name: str, arguments: dict) -> dict:
        """Fuehrt eine Funktion aus."""
        handler = getattr(self, f"_exec_{function_name}", None)
        if not handler:
            return {"success": False, "message": f"Unbekannte Funktion: {function_name}"}

        try:
            return await handler(arguments)
        except Exception as e:
            logger.error("Fehler bei %s: %s", function_name, e)
            return {"success": False, "message": f"Fehler: {e}"}

    async def _get_cached_states(self) -> list[dict]:
        """Holt States aus Cache oder von HA."""
        cached = self._cache.get()
        if cached:
            return cached
        states = await self.ha.get_states()
        if states:
            self._cache.set(states)
        return states or []

    def invalidate_cache(self):
        self._cache.invalidate()

    async def _exec_set_light(self, args: dict) -> dict:
        room = args["room"]
        state = args["state"]
        entity_id = await self._find_entity("light", room)
        if not entity_id:
            return {"success": False, "message": f"Kein Licht in '{room}' gefunden"}

        service_data = {"entity_id": entity_id}
        if "brightness" in args and state == "on":
            service_data["brightness_pct"] = args["brightness"]

        service = "turn_on" if state == "on" else "turn_off"
        success = await self.ha.call_service("light", service, service_data)
        if success:
            self.invalidate_cache()
        return {"success": success, "message": f"Licht {room} {state}"}

    async def _exec_set_climate(self, args: dict) -> dict:
        room = args["room"]
        temp = args["temperature"]
        entity_id = await self._find_entity("climate", room)
        if not entity_id:
            return {"success": False, "message": f"Kein Thermostat in '{room}' gefunden"}

        service_data = {"entity_id": entity_id, "temperature": temp}
        if "mode" in args:
            service_data["hvac_mode"] = args["mode"]

        success = await self.ha.call_service("climate", "set_temperature", service_data)
        if success:
            self.invalidate_cache()
        return {"success": success, "message": f"{room} auf {temp}\u00b0C"}

    async def _exec_activate_scene(self, args: dict) -> dict:
        scene = args["scene"]
        entity_id = await self._find_entity("scene", scene)
        if not entity_id:
            entity_id = f"scene.{scene}"

        success = await self.ha.call_service(
            "scene", "turn_on", {"entity_id": entity_id}
        )
        if success:
            self.invalidate_cache()
        return {"success": success, "message": f"Szene '{scene}' aktiviert"}

    async def _exec_set_cover(self, args: dict) -> dict:
        room = args["room"]
        position = args["position"]
        entity_id = await self._find_entity("cover", room)
        if not entity_id:
            return {"success": False, "message": f"Kein Rollladen in '{room}' gefunden"}

        success = await self.ha.call_service(
            "cover", "set_cover_position",
            {"entity_id": entity_id, "position": position},
        )
        return {"success": success, "message": f"Rollladen {room} auf {position}%"}

    async def _exec_play_media(self, args: dict) -> dict:
        action = args["action"]
        room = args.get("room")
        entity_id = await self._find_entity("media_player", room) if room else None

        if not entity_id:
            states = await self._get_cached_states()
            for s in states:
                if s.get("entity_id", "").startswith("media_player."):
                    entity_id = s["entity_id"]
                    break

        if not entity_id:
            return {"success": False, "message": "Kein Media Player gefunden"}

        service_map = {
            "play": "media_play",
            "pause": "media_pause",
            "stop": "media_stop",
            "next": "media_next_track",
            "previous": "media_previous_track",
        }
        service = service_map.get(action, "media_play")
        success = await self.ha.call_service(
            "media_player", service, {"entity_id": entity_id}
        )
        return {"success": success, "message": f"Medien: {action}"}

    async def _exec_set_alarm(self, args: dict) -> dict:
        mode = args["mode"]
        states = await self._get_cached_states()
        entity_id = None
        for s in states:
            if s.get("entity_id", "").startswith("alarm_control_panel."):
                entity_id = s["entity_id"]
                break

        if not entity_id:
            return {"success": False, "message": "Keine Alarmanlage gefunden"}

        service_map = {
            "arm_home": "alarm_arm_home",
            "arm_away": "alarm_arm_away",
            "disarm": "alarm_disarm",
        }
        service = service_map.get(mode, mode)
        success = await self.ha.call_service(
            "alarm_control_panel", service, {"entity_id": entity_id}
        )
        if success:
            self.invalidate_cache()
        return {"success": success, "message": f"Alarm: {mode}"}

    async def _exec_lock_door(self, args: dict) -> dict:
        door = args["door"]
        action = args["action"]
        entity_id = await self._find_entity("lock", door)
        if not entity_id:
            return {"success": False, "message": f"Kein Schloss '{door}' gefunden"}

        success = await self.ha.call_service(
            "lock", action, {"entity_id": entity_id}
        )
        if success:
            self.invalidate_cache()
        return {"success": success, "message": f"Tuer {door}: {action}"}

    async def _exec_send_notification(self, args: dict) -> dict:
        message = args["message"]
        target = args.get("target", "phone")

        if target == "phone":
            success = await self.ha.call_service(
                "notify", "notify", {"message": message}
            )
        elif target == "speaker":
            success = await self.ha.call_service(
                "tts", "speak", {"message": message, "language": "de"}
            )
        else:
            success = await self.ha.call_service(
                "persistent_notification", "create", {"message": message}
            )
        return {"success": success, "message": "Benachrichtigung gesendet"}

    async def _exec_get_entity_state(self, args: dict) -> dict:
        entity_id = args["entity_id"]
        state = await self.ha.get_state(entity_id)
        if not state:
            return {"success": False, "message": f"Entity '{entity_id}' nicht gefunden"}

        current = state.get("state", "unknown")
        attrs = state.get("attributes", {})
        friendly_name = attrs.get("friendly_name", entity_id)
        unit = attrs.get("unit_of_measurement", "")

        display = f"{friendly_name}: {current}"
        if unit:
            display += f" {unit}"

        return {"success": True, "message": display, "state": current, "attributes": attrs}

    async def _exec_set_presence_mode(self, args: dict) -> dict:
        mode = args["mode"]

        states = await self._get_cached_states()
        entity_id = None
        for s in states:
            eid = s.get("entity_id", "")
            if eid.startswith("input_select.") and any(
                kw in eid for kw in ("presence", "anwesenheit", "presence_mode")
            ):
                entity_id = eid
                break

        if entity_id:
            success = await self.ha.call_service(
                "input_select", "select_option",
                {"entity_id": entity_id, "option": mode},
            )
            return {"success": success, "message": f"Anwesenheit: {mode}"}

        success = await self.ha.call_service(
            "event", "fire",
            {"event_type": "mindhome_presence_mode", "event_data": {"mode": mode}},
        )
        if not success:
            success = await self.ha.call_service(
                "input_boolean", "turn_on" if mode == "home" else "turn_off",
                {"entity_id": "input_boolean.zu_hause"},
            )
        return {"success": success, "message": f"Anwesenheit: {mode}"}

    async def _find_entity(self, domain: str, search: str) -> Optional[str]:
        """Findet eine Entity anhand von Domain und Suchbegriff."""
        if not search:
            return None

        states = await self._get_cached_states()
        if not states:
            return None

        search_norm = normalize_for_search(search)

        for state in states:
            entity_id = state.get("entity_id", "")
            if not entity_id.startswith(f"{domain}."):
                continue

            # Match gegen entity_id
            name = entity_id.split(".", 1)[1]
            if search_norm in name:
                return entity_id

            # Match gegen friendly_name (auch normalisiert)
            friendly = state.get("attributes", {}).get("friendly_name", "")
            if friendly and search_norm in normalize_for_search(friendly):
                return entity_id

        return None
