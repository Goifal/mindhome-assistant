"""
MindHome Assistant - Hauptanwendung (FastAPI Server)
Startet den MindHome Assistant REST API Server.
"""

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

from .audit import audit_log
from .brain import AssistantBrain
from .config import settings
from .middleware import (
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    StructuredFormatter,
)
from .websocket import ws_manager, emit_speaking

# Structured Logging konfigurieren
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
)
logger = logging.getLogger("mindhome-assistant")

# Brain-Instanz
brain = AssistantBrain()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup und Shutdown."""
    logger.info("=" * 50)
    logger.info(" MindHome Assistant v0.1.0 startet...")
    logger.info("=" * 50)
    await brain.initialize()

    health = await brain.health_check()
    for component, status in health["components"].items():
        icon = "OK" if status in ("connected", "running") else "!!"
        logger.info(" [%s] %s: %s", icon, component, status)

    logger.info(" Autonomie: Level %d (%s)",
        health["autonomy"]["level"],
        health["autonomy"]["name"])
    logger.info("=" * 50)
    logger.info(" MindHome Assistant bereit auf %s:%d",
        settings.assistant_host, settings.assistant_port)
    logger.info("=" * 50)

    yield

    await brain.shutdown()
    logger.info("MindHome Assistant heruntergefahren.")


app = FastAPI(
    title="MindHome Assistant",
    description="Lokaler KI-Sprachassistent fuer Home Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

# ----- Middleware (Reihenfolge wichtig: zuletzt hinzugefuegt = zuerst ausgefuehrt) -----

# CORS Policy - nur HA und lokales Netzwerk
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.ha_url,
        "http://localhost:*",
        "http://127.0.0.1:*",
        "http://192.168.*",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)

# Rate Limiting: 30 Anfragen pro Minute pro IP
app.add_middleware(RateLimitMiddleware, max_requests=30, window_seconds=60)

# Request Logging mit IDs und Latenz
app.add_middleware(RequestLoggingMiddleware)


# ----- Request/Response Modelle mit Validation -----

MAX_TEXT_LENGTH = 2000


class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    person: Optional[str] = Field(None, max_length=100)


class ChatResponse(BaseModel):
    response: str
    actions: list = []
    model_used: str = ""
    context_room: str = ""


class SettingsUpdate(BaseModel):
    autonomy_level: Optional[int] = Field(None, ge=1, le=5)


# ----- API Endpoints -----

@app.get("/api/assistant/health")
async def health():
    """Health Check - Status aller Komponenten."""
    return await brain.health_check()


@app.post("/api/assistant/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Hauptendpoint - Text an den Assistenten senden.

    Beispiel:
    POST /api/assistant/chat
    {"text": "Mach das Licht im Wohnzimmer aus", "person": "Max"}
    """
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Kein Text angegeben")

    result = await brain.process(text, request.person)
    return ChatResponse(**result)


@app.get("/api/assistant/context")
async def get_context():
    """Debug: Aktueller Kontext-Snapshot."""
    return await brain.context_builder.build()


@app.get("/api/assistant/memory/search")
async def search_memory(q: str):
    """Sucht im Langzeitgedaechtnis."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Kein Suchbegriff")
    if len(q) > MAX_TEXT_LENGTH:
        raise HTTPException(status_code=400, detail="Suchbegriff zu lang")
    results = await brain.memory.search_memories(q)
    return {"query": q, "results": results}


@app.get("/api/assistant/audit")
async def get_audit(limit: int = 50):
    """Audit Log - Letzte ausgefuehrte Aktionen."""
    if limit < 1 or limit > 200:
        limit = 50
    return {"entries": audit_log.get_recent(limit)}


@app.get("/api/assistant/settings")
async def get_settings():
    """Aktuelle Einstellungen."""
    return {
        "autonomy": brain.autonomy.get_level_info(),
        "models": brain.model_router.get_model_info(),
        "user_name": settings.user_name,
        "language": settings.language,
    }


@app.put("/api/assistant/settings")
async def update_settings(update: SettingsUpdate):
    """Einstellungen aktualisieren."""
    result = {}
    if update.autonomy_level is not None:
        success = brain.autonomy.set_level(update.autonomy_level)
        if not success:
            raise HTTPException(status_code=400, detail="Level muss 1-5 sein")
        result["autonomy"] = brain.autonomy.get_level_info()
    return result


@app.websocket("/api/assistant/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket fuer Echtzeit-Events.

    Events (Server -> Client):
    assistant.speaking - Assistent spricht (Text)
    assistant.thinking - Assistent denkt nach
    assistant.action - Assistent fuehrt Aktion aus
    assistant.listening - Assistent hoert zu
    assistant.proactive - Proaktive Meldung

    Events (Client -> Server):
    assistant.text - Text-Eingabe
    assistant.feedback - Feedback auf Meldung
    assistant.interrupt - Unterbrechung
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                event = message.get("event", "")

                if event == "assistant.text":
                    text = message.get("data", {}).get("text", "")
                    person = message.get("data", {}).get("person")
                    if text and len(text) <= MAX_TEXT_LENGTH:
                        result = await brain.process(text, person)
                        await emit_speaking(result["response"])

                elif event == "assistant.feedback":
                    event_type = message.get("data", {}).get("event_type", "")
                    response = message.get("data", {}).get("response", "ignored")
                    delta_map = {
                        "ignored": -0.05,
                        "dismissed": -0.10,
                        "engaged": 0.10,
                        "thanked": 0.20,
                    }
                    delta = delta_map.get(response, 0)
                    if event_type and delta:
                        await brain.memory.update_feedback_score(event_type, delta)

                elif event == "assistant.interrupt":
                    pass  # Fuer spaetere Streaming-Unterbrechung

            except json.JSONDecodeError:
                await ws_manager.send_personal(
                    websocket, "error", {"message": "Ungueltiges JSON"}
                )
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/")
async def root():
    """Startseite."""
    return {
        "name": "MindHome Assistant",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


def start():
    """Einstiegspunkt fuer den Server."""
    import uvicorn

    uvicorn.run(
        "assistant.main:app",
        host=settings.assistant_host,
        port=settings.assistant_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    start()
