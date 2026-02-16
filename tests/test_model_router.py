"""Tests fuer Model Router."""

from assistant.model_router import ModelRouter


class TestModelRouter:

    def setup_method(self):
        self.router = ModelRouter()

    def test_fast_model_for_light_command(self):
        assert self.router.select_model("Licht aus") == self.router.model_fast

    def test_fast_model_for_short_keyword(self):
        assert self.router.select_model("Musik pause") == self.router.model_fast

    def test_fast_model_for_temperature(self):
        assert self.router.select_model("Temperatur hoch") == self.router.model_fast

    def test_smart_model_for_question(self):
        assert self.router.select_model("Was ist die Temperatur im Wohnzimmer?") == self.router.model_smart

    def test_smart_model_for_complex_request(self):
        assert self.router.select_model("Erklaere mir wie die Heizung funktioniert und was ich einstellen sollte") == self.router.model_smart

    def test_smart_model_default_for_long_text(self):
        assert self.router.select_model("Bitte mach es gemuetlich heute Abend") == self.router.model_smart

    def test_smart_model_for_how_question(self):
        assert self.router.select_model("Wie warm ist es draussen?") == self.router.model_smart

    def test_fast_model_case_insensitive(self):
        assert self.router.select_model("LICHT AN") == self.router.model_fast

    def test_get_model_info(self):
        info = self.router.get_model_info()
        assert "fast" in info
        assert "smart" in info
        assert info["fast_keywords_count"] > 0
