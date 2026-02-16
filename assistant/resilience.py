"""
Resilience - Retry-Logik und Circuit Breaker fuer externe Services.
Schuetzt den Assistenten vor Ausfaellen von Ollama, Home Assistant, etc.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Circuit Breaker fuer externe Services.

    CLOSED: Alles OK, Anfragen werden durchgelassen.
    OPEN: Service gestoert, Anfragen werden sofort abgelehnt.
    HALF_OPEN: Test-Phase, eine Anfrage darf durch.
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit Breaker [%s]: HALF_OPEN", self.name)
        return self._state

    def record_success(self):
        self._failure_count = 0
        if self._state != CircuitState.CLOSED:
            logger.info("Circuit Breaker [%s]: CLOSED", self.name)
        self._state = CircuitState.CLOSED

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit Breaker [%s]: OPEN nach %d Fehlern",
                self.name, self._failure_count,
            )

    @property
    def is_available(self) -> bool:
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def reset(self):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0


async def retry_async(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exceptions: tuple = (Exception,),
    circuit_breaker: Optional[CircuitBreaker] = None,
):
    """
    Fuehrt eine async Funktion mit Retry und optionalem Circuit Breaker aus.

    Args:
        func: Async Callable (keine Argumente, nutze lambda/partial)
        max_retries: Maximale Versuche
        base_delay: Basis-Wartezeit in Sekunden (verdoppelt sich)
        max_delay: Maximale Wartezeit
        exceptions: Exception-Typen die Retry ausloesen
        circuit_breaker: Optionaler Circuit Breaker

    Returns:
        Ergebnis der Funktion

    Raises:
        ConnectionError: Wenn Circuit Breaker offen
        Letzte Exception: Nach allen Retries
    """
    if circuit_breaker and not circuit_breaker.is_available:
        raise ConnectionError(
            f"Service [{circuit_breaker.name}] nicht verfuegbar (Circuit Breaker offen)"
        )

    last_exception = None
    for attempt in range(max_retries):
        try:
            result = await func()
            if circuit_breaker:
                circuit_breaker.record_success()
            return result
        except exceptions as e:
            last_exception = e
            if circuit_breaker:
                circuit_breaker.record_failure()

            if attempt < max_retries - 1:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(
                    "Retry %d/%d nach Fehler: %s (warte %.1fs)",
                    attempt + 1, max_retries, e, delay,
                )
                await asyncio.sleep(delay)

    raise last_exception
