"""
Memory Extractor - Extrahiert Fakten aus Gespraechen mittels LLM.
Laeuft nach jeder substantiellen Konversation und speichert
extrahierte Fakten im Semantic Memory.
"""

import json
import logging
from typing import Optional

from .ollama_client import OllamaClient
from .semantic_memory import SemanticFact, SemanticMemory

logger = logging.getLogger(__name__)

# Prompt fuer Fakten-Extraktion (deutsch, knapp, strukturiert)
EXTRACTION_PROMPT = """Du bist ein Fakten-Extraktor. Analysiere das folgende Gespraech und extrahiere ALLE relevanten Fakten.

Kategorien:
- preference: Vorlieben und Abneigungen (Temperatur, Licht, Musik, Essen, etc.)
- person: Informationen ueber Personen (Namen, Beziehungen, Berufe)
- habit: Gewohnheiten und Routinen (Aufstehzeit, Joggen, Arbeitszeiten)
- health: Gesundheitsinformationen (Allergien, Unvertraeglichkeiten, Medikamente)
- work: Arbeit und Projekte (Job, Meetings, Deadlines)
- general: Sonstige wichtige Fakten

Regeln:
- Nur KONKRETE Fakten extrahieren, keine Vermutungen.
- Jeder Fakt als eigenstaendiger Satz.
- Person identifizieren (wer sagt/meint das?).
- Keine Fakten ueber das Smart Home System selbst.
- Keine trivialen Befehle ("Licht an") als Fakten speichern.
- NUR Fakten die langfristig relevant sind.

Antworte NUR mit einem JSON-Array. Wenn keine Fakten vorhanden, antworte mit [].

Format:
[
  {"content": "Max bevorzugt 21 Grad im Buero", "category": "preference", "person": "Max"},
  {"content": "Lisa ist die Freundin von Max", "category": "person", "person": "Max"}
]

Gespraech:
{conversation}

Fakten (JSON-Array):"""

# Minimale Konversationslaenge fuer Extraktion
MIN_CONVERSATION_WORDS = 5
# Maximale Konversationslaenge fuer Extraktion (Token-Limit)
MAX_CONVERSATION_LENGTH = 2000


class MemoryExtractor:
    """Extrahiert Fakten aus Gespraechen mittels LLM."""

    def __init__(self, ollama: OllamaClient, semantic_memory: SemanticMemory):
        self.ollama = ollama
        self.semantic = semantic_memory
        self._extraction_model = "qwen2.5:3b"  # Schnelles Modell reicht

    async def extract_and_store(
        self,
        user_text: str,
        assistant_response: str,
        person: str = "unknown",
        context: Optional[dict] = None,
    ) -> list[SemanticFact]:
        """
        Extrahiert Fakten aus einem Gespraech und speichert sie.

        Args:
            user_text: Was der User gesagt hat
            assistant_response: Was der Assistant geantwortet hat
            person: Name der Person
            context: Optionaler Kontext (Raum, Zeit, etc.)

        Returns:
            Liste der extrahierten und gespeicherten Fakten
        """
        # Pruefen ob Extraktion sinnvoll ist
        if not self._should_extract(user_text, assistant_response):
            return []

        # Konversation formatieren
        conversation = self._format_conversation(
            user_text, assistant_response, person, context
        )

        # LLM um Fakten-Extraktion bitten
        raw_facts = await self._call_llm(conversation)
        if not raw_facts:
            return []

        # Fakten parsen und speichern
        stored_facts = []
        for raw in raw_facts:
            content = raw.get("content", "").strip()
            category = raw.get("category", "general").strip()
            fact_person = raw.get("person", person).strip()

            if not content:
                continue

            fact = SemanticFact(
                content=content,
                category=category,
                person=fact_person,
                confidence=0.7,  # Initiale Confidence
                source_conversation=f"User: {user_text[:100]}",
            )

            success = await self.semantic.store_fact(fact)
            if success:
                stored_facts.append(fact)

        if stored_facts:
            logger.info(
                "%d Fakt(en) extrahiert aus Gespraech mit %s",
                len(stored_facts), person,
            )

        return stored_facts

    def _should_extract(self, user_text: str, assistant_response: str) -> bool:
        """Prueeft ob eine Extraktion sinnvoll ist."""
        # Zu kurze Texte ueberspringen
        if len(user_text.split()) < MIN_CONVERSATION_WORDS:
            return False

        # Reine Befehle ueberspringen (kein Fakten-Potenzial)
        command_only = [
            "licht an", "licht aus", "stopp", "stop", "pause",
            "weiter", "lauter", "leiser", "gute nacht", "guten morgen",
        ]
        if user_text.lower().strip() in command_only:
            return False

        return True

    def _format_conversation(
        self,
        user_text: str,
        assistant_response: str,
        person: str,
        context: Optional[dict] = None,
    ) -> str:
        """Formatiert die Konversation fuer den Extraction-Prompt."""
        parts = []

        if person and person != "unknown":
            parts.append(f"Person: {person}")

        if context:
            room = context.get("room", "")
            time_info = context.get("time", {})
            if room:
                parts.append(f"Raum: {room}")
            if time_info:
                parts.append(f"Zeit: {time_info.get('datetime', '')}")

        parts.append(f"{person or 'User'}: {user_text}")
        parts.append(f"Assistant: {assistant_response}")

        conversation = "\n".join(parts)
        # Auf maximale Laenge begrenzen
        return conversation[:MAX_CONVERSATION_LENGTH]

    async def _call_llm(self, conversation: str) -> list[dict]:
        """Ruft das LLM auf um Fakten zu extrahieren."""
        prompt = EXTRACTION_PROMPT.replace("{conversation}", conversation)

        try:
            response = await self.ollama.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self._extraction_model,
                temperature=0.1,  # Niedrige Temperatur = konsistentere Extraktion
                max_tokens=512,
            )

            if "error" in response:
                logger.error("LLM Fehler bei Extraktion: %s", response["error"])
                return []

            content = response.get("message", {}).get("content", "").strip()
            return self._parse_facts(content)

        except Exception as e:
            logger.error("Fehler bei Fakten-Extraktion: %s", e)
            return []

    def _parse_facts(self, llm_output: str) -> list[dict]:
        """Parst die LLM-Antwort in eine Liste von Fakten."""
        # JSON-Array aus der Antwort extrahieren
        text = llm_output.strip()

        # Versuche direktes JSON-Parsing
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return [f for f in result if isinstance(f, dict) and f.get("content")]
            return []
        except json.JSONDecodeError:
            pass

        # Fallback: JSON-Array in der Antwort suchen
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                result = json.loads(text[start:end + 1])
                if isinstance(result, list):
                    return [f for f in result if isinstance(f, dict) and f.get("content")]
            except json.JSONDecodeError:
                pass

        logger.debug("Konnte LLM-Antwort nicht parsen: %s", text[:200])
        return []
