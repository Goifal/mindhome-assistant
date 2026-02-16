"""
Audit Log - Protokolliert alle ausgefuehrten Aktionen.
Fuer Nachvollziehbarkeit und Debugging.
"""

import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("mindhome.audit")


class AuditLogger:
    """Protokolliert alle Function-Call-Aktionen."""

    def __init__(self, max_entries: int = 1000):
        self._log: list[dict] = []
        self._max_entries = max_entries

    def log_action(
        self,
        function_name: str,
        arguments: dict,
        result: dict,
        person: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "function": function_name,
            "arguments": arguments,
            "success": result.get("success", False),
            "message": result.get("message", ""),
            "person": person,
            "request_id": request_id,
        }

        self._log.append(entry)
        if len(self._log) > self._max_entries:
            self._log = self._log[-self._max_entries:]

        logger.info(
            "AUDIT: %s(%s) -> %s [Person: %s]",
            function_name,
            json.dumps(arguments, ensure_ascii=False),
            "OK" if result.get("success") else "FAIL",
            person or "unknown",
        )

    def get_recent(self, limit: int = 50) -> list[dict]:
        return self._log[-limit:][::-1]

    def get_by_person(self, person: str, limit: int = 20) -> list[dict]:
        return [
            e for e in reversed(self._log)
            if e.get("person") == person
        ][:limit]


# Globale Instanz
audit_log = AuditLogger()
