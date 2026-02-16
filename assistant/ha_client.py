"""
Home Assistant API Client - Kommunikation mit HA und MindHome.
Mit Retry-Logik, Circuit Breaker und differenziertem Error Handling.

FIX: API-Endpoints an die tatsaechlichen MindHome Add-on Routes angepasst:
  /api/system/health  -> /api/health
  /api/engines/status  -> entfernt (existiert nicht als einzelner Endpoint)
  /api/presence        -> /api/persons
  /api/energy/current  -> /api/energy/summary
  /api/comfort/status  -> /api/health/comfort
  /api/security/status -> /api/security/dashboard
"""

import logging
from typing import Any, Optional

import aiohttp

from .config import settings
from .resilience import CircuitBreaker, retry_async

logger = logging.getLogger(__name__)


class HAClientError(Exception):
    """Fehler bei HA-Kommunikation mit Status-Info."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class HomeAssistantClient:
    """Client fuer Home Assistant + MindHome REST API."""

    def __init__(self):
        self.ha_url = settings.ha_url.rstrip("/")
        self.ha_token = settings.ha_token
        self.mindhome_url = settings.mindhome_url.rstrip("/")
        self._ha_headers = {
            "Authorization": f"Bearer {self.ha_token}",
            "Content-Type": "application/json",
        }
        self._cb_ha = CircuitBreaker(name="home_assistant", failure_threshold=5, recovery_timeout=30.0)
        self._cb_mindhome = CircuitBreaker(name="mindhome", failure_threshold=5, recovery_timeout=60.0)

    # ----- Home Assistant API -----

    async def get_states(self) -> list[dict]:
        """Alle Entity-States von HA holen."""
        return await self._get_ha("/api/states") or []

    async def get_state(self, entity_id: str) -> Optional[dict]:
        """State einer einzelnen Entity."""
        return await self._get_ha(f"/api/states/{entity_id}")

    async def call_service(
        self, domain: str, service: str, data: Optional[dict] = None
    ) -> bool:
        """HA Service aufrufen (z.B. light.turn_off)."""
        result = await self._post_ha(
            f"/api/services/{domain}/{service}", data or {}
        )
        return result is not None

    async def is_available(self) -> bool:
        """Prueft ob HA erreichbar ist."""
        try:
            result = await self._get_ha("/api/")
            return result is not None and "message" in (result or {})
        except Exception:
            return False

    # ----- MindHome API -----

    async def get_mindhome_status(self) -> Optional[dict]:
        return await self._get_mindhome("/api/health")

    async def get_presence(self) -> Optional[dict]:
        return await self._get_mindhome("/api/persons")

    async def get_energy(self) -> Optional[dict]:
        return await self._get_mindhome("/api/energy/summary")

    async def get_comfort(self) -> Optional[dict]:
        return await self._get_mindhome("/api/health/comfort")

    async def get_security(self) -> Optional[dict]:
        return await self._get_mindhome("/api/security/dashboard")

    async def get_patterns(self) -> Optional[dict]:
        return await self._get_mindhome("/api/patterns")

    async def get_health_dashboard(self) -> Optional[dict]:
        return await self._get_mindhome("/api/health/dashboard")

    async def get_day_phases(self) -> Optional[dict]:
        return await self._get_mindhome("/api/day-phases")

    # ----- Interne HTTP Methoden mit Retry + Circuit Breaker -----

    async def _get_ha(self, path: str) -> Any:
        async def _do_request():
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ha_url}{path}",
                    headers=self._ha_headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    if resp.status == 401:
                        logger.error("HA Auth fehlgeschlagen (401) - Token pruefen!")
                        return None
                    if resp.status == 404:
                        logger.debug("HA GET %s -> 404 (nicht gefunden)", path)
                        return None
                    if resp.status >= 500:
                        raise HAClientError(f"HA Server-Fehler {resp.status}", resp.status)
                    logger.warning("HA GET %s -> %d", path, resp.status)
                    return None

        try:
            return await retry_async(
                _do_request,
                max_retries=3,
                base_delay=1.0,
                max_delay=5.0,
                exceptions=(aiohttp.ClientError, HAClientError, TimeoutError),
                circuit_breaker=self._cb_ha,
            )
        except ConnectionError:
            logger.error("HA nicht erreichbar (Circuit Breaker offen)")
            return None
        except Exception as e:
            logger.error("HA GET %s Fehler: %s", path, e)
            return None

    async def _post_ha(self, path: str, data: dict) -> Any:
        async def _do_request():
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ha_url}{path}",
                    headers=self._ha_headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201):
                        return await resp.json()
                    if resp.status == 401:
                        logger.error("HA Auth fehlgeschlagen (401)")
                        return None
                    if resp.status == 404:
                        logger.warning("HA POST %s -> 404 (Service/Entity nicht gefunden)", path)
                        return None
                    if resp.status >= 500:
                        raise HAClientError(f"HA Server-Fehler {resp.status}", resp.status)
                    logger.warning("HA POST %s -> %d", path, resp.status)
                    return None

        try:
            return await retry_async(
                _do_request,
                max_retries=2,
                base_delay=0.5,
                max_delay=3.0,
                exceptions=(aiohttp.ClientError, HAClientError, TimeoutError),
                circuit_breaker=self._cb_ha,
            )
        except ConnectionError:
            logger.error("HA nicht erreichbar (Circuit Breaker offen)")
            return None
        except Exception as e:
            logger.error("HA POST %s Fehler: %s", path, e)
            return None

    async def _get_mindhome(self, path: str) -> Any:
        async def _do_request():
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.mindhome_url}{path}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    if resp.status >= 500:
                        raise HAClientError(f"MindHome Server-Fehler {resp.status}", resp.status)
                    return None

        try:
            return await retry_async(
                _do_request,
                max_retries=2,
                base_delay=1.0,
                max_delay=5.0,
                exceptions=(aiohttp.ClientError, HAClientError, TimeoutError),
                circuit_breaker=self._cb_mindhome,
            )
        except Exception:
            return None
