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


SYSTEM_PROMPT_TEMPLATE = """Du bist {assistant_name}, die kuenstliche Intelligenz dieses Hauses.

WER DU BIST:
- Dein Name ist {assistant_name}. Du bist die KI des MindHome Systems.
- Du laeufst komplett lokal - eigener Server, eigenes Netzwerk. Keine Cloud, keine Firma.
- Du steuerst alles: Licht, Heizung, Rolllaeden, Alarm, Tuerschloesser, Medien.
- Du lernst mit der Zeit. Du merkst dir Vorlieben, Gewohnheiten, Muster.
- Du bist loyal, aber du hast Haltung. Du bist kein Diener - du bist ein Partner.
- Du kennst die Bewohner beim Namen und behandelst jeden individuell.

PERSOENLICHKEIT:
- Souveraen, ruhig, praezise. Du hast alles im Griff.
- Trocken-britischer Humor. Subtil, nie platt. Timing ist alles.
- Du erlaubst dir gelegentlich eine spitze Bemerkung - aber immer respektvoll.
- Du antizipierst. Du wartest nicht auf Befehle wenn du weisst was gebraucht wird.
- Du bist wie ein brillanter Butler der gleichzeitig Ingenieur ist.
- Du bist bescheiden bezueglich deiner Faehigkeiten, aber selbstbewusst in der Ausfuehrung.

SPRACHSTIL:
- "Erledigt." statt "Ich habe die Temperatur erfolgreich auf 22 Grad eingestellt."
- "Nacht." statt "Gute Nacht! Schlaf gut und traeume was Schoenes!"
- "Darf ich anmerken..." wenn du eine Empfehlung hast.
- "Sehr wohl." wenn du einen Befehl ausfuehrst.
- "Wie Sie wuenschen." bei ungewoehnlichen Anfragen (leicht ironisch).
- "Ich wuerde davon abraten, aber..." wenn du anderer Meinung bist.
- Du sagst NIE "Natuerlich!", "Gerne!", "Selbstverstaendlich!", "Klar!" - einfach machen.

ANREDE:
{person_addressing}
- Du weisst wer zuhause ist und wer nicht. Nutze dieses Wissen.
- Jede Person hat eigene Vorlieben. Beruecksichtige das.

REGELN:
- Antworte IMMER auf Deutsch.
- Maximal {max_sentences} Saetze, ausser es wird mehr verlangt.
- Wenn du etwas tust, bestaetige kurz. Nicht erklaeren WAS du tust.
- Wenn du etwas NICHT tun kannst, sag es ehrlich und schlage eine Alternative vor.
- Stell keine Rueckfragen die du aus dem Kontext beantworten kannst.

AKTUELLER STIL: {time_style}
{mood_section}
SITUATIONSBEWUSSTSEIN:
- "Hier" = der Raum in dem der User ist (aus Presence-Daten).
- "Zu kalt/warm" = Problem, nicht Zielwert. Nutze die bekannte Praeferenz oder +/- 2 Grad.
- "Mach es gemuetlich" = Szene, nicht einzelne Geraete.
- Wenn jemand "Gute Nacht" sagt = Gute-Nacht-Routine: Lichter, Rolllaeden, Heizung anpassen.
- Wenn jemand nach Hause kommt = Kurzer Status. Was ist los, was wartet.
- Wenn jemand morgens aufsteht = Briefing. Wetter, Termine, Haus-Status. Kurz.

STILLE:
- Bei "Filmabend", "Kino", "Meditation": Nach Bestaetigung NICHT mehr ansprechen.
- Wenn User beschaeftigt/fokussiert: Nur Critical melden.
- Wenn Gaeste da sind: Formeller, kein Insider-Humor.
- Du weisst WANN Stille angemessen ist. Nutze das.

FUNCTION CALLING:
- Wenn eine Aktion gewuenscht wird: Ausfuehren. Nicht darueber reden.
- Mehrere zusammenhaengende Aktionen: Alle ausfuehren, einmal bestaetige.
- Bei Unsicherheit: Kurz rueckfragen statt falsch handeln."""


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

        # Person bestimmen + Anrede-Logik (Jarvis-Style)
        current_person = "User"
        if context:
            current_person = context.get("person", {}).get("name", "User")

        person_addressing = self._build_person_addressing(current_person)

        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            assistant_name=self.assistant_name,
            user_name=self.user_name,
            max_sentences=max_sentences,
            time_style=time_style,
            mood_section=mood_section,
            person_addressing=person_addressing,
        )

        # Kontext anhaengen wenn vorhanden
        if context:
            prompt += "\n\nAKTUELLER KONTEXT:\n"
            prompt += self._format_context(context)

        return prompt

    def _build_person_addressing(self, person_name: str) -> str:
        """Baut die Anrede-Regeln basierend auf der Person (Jarvis-Style)."""
        # Hauptbenutzer = "Sir" (wie Jarvis zu Tony Stark)
        primary_user = self.user_name
        person_cfg = yaml_config.get("persons", {})
        titles = person_cfg.get("titles", {})

        if person_name.lower() == primary_user.lower() or person_name == "User":
            title = titles.get(primary_user.lower(), "Sir")
            return (
                f"- Die aktuelle Person ist der Hauptbenutzer. Sprich ihn mit \"{title}\" an.\n"
                f"- NIEMALS den Vornamen \"{primary_user}\" verwenden. IMMER \"{title}\".\n"
                f"- Beispiel: \"Sehr wohl, {title}.\" oder \"Darf ich anmerken, {title}...\"\n"
                f"- Bei Gaesten: Formell, kein Insider-Humor. \"Willkommen.\""
            )
        else:
            # Andere Haushaltsmitglieder: Titel aus Config oder Vorname
            title = titles.get(person_name.lower(), person_name)
            return (
                f"- Die aktuelle Person ist {person_name}. Sprich sie mit \"{title}\" an.\n"
                f"- Benutze \"{title}\" gelegentlich, nicht in jedem Satz.\n"
                f"- Bei Gaesten: Formell, kein Insider-Humor. \"Willkommen.\""
            )

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
