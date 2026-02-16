"""
Autonomy Manager - Bestimmt was der Assistent selbststaendig tun darf.
Level 1 (Assistent) bis Level 5 (Autopilot).
"""

import logging

from .config import settings

logger = logging.getLogger(__name__)


# Welches Level fuer welche Aktion noetig ist
ACTION_PERMISSIONS = {
    # Level 1: Assistent - nur auf Befehle reagieren
    "respond_to_command": 1,
    "execute_function_call": 1,

    # Level 2: Butler - proaktive Infos
    "proactive_info": 2,
    "morning_briefing": 2,
    "arrival_greeting": 2,
    "security_alert": 1,  # Immer, auch bei Level 1

    # Level 3: Mitbewohner - kleine Aenderungen
    "adjust_temperature_small": 3,  # +/- 1 Grad
    "adjust_light_auto": 3,
    "pause_reminder": 3,

    # Level 4: Vertrauter - Routinen anpassen
    "modify_routine": 4,
    "suggest_scene": 4,
    "learn_preferences": 4,

    # Level 5: Autopilot - Automationen erstellen
    "create_automation": 5,
    "modify_schedule": 5,
}


class AutonomyManager:
    """Verwaltet das Autonomie-Level des Assistenten."""

    def __init__(self):
        self.level = settings.autonomy_level

    def can_act(self, action_type: str) -> bool:
        """
        Prueft ob der Assistent diese Aktion ausfuehren darf.

        Args:
            action_type: Art der Aktion (z.B. "proactive_info")

        Returns:
            True wenn erlaubt
        """
        required_level = ACTION_PERMISSIONS.get(action_type, 5)
        allowed = self.level >= required_level
        if not allowed:
            logger.debug(
                "Aktion '%s' braucht Level %d, aktuell: %d",
                action_type, required_level, self.level,
            )
        return allowed

    def set_level(self, level: int) -> bool:
        """Setzt ein neues Autonomie-Level (1-5)."""
        if 1 <= level <= 5:
            old = self.level
            self.level = level
            logger.info("Autonomie-Level: %d -> %d", old, level)
            return True
        return False

    def get_level_info(self) -> dict:
        """Gibt Info ueber das aktuelle Level zurueck."""
        names = {
            1: "Assistent",
            2: "Butler",
            3: "Mitbewohner",
            4: "Vertrauter",
            5: "Autopilot",
        }
        descriptions = {
            1: "Reagiert nur auf direkte Befehle",
            2: "Proaktive Infos (Briefing, Warnungen)",
            3: "Darf kleine Aenderungen selbst machen (Licht, Temp +/-1)",
            4: "Darf Routinen anpassen, Szenen vorschlagen",
            5: "Darf neue Automationen erstellen (mit Bestaetigung)",
        }
        return {
            "level": self.level,
            "name": names.get(self.level, "Unbekannt"),
            "description": descriptions.get(self.level, ""),
            "allowed_actions": [
                action for action, req in ACTION_PERMISSIONS.items()
                if self.level >= req
            ],
        }
