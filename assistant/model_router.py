"""
Model Router - Waehlt das richtige LLM basierend auf der Anfrage
Schnelles Modell fuer einfache Befehle, schlaues fuer komplexe Fragen.
"""

import logging

from .config import settings, yaml_config

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routet Anfragen zum schnellen oder schlauen Modell."""

    def __init__(self):
        self.model_fast = settings.model_fast
        self.model_smart = settings.model_smart

        # Keywords aus settings.yaml laden
        models_config = yaml_config.get("models", {})
        self.fast_keywords = models_config.get("fast_keywords", [
            "licht", "lampe", "temperatur", "heizung", "rollladen",
            "jalousie", "szene", "alarm", "tuer", "gute nacht",
            "guten morgen", "musik", "pause", "stopp", "stop",
            "leiser", "lauter", "an", "aus",
        ])

    def select_model(self, text: str) -> str:
        """
        Waehlt das passende Modell fuer die Anfrage.

        Args:
            text: User-Eingabe

        Returns:
            Modellname fuer Ollama
        """
        text_lower = text.lower().strip()

        # Kurze Befehle -> schnelles Modell
        if len(text_lower.split()) <= 4:
            for keyword in self.fast_keywords:
                if keyword in text_lower:
                    logger.debug("Fast model fuer: '%s' (keyword: %s)", text, keyword)
                    return self.model_fast

        # Fragen -> schlaues Modell
        if any(text_lower.startswith(w) for w in ["was ", "wie ", "warum ", "wann ", "wo ", "wer "]):
            logger.debug("Smart model fuer Frage: '%s'", text)
            return self.model_smart

        # Default: schlaues Modell
        logger.debug("Smart model (default) fuer: '%s'", text)
        return self.model_smart

    def get_model_info(self) -> dict:
        """Gibt Info ueber die konfigurierten Modelle zurueck."""
        return {
            "fast": self.model_fast,
            "smart": self.model_smart,
            "fast_keywords_count": len(self.fast_keywords),
        }
