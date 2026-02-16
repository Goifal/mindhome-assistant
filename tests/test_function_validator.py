"""Tests fuer Function Validator."""

from assistant.function_validator import FunctionValidator, ValidationResult


class TestFunctionValidator:

    def setup_method(self):
        self.validator = FunctionValidator()

    def test_valid_climate_in_range(self):
        result = self.validator.validate("set_climate", {"temperature": 22})
        assert result.ok is True

    def test_climate_too_cold(self):
        result = self.validator.validate("set_climate", {"temperature": 10})
        assert result.ok is False
        assert "Minimum" in result.reason

    def test_climate_too_hot(self):
        result = self.validator.validate("set_climate", {"temperature": 35})
        assert result.ok is False
        assert "Maximum" in result.reason

    def test_climate_at_min_boundary(self):
        result = self.validator.validate("set_climate", {"temperature": 15})
        assert result.ok is True

    def test_climate_at_max_boundary(self):
        result = self.validator.validate("set_climate", {"temperature": 28})
        assert result.ok is True

    def test_valid_light_brightness(self):
        result = self.validator.validate("set_light", {"brightness": 50})
        assert result.ok is True

    def test_light_brightness_too_high(self):
        result = self.validator.validate("set_light", {"brightness": 150})
        assert result.ok is False

    def test_light_brightness_negative(self):
        result = self.validator.validate("set_light", {"brightness": -10})
        assert result.ok is False

    def test_valid_cover_position(self):
        result = self.validator.validate("set_cover", {"position": 50})
        assert result.ok is True

    def test_cover_position_out_of_range(self):
        result = self.validator.validate("set_cover", {"position": 150})
        assert result.ok is False

    def test_unknown_function_passes(self):
        result = self.validator.validate("some_function", {"key": "value"})
        assert result.ok is True

    def test_no_brightness_passes(self):
        result = self.validator.validate("set_light", {"room": "wohnzimmer", "state": "on"})
        assert result.ok is True

    def test_no_temperature_passes(self):
        result = self.validator.validate("set_climate", {"room": "wohnzimmer"})
        assert result.ok is True
