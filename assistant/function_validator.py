"""
Function Validator - Prueft Function Calls auf Sicherheit und Plausibilitaet.
Verhindert gefaehrliche oder unsinnige Aktionen.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from .config import yaml_config

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    ok: bool
    needs_confirmation: bool = False
    reason: Optional[str] = None


class FunctionValidator:
    """Validiert Function Calls vor der Ausfuehrung."""

    def __init__(self):
        security = yaml_config.get("security", {})
        limits = security.get("climate_limits", {})
        self.temp_min = limits.get("min", 15)
        self.temp_max = limits.get("max", 28)

        # Aktionen die Bestaetigung brauchen
        confirm_list = security.get("require_confirmation", [])
        self.require_confirmation = set(confirm_list)

    def validate(self, function_name: str, arguments: dict) -> ValidationResult:
        """
        Prueft einen Function Call.

        Args:
            function_name: Name der Funktion
            arguments: Parameter

        Returns:
            ValidationResult mit ok, needs_confirmation, reason
        """
        # Bestaetigung pruefen
        for confirm_rule in self.require_confirmation:
            parts = confirm_rule.split(":")
            if len(parts) == 2:
                func, value = parts
                if function_name == func:
                    # Pruefen ob der kritische Wert gesetzt ist
                    for arg_value in arguments.values():
                        if str(arg_value) == value:
                            return ValidationResult(
                                ok=False,
                                needs_confirmation=True,
                                reason=f"Sicherheitsbestaetigung noetig fuer {function_name}:{value}",
                            )

        # Spezifische Validierungen
        validator = getattr(self, f"_validate_{function_name}", None)
        if validator:
            return validator(arguments)

        return ValidationResult(ok=True)

    def _validate_set_climate(self, args: dict) -> ValidationResult:
        temp = args.get("temperature")
        if temp is not None:
            if temp < self.temp_min:
                return ValidationResult(
                    ok=False,
                    reason=f"Temperatur {temp}°C unter Minimum ({self.temp_min}°C)",
                )
            if temp > self.temp_max:
                return ValidationResult(
                    ok=False,
                    reason=f"Temperatur {temp}°C ueber Maximum ({self.temp_max}°C)",
                )
        return ValidationResult(ok=True)

    def _validate_set_light(self, args: dict) -> ValidationResult:
        brightness = args.get("brightness")
        if brightness is not None:
            if brightness < 0 or brightness > 100:
                return ValidationResult(
                    ok=False,
                    reason=f"Helligkeit {brightness}% ausserhalb 0-100",
                )
        return ValidationResult(ok=True)

    def _validate_set_cover(self, args: dict) -> ValidationResult:
        position = args.get("position")
        if position is not None:
            if position < 0 or position > 100:
                return ValidationResult(
                    ok=False,
                    reason=f"Position {position}% ausserhalb 0-100",
                )
        return ValidationResult(ok=True)
