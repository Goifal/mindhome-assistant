"""
Action Planner (Phase 4) - Plant und fuehrt komplexe Multi-Step Aktionen aus.

Erkennt komplexe Anfragen die mehrere Schritte brauchen und fuehrt sie
iterativ aus: LLM plant -> Aktionen ausfuehren -> Ergebnisse zurueck an LLM
-> weiter planen -> bis fertig.

Beispiele:
  "Mach alles fertig fuer morgen frueh"
  -> Kalender checken, Wecker stellen, Klima Nachtmodus, Kaffee-Timer

  "Ich gehe fuer 3 Tage weg"
  -> Away-Modus, Heizung runter, Rolllaeden zu, Alarm scharf
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from .function_calling import ASSISTANT_TOOLS, FunctionExecutor
from .function_validator import FunctionValidator
from .ollama_client import OllamaClient
from .websocket import emit_action

logger = logging.getLogger(__name__)

# Maximale Iterationen (LLM-Runden) um Endlosschleifen zu verhindern
MAX_ITERATIONS = 5

# Keywords die auf komplexe Anfragen hindeuten
COMPLEX_KEYWORDS = [
    "alles", "fertig machen", "vorbereiten",
    "gehe weg", "fahre weg", "verreise", "urlaub",
    "routine", "morgenroutine", "abendroutine",
    "wenn ich", "falls ich", "bevor ich",
    "zuerst", "danach", "und dann", "ausserdem",
    "komplett", "ueberall", "in allen",
    "party", "besuch kommt", "gaeste",
]

# Prompt fuer den Action Planner
PLANNER_SYSTEM_PROMPT = """Du bist der MindHome Action Planner.
Deine Aufgabe: Komplexe Anfragen in konkrete Aktionen umsetzen.

REGELN:
- Nutze die verfuegbaren Tools um Aktionen auszufuehren.
- Fuehre ALLE noetige Schritte aus, nicht nur den ersten.
- Wenn du Informationen brauchst (z.B. Kalender), frage sie zuerst ab.
- Ergebnisse vorheriger Schritte nutzen um naechste Schritte zu planen.
- Am Ende: Kurze Zusammenfassung auf Deutsch (max 2-3 Saetze).
- Antworte IMMER auf Deutsch.
- Sei knapp. Butler-Stil. Kein Geschwafel."""


@dataclass
class PlanStep:
    """Ein einzelner Schritt im Plan."""
    function: str
    args: dict
    result: Optional[dict] = None
    status: str = "pending"  # pending, running, done, failed, blocked


@dataclass
class ActionPlan:
    """Ein kompletter Aktionsplan."""
    request: str
    steps: list[PlanStep] = field(default_factory=list)
    summary: str = ""
    iterations: int = 0
    needs_confirmation: bool = False
    confirmation_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "request": self.request,
            "steps": [
                {
                    "function": s.function,
                    "args": s.args,
                    "result": s.result,
                    "status": s.status,
                }
                for s in self.steps
            ],
            "summary": self.summary,
            "iterations": self.iterations,
            "needs_confirmation": self.needs_confirmation,
            "confirmation_reasons": self.confirmation_reasons,
        }


class ActionPlanner:
    """Plant und fuehrt komplexe Multi-Step Aktionen aus."""

    def __init__(
        self,
        ollama: OllamaClient,
        executor: FunctionExecutor,
        validator: FunctionValidator,
    ):
        self.ollama = ollama
        self.executor = executor
        self.validator = validator
        self._last_plan: Optional[ActionPlan] = None

    def is_complex_request(self, text: str) -> bool:
        """
        Erkennt ob eine Anfrage komplex ist und den Planner braucht.

        Heuristik:
        - Enthaelt Keywords fuer komplexe Aktionen
        - Enthaelt mehrere Befehle (und/dann/ausserdem)
        """
        text_lower = text.lower()
        return any(kw in text_lower for kw in COMPLEX_KEYWORDS)

    async def plan_and_execute(
        self,
        text: str,
        system_prompt: str,
        context: dict,
        messages: list[dict],
    ) -> dict:
        """
        Plant und fuehrt eine komplexe Anfrage aus.

        Args:
            text: User-Anfrage
            system_prompt: Basis-System-Prompt (inkl. Persoenlichkeit + Memory)
            context: Aktueller Kontext
            messages: Bisherige Nachrichten (History)

        Returns:
            Dict mit response, actions, plan
        """
        plan = ActionPlan(request=text)

        # System Prompt fuer Planner erweitern
        planner_prompt = system_prompt + "\n\n" + PLANNER_SYSTEM_PROMPT

        # Nachrichten fuer den Planner aufbauen
        planner_messages = [{"role": "system", "content": planner_prompt}]
        # History uebernehmen (ohne System Prompt)
        for msg in messages:
            if msg["role"] != "system":
                planner_messages.append(msg)

        all_actions = []

        # Iterative Ausfuehrung: LLM -> Tools -> Ergebnisse -> LLM -> ...
        for iteration in range(MAX_ITERATIONS):
            plan.iterations = iteration + 1

            logger.info("Action Planner: Iteration %d", iteration + 1)

            # LLM aufrufen (mit Tools + Kontext der bisherigen Ergebnisse)
            response = await self.ollama.chat(
                messages=planner_messages,
                model="qwen2.5:14b",  # Immer smart model fuer Planung
                tools=ASSISTANT_TOOLS,
                max_tokens=512,
            )

            if "error" in response:
                logger.error("Planner LLM Fehler: %s", response["error"])
                plan.summary = "Fehler bei der Planung."
                break

            message = response.get("message", {})
            response_text = message.get("content", "")
            tool_calls = message.get("tool_calls", [])

            # Keine weiteren Tool Calls -> LLM ist fertig
            if not tool_calls:
                plan.summary = response_text
                logger.info("Action Planner fertig nach %d Iterationen", iteration + 1)
                break

            # Tool Calls ausfuehren
            tool_results = []
            for tool_call in tool_calls:
                func = tool_call.get("function", {})
                func_name = func.get("name", "")
                func_args = func.get("arguments", {})

                step = PlanStep(function=func_name, args=func_args)

                # Validierung
                validation = self.validator.validate(func_name, func_args)
                if not validation.ok:
                    if validation.needs_confirmation:
                        step.status = "blocked"
                        step.result = {"needs_confirmation": True, "reason": validation.reason}
                        plan.needs_confirmation = True
                        plan.confirmation_reasons.append(validation.reason)
                        tool_results.append(
                            f"BLOCKIERT: {func_name} braucht Bestaetigung - {validation.reason}"
                        )
                    else:
                        step.status = "failed"
                        step.result = {"success": False, "message": validation.reason}
                        tool_results.append(
                            f"FEHLER: {func_name} - {validation.reason}"
                        )
                    plan.steps.append(step)
                    all_actions.append({
                        "function": func_name,
                        "args": func_args,
                        "result": step.result,
                    })
                    continue

                # Ausfuehren
                step.status = "running"
                result = await self.executor.execute(func_name, func_args)
                step.result = result
                step.status = "done" if result.get("success", False) else "failed"

                plan.steps.append(step)
                all_actions.append({
                    "function": func_name,
                    "args": func_args,
                    "result": result,
                })

                # WebSocket: Aktion melden
                await emit_action(func_name, func_args, result)

                tool_results.append(
                    f"{func_name}: {result.get('message', 'OK')}"
                )

                logger.info(
                    "Planner Step: %s(%s) -> %s",
                    func_name, func_args, result.get("message", ""),
                )

            # Ergebnisse zurueck an LLM fuer naechste Iteration
            # Aktuelle Antwort des LLM als assistant message hinzufuegen
            planner_messages.append({
                "role": "assistant",
                "content": response_text or "",
                "tool_calls": tool_calls,
            })
            # Tool-Ergebnisse als tool response
            planner_messages.append({
                "role": "tool",
                "content": "\n".join(tool_results),
            })

        else:
            # Max Iterations erreicht
            logger.warning("Action Planner: Max Iterations erreicht")
            if not plan.summary:
                plan.summary = "Plan ausgefuehrt."

        # Fallback-Summary wenn keins vorhanden
        if not plan.summary and plan.steps:
            successful = sum(1 for s in plan.steps if s.status == "done")
            total = len(plan.steps)
            plan.summary = f"{successful} von {total} Aktionen ausgefuehrt."

        self._last_plan = plan

        return {
            "response": plan.summary,
            "actions": all_actions,
            "plan": plan.to_dict(),
        }

    def get_last_plan(self) -> Optional[dict]:
        """Gibt den letzten ausgefuehrten Plan zurueck."""
        if self._last_plan:
            return self._last_plan.to_dict()
        return None
