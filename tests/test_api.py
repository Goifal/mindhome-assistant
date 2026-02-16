"""Tests fuer FastAPI Endpoints."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Erstellt einen Test-Client mit gemocktem Brain."""
    with patch("assistant.main.brain") as mock_brain:
        mock_brain.initialize = AsyncMock()
        mock_brain.shutdown = AsyncMock()
        mock_brain.health_check = AsyncMock(return_value={
            "status": "ok",
            "components": {
                "ollama": "connected",
                "home_assistant": "connected",
                "redis": "connected",
                "chromadb": "connected",
                "proactive": "running",
            },
            "models_available": ["qwen2.5:3b"],
            "autonomy": {"level": 2, "name": "Butler", "description": "...", "allowed_actions": []},
        })
        mock_brain.process = AsyncMock(return_value={
            "response": "Erledigt.",
            "actions": [],
            "model_used": "qwen2.5:3b",
            "context_room": "Wohnzimmer",
        })
        mock_brain.context_builder = MagicMock()
        mock_brain.context_builder.build = AsyncMock(return_value={"time": {}})
        mock_brain.memory = MagicMock()
        mock_brain.memory.search_memories = AsyncMock(return_value=[])
        mock_brain.autonomy = MagicMock()
        mock_brain.autonomy.get_level_info.return_value = {"level": 2, "name": "Butler"}
        mock_brain.autonomy.set_level.return_value = True
        mock_brain.model_router = MagicMock()
        mock_brain.model_router.get_model_info.return_value = {"fast": "qwen2.5:3b", "smart": "qwen2.5:14b"}

        from assistant.main import app
        yield TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:

    def test_health_returns_ok(self, client):
        resp = client.get("/api/assistant/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "components" in data


class TestChatEndpoint:

    def test_chat_success(self, client):
        resp = client.post("/api/assistant/chat", json={"text": "Licht an", "person": "Max"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Erledigt."

    def test_chat_empty_text_rejected(self, client):
        resp = client.post("/api/assistant/chat", json={"text": ""})
        assert resp.status_code == 422  # Pydantic validation

    def test_chat_whitespace_only_rejected(self, client):
        resp = client.post("/api/assistant/chat", json={"text": "   "})
        assert resp.status_code == 400

    def test_chat_text_too_long(self, client):
        resp = client.post("/api/assistant/chat", json={"text": "x" * 3000})
        assert resp.status_code == 422  # Pydantic max_length

    def test_chat_without_person(self, client):
        resp = client.post("/api/assistant/chat", json={"text": "Hallo"})
        assert resp.status_code == 200


class TestContextEndpoint:

    def test_context_returns_data(self, client):
        resp = client.get("/api/assistant/context")
        assert resp.status_code == 200


class TestMemoryEndpoint:

    def test_memory_search(self, client):
        resp = client.get("/api/assistant/memory/search?q=test")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    def test_memory_search_empty(self, client):
        resp = client.get("/api/assistant/memory/search?q=")
        assert resp.status_code == 400


class TestAuditEndpoint:

    def test_audit_returns_entries(self, client):
        resp = client.get("/api/assistant/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data


class TestSettingsEndpoint:

    def test_get_settings(self, client):
        resp = client.get("/api/assistant/settings")
        assert resp.status_code == 200

    def test_update_autonomy(self, client):
        resp = client.put("/api/assistant/settings", json={"autonomy_level": 3})
        assert resp.status_code == 200

    def test_update_autonomy_invalid(self, client):
        resp = client.put("/api/assistant/settings", json={"autonomy_level": 10})
        assert resp.status_code == 422  # Pydantic le=5


class TestRootEndpoint:

    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "MindHome Assistant"
