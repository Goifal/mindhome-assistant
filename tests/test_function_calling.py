"""Tests fuer Function Calling."""

import time

import pytest
from unittest.mock import AsyncMock, MagicMock

from assistant.function_calling import (
    EntityCache,
    FunctionExecutor,
    normalize_for_search,
)


class TestNormalizeForSearch:

    def test_lowercase(self):
        assert normalize_for_search("Wohnzimmer") == "wohnzimmer"

    def test_spaces_to_underscores(self):
        assert normalize_for_search("gute nacht") == "gute_nacht"

    def test_umlaut_ae(self):
        assert normalize_for_search("B\u00e4der") == "baeder"

    def test_umlaut_oe(self):
        assert normalize_for_search("K\u00f6ln") == "koeln"

    def test_umlaut_ue(self):
        assert normalize_for_search("B\u00fcro") == "buero"

    def test_umlaut_ss(self):
        assert normalize_for_search("Stra\u00dfe") == "strasse"

    def test_already_ascii(self):
        assert normalize_for_search("buero") == "buero"

    def test_mixed_umlauts_and_spaces(self):
        assert normalize_for_search("K\u00fcche Ger\u00e4t") == "kueche_geraet"

    def test_empty_string(self):
        assert normalize_for_search("") == ""


class TestEntityCache:

    def test_empty_cache(self):
        cache = EntityCache(ttl=30)
        assert cache.get() == []
        assert cache.is_valid is False

    def test_set_and_get(self):
        cache = EntityCache(ttl=30)
        states = [{"entity_id": "light.test", "state": "on"}]
        cache.set(states)
        assert cache.get() == states
        assert cache.is_valid is True

    def test_invalidate(self):
        cache = EntityCache(ttl=30)
        cache.set([{"entity_id": "light.test"}])
        cache.invalidate()
        assert cache.get() == []
        assert cache.is_valid is False

    def test_ttl_expiry(self):
        cache = EntityCache(ttl=0)  # Sofort abgelaufen
        cache.set([{"entity_id": "light.test"}])
        # TTL=0 bedeutet: Cache ist sofort ungueltig
        time.sleep(0.01)
        assert cache.is_valid is False


class TestFunctionExecutor:

    def setup_method(self):
        self.ha_mock = MagicMock()
        self.ha_mock.get_states = AsyncMock(return_value=[])
        self.ha_mock.get_state = AsyncMock(return_value=None)
        self.ha_mock.call_service = AsyncMock(return_value=True)
        self.executor = FunctionExecutor(self.ha_mock)

    @pytest.mark.asyncio
    async def test_unknown_function(self):
        result = await self.executor.execute("nonexistent", {})
        assert result["success"] is False
        assert "Unbekannte" in result["message"]

    @pytest.mark.asyncio
    async def test_set_light_on(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        result = await self.executor.execute("set_light", {"room": "wohnzimmer", "state": "on"})
        assert result["success"] is True
        self.ha_mock.call_service.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_light_with_brightness(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        result = await self.executor.execute(
            "set_light", {"room": "wohnzimmer", "state": "on", "brightness": 50}
        )
        assert result["success"] is True
        call_args = self.ha_mock.call_service.call_args
        assert call_args[1].get("data") or call_args[0][2].get("brightness_pct") == 50

    @pytest.mark.asyncio
    async def test_set_light_room_not_found(self):
        self.ha_mock.get_states = AsyncMock(return_value=[])
        result = await self.executor.execute("set_light", {"room": "garage", "state": "on"})
        assert result["success"] is False
        assert "gefunden" in result["message"]

    @pytest.mark.asyncio
    async def test_set_climate(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        result = await self.executor.execute("set_climate", {"room": "wohnzimmer", "temperature": 22})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_activate_scene(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        result = await self.executor.execute("activate_scene", {"scene": "filmabend"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_get_entity_state(self):
        self.ha_mock.get_state = AsyncMock(return_value={
            "state": "21.5",
            "attributes": {"friendly_name": "Temperatur", "unit_of_measurement": "\u00b0C"},
        })
        result = await self.executor.execute("get_entity_state", {"entity_id": "sensor.temp"})
        assert result["success"] is True
        assert "21.5" in result["message"]

    @pytest.mark.asyncio
    async def test_get_entity_state_not_found(self):
        self.ha_mock.get_state = AsyncMock(return_value=None)
        result = await self.executor.execute("get_entity_state", {"entity_id": "sensor.unknown"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_find_entity_by_umlaut(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        entity_id = await self.executor._find_entity("light", "B\u00fcro")
        assert entity_id == "light.buero"

    @pytest.mark.asyncio
    async def test_find_entity_by_ascii(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        entity_id = await self.executor._find_entity("light", "wohnzimmer")
        assert entity_id == "light.wohnzimmer"

    @pytest.mark.asyncio
    async def test_entity_caching(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        await self.executor._find_entity("light", "wohnzimmer")
        await self.executor._find_entity("light", "schlafzimmer")
        # get_states should only be called once (cached)
        assert self.ha_mock.get_states.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        await self.executor._find_entity("light", "wohnzimmer")
        self.executor.invalidate_cache()
        await self.executor._find_entity("light", "wohnzimmer")
        assert self.ha_mock.get_states.call_count == 2

    @pytest.mark.asyncio
    async def test_play_media(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        result = await self.executor.execute("play_media", {"action": "pause", "room": "wohnzimmer"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_set_alarm(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        result = await self.executor.execute("set_alarm", {"mode": "disarm"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_lock_door(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        result = await self.executor.execute("lock_door", {"door": "haustuer", "action": "lock"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_send_notification(self):
        result = await self.executor.execute("send_notification", {"message": "Test", "target": "phone"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_set_presence_mode(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        result = await self.executor.execute("set_presence_mode", {"mode": "away"})
        assert result["success"] is True
