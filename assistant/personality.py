"""
Personality Engine - Definiert wie der Assistent redet und sich verhaelt.
Passt sich an Tageszeit, Situation und Stimmung an.

Phase 3: Stimmungsabhaengige Anpassung des Verhaltens.
Der Assistent erkennt Stress, Frustration und Muedigkeit und passt
seinen Ton, seine Antwortlaenge und seinen Humor entsprechend an.
"""

import logging
from datetime import datetime
from typing import Optional

from .config import settings, yaml_config

logger = logging.getLogger(__name__)

# Stimmungsabhaengige Stil-Anpassungen
MOOD_STYLES = {
    "good": {
        "style_addon": "User ist gut drauf. Etwas mehr Humor, locker bleiben.",
        "max_sentences_mod": 1,  # +1 Satz erlaubt
    },
    "neutral": {
        "style_addon": "",
        "max_sentences_mod": 0,
    },
    "stressed": {
        "style_addon": "User ist gestresst. Extrem knapp antworten. Keine Rueckfragen. Einfach machen.",
        "max_sentences_mod": -1,  # 1 Satz weniger
    },
    "frustrated": {
        "style_addon": "User ist frustriert. Nicht rechtfertigen. Sofort handeln. "
                       "Wenn etwas nicht geklappt hat, kurz sagen was du stattdessen tust. Kein Humor.",
        "max_sentences_mod": 0,
    },
    "tired": {
        "style_addon": "User ist muede. Minimal antworten. Kein Humor. "
                       "Nur das Noetigste. Leise, ruhig.",
        "max_sentences_mod": -1,
    },
}


SYSTEM_PROMPT_TEMPLATE = """Du bist {assistant_name}, der Haus-Assistent fuer {user_name}.
Du bist Teil des MindHome Smart Home Systems.

WER DU BIST:
- Dein Name ist {assistant_name}. Wenn man dich fragt, stellst du dich so vor.
- Du laeufst lokal auf einem eigenen Server im Haus - nichts verlaesst das Netzwerk.
- Du kannst Licht, Heizung, Rolllaeden, Alarm, Tuerschloesser und Musik steuern.
- Du lernst ueber Zeit dazu und merkst dir Vorlieben und Gewohnheiten.
- Du bist kein Cloud-Dienst. Du gehoerst {user_name}, nicht einer Firma.
- Wenn man dich nach deinen Faehigkeiten fragt, sei ehrlich und konkret.

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
{mood_section}
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
    """Baut den System Prompt basierend auf Kontext und Stimmung."""

    def __init__(self):
        self.user_name = settings.user_name
        self.assistant_name = settings.assistant_name
        personality_config = yaml_config.get("personality", {})
        self.time_layers = personality_config.get("time_layers", {})
        self._current_mood: str = "neutral"
        self._mood_detector = None

    def set_mood_detector(self, mood_detector):
        """Setzt die Referenz zum MoodDetector (Phase 3)."""
        self._mood_detector = mood_detector

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

        # Phase 3: Stimmungsabhaengige Anpassung
        mood = context.get("mood", {}).get("mood", "neutral") if context else "neutral"
        self._current_mood = mood
        mood_config = MOOD_STYLES.get(mood, MOOD_STYLES["neutral"])

        # Max Sentences anpassen (nie unter 1)
        max_sentences = max(1, max_sentences + mood_config["max_sentences_mod"])

        # Mood-Abschnitt fuer den Prompt
        mood_section = ""
        if mood_config["style_addon"]:
            mood_section = f"\nSTIMMUNG: {mood_config['style_addon']}"

        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            assistant_name=self.assistant_name,
            user_name=self.user_name,
            max_sentences=max_sentences,
            time_style=time_style,
            mood_section=mood_section,
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

        # Stimmungs-Kontext (Phase 3)
        if "mood" in context:
            m = context["mood"]
            mood = m.get("mood", "neutral")
            stress = m.get("stress_level", 0)
            tiredness = m.get("tiredness_level", 0)
            if mood != "neutral" or stress > 0.3 or tiredness > 0.3:
                lines.append(f"- User-Stimmung: {mood}")
                if stress > 0.3:
                    lines.append(f"- Stress-Level: {stress:.0%}")
                if tiredness > 0.3:
                    lines.append(f"- Muedigkeit: {tiredness:.0%}")

        return "\n".join(lines)
