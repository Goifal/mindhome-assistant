"""
MindHome Assistant Brain - Das zentrale Gehirn.
Verbindet alle Komponenten: Context Builder, Model Router, Personality,
Function Calling, Memory und Autonomy.
"""

import json
import logging
from typing import Optional

from .autonomy import AutonomyManager
from .config import settings
from .context_builder import ContextBuilder
from .function_calling import ASSISTANT_TOOLS, FunctionExecutor
from .function_validator import FunctionValidator
from .ha_client import HomeAssistantClient
from .memory import MemoryManager
from .model_router import ModelRouter
from .ollama_client import OllamaClient
from .personality import PersonalityEngine
from .proactive import ProactiveManager
from .websocket import emit_thinking, emit_speaking, emit_action

logger = logging.getLogger(__name__)


class AssistantBrain:
    """Das zentrale Gehirn von MindHome Assistant."""

    def __init__(self):
        # Clients
        self.ha = HomeAssistantClient()
        self.ollama = OllamaClient()

        # Komponenten
        self.context_builder = ContextBuilder(self.ha)
        self.model_router = ModelRouter()
        self.personality = PersonalityEngine()
        self.executor = FunctionExecutor(self.ha)
        self.validator = FunctionValidator()
        self.memory = MemoryManager()
        self.autonomy = AutonomyManager()
        self.proactive = ProactiveManager(self)

    async def initialize(self):
        """Initialisiert alle Komponenten."""
        await self.memory.initialize()
        await self.proactive.start()
        logger.info("MindHome Assistant Brain initialisiert")

    async def process(self, text: str, person: Optional[str] = None) -> dict:
        """
        Verarbeitet eine User-Eingabe.

        Args:
            text: User-Text (z.B. "Mach das Licht aus")
            person: Name der Person (optional)

        Returns:
            Dict mit response, actions, model_used
        """
        logger.info("Input: '%s' (Person: %s)", text, person or "unbekannt")

        # WebSocket: Denk-Status senden
        await emit_thinking()

        # 1. Kontext sammeln
        context = await self.context_builder.build(trigger="voice")
        if person:
            context.setdefault("person", {})["name"] = person

        # 2. Modell waehlen
        model = self.model_router.select_model(text)

        # 3. System Prompt bauen
        system_prompt = self.personality.build_system_prompt(context)

        # 4. Letzte Gespraeche laden (Working Memory)
        recent = await self.memory.get_recent_conversations(limit=5)
        messages = [{"role": "system", "content": system_prompt}]
        for conv in recent:
            messages.append({"role": conv["role"], "content": conv["content"]})
        messages.append({"role": "user", "content": text})

        # 5. LLM aufrufen (mit Function Calling Tools)
        response = await self.ollama.chat(
            messages=messages,
            model=model,
            tools=ASSISTANT_TOOLS,
        )

        if "error" in response:
            logger.error("LLM Fehler: %s", response["error"])
            return {
                "response": "Da stimmt etwas nicht. Ich kann gerade nicht denken.",
                "actions": [],
                "model_used": model,
                "error": response["error"],
            }

        # 6. Antwort verarbeiten
        message = response.get("message", {})
        response_text = message.get("content", "")
        tool_calls = message.get("tool_calls", [])
        executed_actions = []

        # 7. Function Calls ausfuehren
        if tool_calls:
            for tool_call in tool_calls:
                func = tool_call.get("function", {})
                func_name = func.get("name", "")
                func_args = func.get("arguments", {})

                logger.info("Function Call: %s(%s)", func_name, func_args)

                # Validierung
                validation = self.validator.validate(func_name, func_args)
                if not validation.ok:
                    if validation.needs_confirmation:
                        response_text = f"Sicherheitsbestaetigung noetig: {validation.reason}"
                        executed_actions.append({
                            "function": func_name,
                            "args": func_args,
                            "result": "needs_confirmation",
                        })
                        continue
                    else:
                        logger.warning("Validation failed: %s", validation.reason)
                        executed_actions.append({
                            "function": func_name,
                            "args": func_args,
                            "result": f"blocked: {validation.reason}",
                        })
                        continue

                # Ausfuehren
                result = await self.executor.execute(func_name, func_args)
                executed_actions.append({
                    "function": func_name,
                    "args": func_args,
                    "result": result,
                })

                # WebSocket: Aktion melden
                await emit_action(func_name, func_args, result)

            # Wenn Aktionen, aber keine Text-Antwort: Standard-Bestaetigung
            if executed_actions and not response_text:
                if all(a["result"].get("success", False) for a in executed_actions if isinstance(a["result"], dict)):
                    response_text = "Erledigt."
                else:
                    failed = [
                        a["result"].get("message", "")
                        for a in executed_actions
                        if isinstance(a["result"], dict) and not a["result"].get("success", False)
                    ]
                    response_text = f"Problem: {', '.join(failed)}" if failed else "Teilweise erledigt."

        # 8. Im Gedaechtnis speichern
        await self.memory.add_conversation("user", text)
        await self.memory.add_conversation("assistant", response_text)

        # 9. Episode speichern (Langzeitgedaechtnis)
        if len(text.split()) > 3:  # Nur bei substantiellen Gespraechen
            episode = f"User: {text}\nAssistant: {response_text}"
            await self.memory.store_episode(episode, {
                "person": person or "unknown",
                "room": context.get("room", "unknown"),
                "actions": json.dumps([a["function"] for a in executed_actions]),
            })

        result = {
            "response": response_text,
            "actions": executed_actions,
            "model_used": model,
            "context_room": context.get("room", "unbekannt"),
        }
        # WebSocket: Antwort senden
        await emit_speaking(response_text)

        logger.info("Output: '%s' (Aktionen: %d)", response_text, len(executed_actions))
        return result

    async def health_check(self) -> dict:
        """Prueft den Zustand aller Komponenten."""
        ollama_ok = await self.ollama.is_available()
        ha_ok = await self.ha.is_available()

        models = await self.ollama.list_models() if ollama_ok else []

        return {
            "status": "ok" if (ollama_ok and ha_ok) else "degraded",
            "components": {
                "ollama": "connected" if ollama_ok else "disconnected",
                "home_assistant": "connected" if ha_ok else "disconnected",
                "redis": "connected" if self.memory.redis else "disconnected",
                "chromadb": "connected" if self.memory.chroma_collection else "disconnected",
                "proactive": "running" if self.proactive._running else "stopped",
            },
            "models_available": models,
            "autonomy": self.autonomy.get_level_info(),
        }

    async def shutdown(self):
        """Faehrt MindHome Assistant herunter."""
        await self.proactive.stop()
        await self.memory.close()
        logger.info("MindHome Assistant heruntergefahren")
