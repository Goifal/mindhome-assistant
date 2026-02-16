"""Tests fuer Personality Engine."""

from assistant.personality import PersonalityEngine


class TestPersonalityEngine:

    def setup_method(self):
        self.engine = PersonalityEngine()

    def test_time_of_day_early_morning(self):
        assert self.engine.get_time_of_day(6) == "early_morning"

    def test_time_of_day_morning(self):
        assert self.engine.get_time_of_day(9) == "morning"

    def test_time_of_day_afternoon(self):
        assert self.engine.get_time_of_day(14) == "afternoon"

    def test_time_of_day_evening(self):
        assert self.engine.get_time_of_day(20) == "evening"

    def test_time_of_day_night(self):
        assert self.engine.get_time_of_day(23) == "night"

    def test_time_of_day_midnight(self):
        assert self.engine.get_time_of_day(0) == "night"

    def test_system_prompt_contains_user_name(self):
        prompt = self.engine.build_system_prompt()
        assert "TestUser" in prompt

    def test_system_prompt_contains_rules(self):
        prompt = self.engine.build_system_prompt()
        assert "Deutsch" in prompt
        assert "Erledigt" in prompt

    def test_system_prompt_with_context(self):
        context = {
            "time": {"datetime": "2026-02-16 14:30", "weekday": "Montag"},
            "person": {"name": "Max", "last_room": "Wohnzimmer"},
            "room": "Wohnzimmer",
            "house": {
                "temperatures": {"Wohnzimmer": {"current": 21, "target": 22, "mode": "heat"}},
                "lights": ["Wohnzimmer: 80%"],
                "presence": {"home": ["Max"], "away": ["Lisa"]},
                "weather": {"temp": 8, "condition": "cloudy"},
                "active_scenes": [],
                "security": "armed_home",
            },
            "alerts": ["Offen: Fenster Kueche"],
        }
        prompt = self.engine.build_system_prompt(context)
        assert "Wohnzimmer" in prompt
        assert "Max" in prompt
        assert "WARNUNG" in prompt

    def test_system_prompt_with_memories(self):
        context = {
            "memories": ["User mag 21 Grad im Wohnzimmer", "Lisa kommt immer um 18 Uhr"],
        }
        prompt = self.engine.build_system_prompt(context)
        assert "Erinnerungen" in prompt
        assert "21 Grad" in prompt

    def test_max_sentences_night(self):
        assert self.engine.get_max_sentences("night") == 1

    def test_max_sentences_evening(self):
        assert self.engine.get_max_sentences("evening") == 3
