"""
Home Assistant API Client - Kommunikation mit HA und MindHome

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

logger = logging.getLogger(__name__)


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
        """
        HA Service aufrufen (z.B. light.turn_off).

        Args:
            domain: z.B. "light", "climate", "scene"
            service: z.B. "turn_on", "turn_off", "activate"
            data: Service-Daten (entity_id, brightness, etc.)

        Returns:
            True bei Erfolg
        """
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
        """MindHome System-Status."""
        return await self._get_mindhome("/api/health")

    async def get_presence(self) -> Optional[dict]:
        """Anwesenheitsdaten von MindHome."""
        return await self._get_mindhome("/api/persons")

    async def get_energy(self) -> Optional[dict]:
        """Energie-Daten von MindHome."""
        return await self._get_mindhome("/api/energy/summary")

    async def get_comfort(self) -> Optional[dict]:
        """Komfort-Daten von MindHome."""
        return await self._get_mindhome("/api/health/comfort")

    async def get_security(self) -> Optional[dict]:
        """Sicherheits-Status von MindHome."""
        return await self._get_mindhome("/api/security/dashboard")

    async def get_patterns(self) -> Optional[dict]:
        """Erkannte Muster von MindHome."""
        return await self._get_mindhome("/api/patterns")

    async def get_health_dashboard(self) -> Optional[dict]:
        """Gesundheits-Dashboard von MindHome."""
        return await self._get_mindhome("/api/health/dashboard")

    async def get_day_phases(self) -> Optional[dict]:
        """Tagesphasen von MindHome."""
        return await self._get_mindhome("/api/day-phases")

    # ----- Interne HTTP Methoden -----

    async def _get_ha(self, path: str) -> Any:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ha_url}{path}",
                    headers=self._ha_headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    logger.warning("HA GET %s -> %d", path, resp.status)
                    return None
        except aiohttp.ClientError as e:
            logger.error("HA nicht erreichbar: %s", e)
            return None

    async def _post_ha(self, path: str, data: dict) -> Any:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ha_url}{path}",
                    headers=self._ha_headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201):
                        return await resp.json()
                    logger.warning("HA POST %s -> %d", path, resp.status)
                    return None
        except aiohttp.ClientError as e:
            logger.error("HA nicht erreichbar: %s", e)
            return None

    async def _get_mindhome(self, path: str) -> Any:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.mindhome_url}{path}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return None
        except aiohttp.ClientError:
            return None
