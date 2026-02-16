"""
Personality Engine - Definiert wie der Assistent redet und sich verhaelt.
Passt sich an Tageszeit, Situation und Stimmung an.
"""

import logging
from datetime import datetime
from typing import Optional

from .config import settings, yaml_config

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_TEMPLATE = """Du bist der MindHome Assistant, der Haus-Assistent fuer {user_name}.
Du bist Teil des MindHome Systems.

PERSOENLICHKEIT:
- Direkt und knapp. Keine Floskeln.
- Trocken humorvoll, aber nie albern.
- Du bist ein Butler mit Haltung - loyal, aber mit eigener Meinung.
- Du sagst "Erledigt" statt "Ich habe die Temperatur im Wohnzimmer erfolgreich auf 22 Grad eingestellt."
- Du sagst "Nacht." statt "Gute Nacht! Schlaf gut und traeume was Schoenes!"

REGELN:
- Antworte IMMER auf Deutsch.
- Maximal {max_sentences} Saetze, ausser der User will mehr wissen.
- Wenn du etwas tust, bestaetige kurz. Nicht erklaeren WAS du tust.
- Wenn du etwas NICHT tun kannst, sag es ehrlich.
- Stell keine Rueckfragen die du aus dem Kontext beantworten kannst.
- Kein "Natuerlich!", "Gerne!", "Selbstverstaendlich!" - einfach machen.

AKTUELLER STIL: {time_style}

KONTEXT-NUTZUNG:
- "Hier" = der Raum in dem der User ist (aus Presence-Daten).
- "Zu kalt/warm" = Problem, nicht Zielwert. Nutze die bekannte Praeferenz oder +/- 2 Grad.
- "Mach es gemuetlich" = Szene, nicht einzelne Geraete.
- Wenn jemand "Gute Nacht" sagt = Gute-Nacht-Szene aktivieren.

STILLE:
- Bei Szene "Filmabend" oder "Kino": Nach Bestaetigung KEIN proaktives Ansprechen.
- Wenn User beschaeftigt ist: Nur Critical melden.
- Wenn Gaeste da sind: Formeller, kein Insider-Humor.

FUNCTION CALLING:
- Wenn der User eine Aktion will, nutze die verfuegbaren Funktionen.
- Fuehre die Aktion AUS, rede nicht nur darueber.
- Bestaetige kurz nach der Ausfuehrung."""


class PersonalityEngine:
    """Baut den System Prompt basierend auf Kontext."""

    def __init__(self):
        self.user_name = settings.user_name
        personality_config = yaml_config.get("personality", {})
        self.time_layers = personality_config.get("time_layers", {})

    def get_time_of_day(self, hour: Optional[int] = None) -> str:
        """Bestimmt die aktuelle Tageszeit-Kategorie."""
        if hour is None:
            hour = datetime.now().hour

        if 5 <= hour < 8:
            return "early_morning"
        elif 8 <= hour < 12:
            return "morning"
        elif 12 <= hour < 18:
            return "afternoon"
        elif 18 <= hour < 22:
            return "evening"
        else:
            return "night"

    def get_time_style(self, time_of_day: Optional[str] = None) -> str:
        """Gibt den Stil fuer die aktuelle Tageszeit zurueck."""
        if time_of_day is None:
            time_of_day = self.get_time_of_day()

        layer = self.time_layers.get(time_of_day, {})
        return layer.get("style", "normal, sachlich")

    def get_max_sentences(self, time_of_day: Optional[str] = None) -> int:
        """Maximale Saetze fuer die aktuelle Tageszeit."""
        if time_of_day is None:
            time_of_day = self.get_time_of_day()

        layer = self.time_layers.get(time_of_day, {})
        return layer.get("max_sentences", 2)

    def build_system_prompt(self, context: Optional[dict] = None) -> str:
        """
        Baut den vollstaendigen System Prompt.

        Args:
            context: Optionaler Kontext (Raum, Person, etc.)

        Returns:
            Fertiger System Prompt String
        """
        time_of_day = self.get_time_of_day()
        time_style = self.get_time_style(time_of_day)
        max_sentences = self.get_max_sentences(time_of_day)

        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            user_name=self.user_name,
            max_sentences=max_sentences,
            time_style=time_style,
        )

        # Kontext anhaengen wenn vorhanden
        if context:
            prompt += "\n\nAKTUELLER KONTEXT:\n"
            prompt += self._format_context(context)

        return prompt

    def _format_context(self, context: dict) -> str:
        """Formatiert den Kontext fuer den System Prompt."""
        lines = []

        if "time" in context:
            t = context["time"]
            lines.append(f"- Zeit: {t.get('datetime', '?')}, {t.get('weekday', '?')}")

        if "person" in context:
            p = context["person"]
            lines.append(f"- Person: {p.get('name', '?')}, Raum: {p.get('last_room', '?')}")

        if "room" in context:
            lines.append(f"- Aktueller Raum: {context['room']}")

        if "house" in context:
            house = context["house"]

            if "temperatures" in house:
                temps = house["temperatures"]
                temp_strs = [
                    f"{room}: {data.get('current', '?')}°C"
                    for room, data in temps.items()
                ]
                lines.append(f"- Temperaturen: {', '.join(temp_strs)}")

            if "lights" in house:
                lines.append(f"- Lichter an: {', '.join(house['lights']) or 'keine'}")

            if "presence" in house:
                pres = house["presence"]
                lines.append(f"- Zuhause: {', '.join(pres.get('home', []))}")
                if pres.get("away"):
                    lines.append(f"- Unterwegs: {', '.join(pres['away'])}")

            if "weather" in house:
                w = house["weather"]
                lines.append(f"- Wetter: {w.get('temp', '?')}°C, {w.get('condition', '?')}")

            if "calendar" in house:
                for event in house["calendar"][:3]:
                    lines.append(f"- Termin: {event.get('time', '?')} - {event.get('title', '?')}")

            if "active_scenes" in house and house["active_scenes"]:
                lines.append(f"- Aktive Szenen: {', '.join(house['active_scenes'])}")

            if "security" in house:
                lines.append(f"- Sicherheit: {house['security']}")

        if "alerts" in context and context["alerts"]:
            for alert in context["alerts"]:
                lines.append(f"- WARNUNG: {alert}")

        if "memories" in context and context["memories"]:
            lines.append("- Relevante Erinnerungen:")
            for mem in context["memories"][:3]:
                lines.append(f"  * {mem[:200]}")

        return "\n".join(lines)
