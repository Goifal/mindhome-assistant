"""Tests fuer Context Builder."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from assistant.context_builder import ContextBuilder


class TestContextBuilder:

    def setup_method(self):
        self.ha_mock = MagicMock()
        self.ha_mock.get_states = AsyncMock(return_value=[])
        self.ha_mock.get_presence = AsyncMock(return_value=None)
        self.ha_mock.get_energy = AsyncMock(return_value=None)
        self.builder = ContextBuilder(self.ha_mock)

    @pytest.mark.asyncio
    async def test_build_returns_time(self):
        context = await self.builder.build()
        assert "time" in context
        assert "datetime" in context["time"]
        assert "weekday" in context["time"]
        assert "time_of_day" in context["time"]

    @pytest.mark.asyncio
    async def test_build_with_states(self, sample_ha_states):
        self.ha_mock.get_states = AsyncMock(return_value=sample_ha_states)
        context = await self.builder.build()

        assert "house" in context
        assert "person" in context
        assert "room" in context

    @pytest.mark.asyncio
    async def test_extract_temperatures(self, sample_ha_states):
        house = self.builder._extract_house_status(sample_ha_states)
        assert "Wohnzimmer Thermostat" in house["temperatures"]
        assert house["temperatures"]["Wohnzimmer Thermostat"]["current"] == 21.5

    @pytest.mark.asyncio
    async def test_extract_lights_on(self, sample_ha_states):
        house = self.builder._extract_house_status(sample_ha_states)
        assert len(house["lights"]) == 2  # Wohnzimmer + Buero
        assert any("Wohnzimmer" in l for l in house["lights"])

    @pytest.mark.asyncio
    async def test_extract_persons(self, sample_ha_states):
        house = self.builder._extract_house_status(sample_ha_states)
        assert "Max" in house["presence"]["home"]
        assert "Lisa" in house["presence"]["away"]

    @pytest.mark.asyncio
    async def test_extract_weather(self, sample_ha_states):
        house = self.builder._extract_house_status(sample_ha_states)
        assert house["weather"]["temp"] == 8
        assert house["weather"]["condition"] == "cloudy"

    @pytest.mark.asyncio
    async def test_extract_security(self, sample_ha_states):
        house = self.builder._extract_house_status(sample_ha_states)
        assert house["security"] == "armed_home"

    @pytest.mark.asyncio
    async def test_extract_media(self, sample_ha_states):
        house = self.builder._extract_house_status(sample_ha_states)
        assert len(house["media"]) == 1
        assert "Chill Mix" in house["media"][0]

    @pytest.mark.asyncio
    async def test_guess_room_from_motion(self, sample_ha_states):
        room = self.builder._guess_current_room(sample_ha_states)
        assert "Wohnzimmer" in room

    @pytest.mark.asyncio
    async def test_extract_alerts_none(self, sample_ha_states):
        alerts = self.builder._extract_alerts(sample_ha_states)
        # Rauchmelder Keller ist off, also keine Alarm-Alerts
        assert not any("ALARM" in a for a in alerts)

    @pytest.mark.asyncio
    async def test_extract_alerts_smoke(self):
        states = [
            {"entity_id": "binary_sensor.smoke_keller", "state": "on",
             "attributes": {"friendly_name": "Rauchmelder Keller"}},
        ]
        alerts = self.builder._extract_alerts(states)
        assert len(alerts) >= 1
        assert "ALARM" in alerts[0]

    def test_weekday_german(self):
        assert ContextBuilder._weekday_german(0) == "Montag"
        assert ContextBuilder._weekday_german(6) == "Sonntag"

    def test_time_of_day(self):
        assert ContextBuilder._get_time_of_day(6) == "early_morning"
        assert ContextBuilder._get_time_of_day(14) == "afternoon"
        assert ContextBuilder._get_time_of_day(23) == "night"

    @pytest.mark.asyncio
    async def test_build_without_ha(self):
        self.ha_mock.get_states = AsyncMock(return_value=[])
        context = await self.builder.build()
        assert "time" in context
        # house should not be present since no states
        assert "house" not in context
