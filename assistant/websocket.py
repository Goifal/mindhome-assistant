"""
WebSocket Manager - Echtzeit-Kommunikation mit Clients.
Sendet Events wie assistant.speaking, assistant.thinking, etc.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Verwaltet aktive WebSocket-Verbindungen."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Neue Verbindung akzeptieren."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket verbunden (%d aktiv)", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        """Verbindung entfernen."""
        self.active_connections.remove(websocket)
        logger.info("WebSocket getrennt (%d aktiv)", len(self.active_connections))

    async def broadcast(self, event: str, data: Optional[dict] = None):
        """Event an alle verbundenen Clients senden."""
        if not self.active_connections:
            return

        message = json.dumps({
            "event": event,
            "data": data or {},
            "timestamp": datetime.now().isoformat(),
        })

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.active_connections.remove(conn)

    async def send_personal(self, websocket: WebSocket, event: str, data: Optional[dict] = None):
        """Event an einen bestimmten Client senden."""
        message = json.dumps({
            "event": event,
            "data": data or {},
            "timestamp": datetime.now().isoformat(),
        })
        try:
            await websocket.send_text(message)
        except Exception:
            pass


# Globale Instanz
ws_manager = ConnectionManager()


async def emit_thinking():
    """Signalisiert: Assistant denkt nach."""
    await ws_manager.broadcast("assistant.thinking", {"status": "processing"})


async def emit_speaking(text: str):
    """Signalisiert: Assistant spricht."""
    await ws_manager.broadcast("assistant.speaking", {"text": text})


async def emit_action(function_name: str, args: dict, result: dict):
    """Signalisiert: Assistant fuehrt Aktion aus."""
    await ws_manager.broadcast("assistant.action", {
        "function": function_name,
        "args": args,
        "result": result,
    })


async def emit_listening():
    """Signalisiert: Assistant hoert zu."""
    await ws_manager.broadcast("assistant.listening", {"status": "active"})


async def emit_proactive(
    text: str,
    event_type: str,
    urgency: str = "medium",
    notification_id: str = "",
):
    """Signalisiert: Proaktive Meldung (mit ID fuer Feedback-Tracking)."""
    await ws_manager.broadcast("assistant.proactive", {
        "text": text,
        "event_type": event_type,
        "urgency": urgency,
        "notification_id": notification_id,
    })
