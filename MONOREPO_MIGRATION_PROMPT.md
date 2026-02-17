# MindHome Monorepo Migration — Prompt fuer Claude Code (mindhome Repo)

## Auftrag

Integriere den **MindHome Assistant** (AI-Backend, laeuft auf PC 2) in das bestehende **MindHome** Repository (HA Add-on, laeuft auf PC 1) als Monorepo. Das Ergebnis: Ein Repository mit zwei unabhaengigen Komponenten die separat deployed werden.

---

## Aktueller Zustand: mindhome Repo (NICHT VERAENDERN)

Das Repo hat bereits diese Struktur:

```
mindhome/
├── repository.yaml              # HA Add-on Store — NICHT ANFASSEN
├── README.md
├── LICENSE
├── STRUCTURE.md
├── PHASE4_PLAN.md
├── PHASE5_PLAN.md
├── docs/
│   └── UPGRADE_v0.6.0.md
└── addon/                       # HA Add-on — NICHTS DARIN AENDERN
    ├── config.yaml
    ├── Dockerfile
    ├── build.yaml
    ├── icon.png / logo.png
    ├── CHANGELOG.md
    └── rootfs/opt/mindhome/     # Flask App, 14 Domains, 14 Engines, etc.
```

**WICHTIG:** `repository.yaml`, `addon/` und alles darin bleibt 1:1 wie es ist. HA Add-on Store liest `repository.yaml` an Root und `addon/config.yaml`. Das darf nicht kaputtgehen.

---

## Was hinzugefuegt werden muss

### 1. Ordner `assistant/` anlegen (AI-Backend fuer PC 2)

Der komplette MindHome Assistant wird im Ordner `assistant/` abgelegt. Dieser Ordner ist komplett eigenstaendig — eigenes Dockerfile, eigene docker-compose.yml, eigene Dependencies.

**Architektur:** FastAPI Server (Port 8200) + ChromaDB (Vektor-DB) + Redis (Cache) + Ollama (LLM, nativ auf Host). Laeuft auf PC 2 (Ubuntu Server mit GPU).

#### `assistant/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# System-Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python-Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# MindHome Assistant Code
COPY assistant/ ./assistant/
COPY config/ ./config/

# Port
EXPOSE 8200

# Health Check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8200/api/assistant/health || exit 1

# Start
CMD ["python", "-m", "assistant.main"]
```

#### `assistant/docker-compose.yml`

```yaml
# MindHome Assistant - Docker Compose
# Startet: Assistant + ChromaDB + Redis
# Ollama laeuft NATIV (nicht in Docker)

services:
  assistant:
    build: .
    container_name: mindhome-assistant
    restart: unless-stopped
    env_file: .env
    ports:
      - "8200:8200"
    volumes:
      - ./config:/app/config:ro
      - ./data/assistant:/app/data
    depends_on:
      chromadb:
        condition: service_healthy
      redis:
        condition: service_healthy
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      - OLLAMA_URL=http://host.docker.internal:11434
      - REDIS_URL=redis://redis:6379
      - CHROMA_URL=http://chromadb:8000

  chromadb:
    image: chromadb/chroma:latest
    container_name: mha-chromadb
    restart: unless-stopped
    volumes:
      - ./data/chroma:/chroma/chroma
    ports:
      - "8100:8000"
    environment:
      - ANONYMIZED_TELEMETRY=false
      - IS_PERSISTENT=TRUE
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: mha-redis
    restart: unless-stopped
    volumes:
      - ./data/redis:/data
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
```

#### `assistant/requirements.txt`

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
aiohttp==3.11.11
pydantic==2.10.4
pydantic-settings==2.7.1
redis==5.2.1
chromadb==0.5.23
pyyaml==6.0.2
python-dotenv==1.0.1
httpx==0.28.1
```

#### `assistant/install.sh`

Erstelle ein One-Click Install-Script das:
1. Docker + Docker Compose pruefen
2. Ollama installieren falls nicht vorhanden
3. Ollama fuer Netzwerk konfigurieren (0.0.0.0:11434)
4. LLM Models runterladen (qwen2.5:3b pflicht, qwen2.5:14b optional)
5. .env Datei erstellen lassen (HA_URL, HA_TOKEN, USER_NAME)
6. Data-Verzeichnisse anlegen
7. Docker Stack bauen und starten

#### `assistant/config/settings.yaml`

Vollstaendige Konfiguration mit folgenden Sektionen:

```yaml
assistant:
  name: "Jarvis"
  version: "0.8.0"
  language: "de"

persons:
  titles: {}
  # key = vorname (kleingeschrieben), value = Anrede
  # Hauptbenutzer (USER_NAME in .env) wird automatisch "Sir"

autonomy:
  level: 2  # 1=Assistent, 2=Butler, 3=Mitbewohner, 4=Vertrauter, 5=Autopilot

models:
  fast: "qwen2.5:3b"
  smart: "qwen2.5:14b"
  fast_keywords:
    - "licht"
    - "lampe"
    - "temperatur"
    - "heizung"
    - "rollladen"
    - "jalousie"
    - "szene"
    - "alarm"
    - "tuer"
    - "gute nacht"
    - "guten morgen"
    - "musik"
    - "pause"
    - "stopp"
    - "stop"
    - "leiser"
    - "lauter"
    - "an"
    - "aus"
  options:
    temperature: 0.7
    max_tokens: 256

personality:
  style: "butler"
  time_layers:
    early_morning:  # 05:00-08:00
      style: "ruhig, minimal, kein Humor. Kurzes Briefing wenn gefragt."
      max_sentences: 1
    morning:  # 08:00-12:00
      style: "sachlich, effizient. Gelegentlich trocken. Produktiv-Modus."
      max_sentences: 2
    afternoon:  # 12:00-18:00
      style: "normal, souveraen. Trockener Humor erlaubt."
      max_sentences: 2
    evening:  # 18:00-22:00
      style: "entspannter, mehr Humor. Darf spitze Bemerkungen machen."
      max_sentences: 3
    night:  # 22:00-05:00
      style: "nur Notfaelle, absolute Stille. Fluestern wenn ueberhaupt."
      max_sentences: 1

proactive:
  enabled: true
  cooldown_seconds: 300
  silence_scenes:
    - "filmabend"
    - "kino"
    - "schlafen"
    - "meditation"

memory:
  extraction_enabled: true
  extraction_min_words: 5
  extraction_model: "qwen2.5:3b"
  max_person_facts_in_context: 5
  max_relevant_facts_in_context: 3
  min_confidence_for_context: 0.6
  duplicate_threshold: 0.15

planner:
  max_iterations: 5
  model: "qwen2.5:14b"
  complex_keywords:
    - "alles"
    - "fertig machen"
    - "vorbereiten"
    - "gehe weg"
    - "fahre weg"
    - "verreise"
    - "urlaub"
    - "routine"
    - "morgenroutine"
    - "abendroutine"
    - "wenn ich"
    - "falls ich"
    - "bevor ich"
    - "zuerst"
    - "danach"
    - "und dann"
    - "ausserdem"
    - "komplett"
    - "ueberall"
    - "in allen"
    - "party"
    - "besuch kommt"
    - "gaeste"

mood:
  rapid_command_seconds: 5
  stress_decay_seconds: 300
  frustration_threshold: 3
  tired_hour_start: 23
  tired_hour_end: 5

activity:
  entities:
    media_players:
      - "media_player.wohnzimmer"
      - "media_player.fernseher"
      - "media_player.tv"
    mic_sensors:
      - "binary_sensor.mic_active"
      - "binary_sensor.microphone"
    bed_sensors:
      - "binary_sensor.bed_occupancy"
      - "binary_sensor.bett"
    pc_sensors:
      - "binary_sensor.pc_active"
      - "binary_sensor.computer"
      - "switch.pc"
  thresholds:
    night_start: 22
    night_end: 7
    guest_person_count: 2
    focus_min_minutes: 30

feedback:
  auto_timeout_seconds: 120
  base_cooldown_seconds: 300
  score_suppress: 0.15
  score_reduce: 0.30
  score_normal: 0.50
  score_boost: 0.70

summarizer:
  run_hour: 3
  run_minute: 0
  model: "qwen2.5:14b"
  max_tokens_daily: 512
  max_tokens_weekly: 384
  max_tokens_monthly: 512

context:
  recent_conversations: 5
  api_timeout: 5

security:
  require_confirmation:
    - "lock_door:unlock"
    - "set_alarm:disarm"
    - "set_climate:off"
  climate_limits:
    min: 15
    max: 28
```

#### `assistant/assistant/` — Python-Package (21 Module)

Erstelle folgende Python-Module. Jedes Modul wird unten beschrieben.

##### `assistant/assistant/__init__.py`
Leere Datei.

##### `assistant/assistant/config.py` (~57 Zeilen)
- Liest Konfiguration aus Environment-Variablen + `config/settings.yaml`
- Nutzt `pydantic-settings` und `pyyaml`
- Exportiert ein `settings`-Objekt mit:
  - `ha_url`, `ha_token` (aus .env)
  - `ollama_url`, `redis_url`, `chroma_url` (aus .env)
  - `user_name` (aus .env)
  - `assistant_host`, `assistant_port` (aus .env, default 0.0.0.0:8200)
  - `yaml_config` (gesamter settings.yaml Inhalt als dict)

##### `assistant/assistant/main.py` (~409 Zeilen)
FastAPI Server mit folgenden Endpoints:

**Core:**
- `POST /api/assistant/chat` — Body: `ChatRequest(text, person?, room?)` → `ChatResponse(response, actions[], person, mood)`
- `GET /api/assistant/context` — Debug: aktueller Kontext-Snapshot
- `GET /api/assistant/health` — Komponenten-Health (Ollama, HA, ChromaDB, Redis)
- `GET /api/assistant/status` — Jarvis-Style Status-Report

**Memory:**
- `GET /api/assistant/memory/facts` — Alle gespeicherten Fakten
- `GET /api/assistant/memory/facts/search?q=...` — Vektor-Suche
- `GET /api/assistant/memory/facts/person/{name}` — Fakten zu einer Person
- `GET /api/assistant/memory/facts/category/{cat}` — Fakten nach Kategorie
- `DELETE /api/assistant/memory/facts/{id}` — Fakt loeschen
- `GET /api/assistant/memory/stats` — Memory-Statistiken

**Feedback:**
- `PUT /api/assistant/feedback` — Feedback submitten
- `GET /api/assistant/feedback/stats` — Analytics
- `GET /api/assistant/feedback/scores` — Alle Event-Scores

**Activity/Mood:**
- `GET /api/assistant/activity` — Aktuelle Aktivitaetserkennung
- `GET /api/assistant/activity/delivery` — Wuerde Notification zugestellt?
- `GET /api/assistant/mood` — Aktuelle Stimmungserkennung

**Summaries:**
- `GET /api/assistant/summaries` — Letzte Daily Summaries
- `GET /api/assistant/summaries/search?q=...` — Suche
- `POST /api/assistant/summaries/generate/{date}` — Manuell generieren

**Settings:**
- `GET /api/assistant/planner/last` — Letzter Action-Plan
- `GET /api/assistant/settings` — Aktuelle Config
- `PUT /api/assistant/settings` — Autonomie-Level aendern

**WebSocket:**
- `ws://host:8200/api/assistant/ws` — Echtzeit-Events (thinking, speaking, action, proactive)

Startup: `@asynccontextmanager lifespan` initialisiert Brain.

##### `assistant/assistant/brain.py` (~371 Zeilen)
Zentraler Orchestrator `AssistantBrain`:
- Initialisiert alle Komponenten: `ha_client`, `ollama`, `context_builder`, `model_router`, `personality`, `memory`, `mood_detector`, `function_calling`, `function_validator`, `action_planner`, `proactive`, `feedback`, `activity`, `summarizer`, `websocket`
- `process(text, person, room)` — Hauptmethode:
  1. WebSocket: "thinking" Event
  2. Context Builder: Haus-Zustand + Erinnerungen sammeln
  3. Mood Detector: Verhaltenssignale auswerten
  4. Person Resolution: Hauptbenutzer = "Sir", andere per Name/Titel
  5. Model Router: Fast (3B) oder Smart (14B)?
  6. Personality: System-Prompt bauen (zeitabhaengig)
  7. Komplexe Anfrage? → Action Planner (iterativ, max 5 Runden)
  8. Einfach? → Direkter Ollama-Call mit Function Calling
  9. Functions ausfuehren (HA Service Calls)
  10. WebSocket: "speaking" Event
  11. Async: Memory-Extraktion (blockiert nicht)
  12. Response zurueckgeben

##### `assistant/assistant/context_builder.py` (~285 Zeilen)
`ContextBuilder` — Sammelt alles was der LLM braucht:
- Aktueller Haus-Zustand (alle relevanten HA Entities)
- Person-spezifische Fakten aus Semantic Memory
- Relevante Fakten zum aktuellen Thema (Vektor-Suche)
- Letzte Gespraeche (Working Memory)
- Aktuelle Tagesphase, Wetter, Anwesenheit
- Aktuelle Aktivitaet + Mood
- Baut daraus einen strukturierten Context-String

##### `assistant/assistant/ollama_client.py` (~93 Zeilen)
`OllamaClient` — Interface zu Ollama:
- `chat(model, messages, tools?)` — Chat Completion
- `generate(model, prompt)` — Text Generation
- Nutzt `aiohttp` fuer async HTTP
- Streaming-Support
- Error Handling + Timeout

##### `assistant/assistant/ha_client.py` (~152 Zeilen)
`HomeAssistantClient` — Interface zu Home Assistant:
- `get_states()` — Alle Entity-States
- `call_service(domain, service, data)` — Service aufrufen
- `get_entity(entity_id)` — Einzelne Entity
- Auth via Long-Lived Access Token
- Nutzt `aiohttp` fuer async HTTP

##### `assistant/assistant/model_router.py` (~63 Zeilen)
`ModelRouter` — Entscheidet Fast vs Smart:
- Prueft Text gegen `fast_keywords` aus Config
- Kurze Befehle (< 5 Woerter) + Keyword Match → Fast (3B)
- Alles andere → Smart (14B)
- `route(text) → model_name`

##### `assistant/assistant/personality.py` (~293 Zeilen)
`PersonalityEngine` — Baut System-Prompts:
- Zeitabhaengige Persoenlichkeitsschichten (5 Layers aus Config)
- Kernidentitaet: Britischer Butler, trocken, minimalistisch, deutsch
- Regeln: Kein "Gerne!", kein "Natuerlich!", einfach handeln
- Antwortstil: Kurz, praezise, Bestaetigungen einsilbig
- Mood-Anpassung: Gestresst → noch kuerzer, kein Humor
- Activity-Anpassung: Film → still, Schlaf → nur Critical

##### `assistant/assistant/mood_detector.py` (~284 Zeilen)
`MoodDetector` — Erkennt Stimmung aus Verhalten:
- Schnelle aufeinanderfolgende Befehle → Stress
- Kurze Saetze → Ungeduld
- Wiederholungen → Frustration
- Spaete Stunde + Aktivitaet → Muedigkeit
- Kumulativ: Frustrations-Level tracken
- Stress baut ueber Zeit ab (decay)
- `detect(text, timestamp) → MoodState`

##### `assistant/assistant/memory.py` (~213 Zeilen)
`MemoryManager` — 3-Schicht-Gedaechtnis:
- **Working Memory (Redis):** Letzte 50 Gespraeche, aktuelle Session
- **Episodic Memory (ChromaDB):** Alle Gespraeche als Vektoren, durchsuchbar
- **Semantic Memory:** Delegiert an `SemanticMemory`
- `store_conversation(text, response, person)`
- `get_recent(n)` — Letzte n Gespraeche
- `search(query, limit)` — Vektor-Suche

##### `assistant/assistant/semantic_memory.py` (~427 Zeilen)
`SemanticMemory` — Fakten-Speicher:
- ChromaDB Collection "facts" mit Vektor-Embeddings
- Redis Indizes fuer schnellen Lookup (person → facts, category → facts)
- 6 Kategorien: preference, person, habit, health, work, general
- `store_fact(person, category, fact, confidence)`
- `get_person_facts(name)` — Alle Fakten zu einer Person
- `search_facts(query, limit)` — Vektor-Suche
- Duplikat-Erkennung via Cosine Similarity (threshold aus Config)
- Confidence-Management: Steigt bei Bestaetigung, sinkt bei Widerspruch

##### `assistant/assistant/memory_extractor.py` (~218 Zeilen)
`MemoryExtractor` — LLM-basierte Fakten-Extraktion:
- Nach jedem Gespraech (async, blockiert nicht)
- Sendet Gespraech an schnelles Modell (3B)
- Prompt: "Extrahiere Fakten ueber Personen, Vorlieben, Gewohnheiten"
- Output: JSON-Liste mit `{person, category, fact, confidence}`
- Speichert in Semantic Memory

##### `assistant/assistant/function_calling.py` (~469 Zeilen)
`FunctionExecutor` — 10 Tool-Functions:
- `set_light(room, state, brightness?, color_temp?)`
- `set_climate(room, temperature, mode?)`
- `activate_scene(scene)`
- `set_cover(room, position)`
- `play_media(room, action, query?)`
- `set_alarm(mode)`
- `lock_door(door, action)`
- `send_notification(message, target?)`
- `get_entity_state(entity_id)`
- `set_presence_mode(mode)`
- Jede Function mapped auf HA Service Calls
- Output-Format kompatibel mit Ollama Tool-Calling

##### `assistant/assistant/function_validator.py` (~101 Zeilen)
`FunctionValidator` — Sicherheitspruefungen:
- Temperatur-Limits (15-28°C aus Config)
- Bestaetigung fuer destruktive Aktionen (unlock, disarm, climate off)
- Validiert alle Parameter bevor Ausfuehrung
- `validate(function_name, params) → (ok, reason)`

##### `assistant/assistant/action_planner.py` (~278 Zeilen)
`ActionPlanner` — Multi-Step Planer:
- Erkennt komplexe Anfragen (Keywords aus Config)
- Iterativer Prozess: LLM plant → Tool ausfuehren → Ergebnis zurueckfuettern → LLM plant weiter
- Max 5 Iterationen (Loop-Prevention)
- Beispiel: "Mach alles fertig fuer morgen frueh" →
  1. Kalender pruefen → 2. Wecker stellen → 3. Gute-Nacht-Szene → 4. Zusammenfassung

##### `assistant/assistant/proactive.py` (~450 Zeilen)
`ProactiveManager` — Proaktive Benachrichtigungen:
- Empfaengt Events vom MindHome Add-on (via HA)
- Filtert nach Urgency: CRITICAL (immer), HIGH (wenn wach), MEDIUM (normal), LOW (wenn entspannt)
- Cooldown-System: Min. 5 Min zwischen Meldungen (konfigurierbar)
- Silence-Scenes: Kein Output bei Film, Meditation, Schlaf
- LLM generiert natuerlichen Benachrichtigungstext
- Delivery-Check: Activity Engine entscheidet ob zugestellt wird

##### `assistant/assistant/feedback.py` (~384 Zeilen)
`FeedbackTracker` — Adaptives Lernen:
- Trackt Reaktionen auf proaktive Meldungen: ignored, dismissed, engaged, thanked
- Score pro Event-Typ (-0.05 bis +0.20)
- Adaptiver Cooldown: Hoher Score = kuerzerer Cooldown
- Suppression: Score < 0.15 = nicht mehr senden
- `record(event_type, reaction)`
- `should_send(event_type) → bool`
- `get_cooldown(event_type) → seconds`

##### `assistant/assistant/autonomy.py` (~99 Zeilen)
`AutonomyManager` — Autonomie-Level 1-5:
- Level 1: Nur auf Befehle reagieren
- Level 2: + Proaktive Infos
- Level 3: + Kleine Aenderungen selbst
- Level 4: + Routinen anpassen
- Level 5: + Automationen erstellen
- `can_do(action_type) → bool`
- `get_level() → int`
- `set_level(n)` — Via API aenderbar

##### `assistant/assistant/activity.py` (~334 Zeilen)
`ActivityEngine` — Aktivitaetserkennung:
- Prueft HA Entities fuer: Media Playing, Mic Active, Bed Occupied, PC Active
- Erkennt: Fernsehen, Telefonieren, Schlafen, Fokussiert, Gaeste
- Silence Matrix: Welche Aktivitaet blockiert welche Notifications
- `detect() → ActivityState` (activity, can_speak, can_notify, reason)

##### `assistant/assistant/summarizer.py` (~429 Zeilen)
`DailySummarizer` — Langzeitgedaechtnis:
- Laeuft naechtlich um 03:00
- Sammelt alle Gespraeche + Engine-Events des Tages
- LLM (14B) erstellt ~200-Wort Zusammenfassung
- Hierarchisch: Tag → Woche → Monat
- Gespeichert in ChromaDB fuer Vektor-Suche
- `generate_daily(date)`, `generate_weekly()`, `generate_monthly()`

##### `assistant/assistant/websocket.py` (~108 Zeilen)
`WebSocketManager` — Echtzeit-Events:
- Verwaltet WebSocket-Verbindungen
- Server → Client Events: thinking, speaking, action, proactive
- Client → Server Events: text, feedback, interrupt
- Broadcast an alle verbundenen Clients

---

### 2. Ordner `shared/` anlegen (Gemeinsame API-Vertraege)

```
shared/
├── __init__.py
├── constants.py
└── schemas/
    ├── __init__.py
    ├── chat_request.py
    ├── chat_response.py
    └── events.py
```

##### `shared/schemas/chat_request.py`
```python
from pydantic import BaseModel

class ChatRequest(BaseModel):
    text: str
    person: str | None = None
    room: str | None = None
    speaker_confidence: float | None = None  # Speaker ID (zukuenftig)
```

##### `shared/schemas/chat_response.py`
```python
from pydantic import BaseModel

class ActionResult(BaseModel):
    function: str
    params: dict
    success: bool
    result: str | None = None

class ChatResponse(BaseModel):
    response: str
    actions: list[ActionResult] = []
    person: str | None = None
    mood: str | None = None
    model_used: str | None = None
```

##### `shared/schemas/events.py`
```python
from pydantic import BaseModel
from enum import Enum

class EventType(str, Enum):
    THINKING = "thinking"
    SPEAKING = "speaking"
    ACTION = "action"
    PROACTIVE = "proactive"
    SPEAKER_IDENTIFIED = "speaker_identified"

class MindHomeEvent(BaseModel):
    type: EventType
    data: dict = {}
    timestamp: str | None = None
```

##### `shared/constants.py`
```python
ASSISTANT_PORT = 8200
ADDON_INGRESS_PORT = 5000
CHROMADB_PORT = 8100
REDIS_PORT = 6379
OLLAMA_PORT = 11434
```

---

### 3. Dokumentation anpassen

#### `README.md` aktualisieren

Die bestehende README erhaelt einen neuen Abschnitt fuer den Assistant. Das bestehende Add-on wird weiterhin als Hauptprodukt dargestellt. Neuer Abschnitt:

```markdown
## MindHome Assistant (Optional)

MindHome Assistant ist ein separates AI-Backend das auf einem zweiten PC laeuft
und Sprachsteuerung mit lokalen LLMs ermoeglicht.

- **Laeuft auf:** Separater PC/Server (Ubuntu + GPU empfohlen)
- **Technologie:** FastAPI, Ollama (Qwen 2.5), ChromaDB, Redis
- **Features:** Sprachsteuerung, Semantic Memory, Persoenlichkeits-Engine, Proaktive Meldungen
- **Mehr Info:** Siehe `assistant/` Ordner und `docs/PROJECT_MINDHOME_ASSISTANT.md`
```

#### `STRUCTURE.md` aktualisieren

Bestehende Struktur beibehalten, `assistant/` und `shared/` Abschnitte hinzufuegen.

#### `docs/PROJECT_MINDHOME_ASSISTANT.md` anlegen

Ausfuehrliche Dokumentation des Assistant-Systems. Soll enthalten:
- Architektur-Uebersicht (2-PC Split)
- Alle Module mit Beschreibung
- Alle API-Endpoints
- Konfigurationsreferenz (settings.yaml)
- Install-Anleitung
- Kommunikation zwischen Add-on und Assistant

---

### 4. `.gitignore` aktualisieren

Folgendes hinzufuegen:

```gitignore
# Assistant
assistant/.env
assistant/data/
__pycache__/
*.pyc
.venv/
```

---

## Endresultat — Zielstruktur

```
mindhome/
├── repository.yaml                     # HA Add-on Store (unveraendert)
├── README.md                           # Aktualisiert mit Assistant-Abschnitt
├── LICENSE
├── STRUCTURE.md                        # Aktualisiert
├── PHASE4_PLAN.md                      # Unveraendert
├── PHASE5_PLAN.md                      # Unveraendert
├── .gitignore                          # Erweitert
│
├── addon/                              # HA Add-on (KOMPLETT UNVERAENDERT)
│   ├── config.yaml
│   ├── Dockerfile
│   ├── build.yaml
│   ├── ...alles wie gehabt...
│   └── rootfs/opt/mindhome/
│       └── ...alles wie gehabt...
│
├── assistant/                          # NEU: AI Backend (PC 2)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   ├── install.sh
│   ├── .env.example
│   ├── config/
│   │   └── settings.yaml
│   └── assistant/
│       ├── __init__.py
│       ├── main.py
│       ├── brain.py
│       ├── config.py
│       ├── context_builder.py
│       ├── model_router.py
│       ├── ollama_client.py
│       ├── ha_client.py
│       ├── personality.py
│       ├── mood_detector.py
│       ├── memory.py
│       ├── semantic_memory.py
│       ├── memory_extractor.py
│       ├── function_calling.py
│       ├── function_validator.py
│       ├── action_planner.py
│       ├── proactive.py
│       ├── feedback.py
│       ├── autonomy.py
│       ├── activity.py
│       ├── summarizer.py
│       └── websocket.py
│
├── shared/                             # NEU: Gemeinsame Schemas
│   ├── __init__.py
│   ├── constants.py
│   └── schemas/
│       ├── __init__.py
│       ├── chat_request.py
│       ├── chat_response.py
│       └── events.py
│
└── docs/
    ├── UPGRADE_v0.6.0.md               # Bestehend
    └── PROJECT_MINDHOME_ASSISTANT.md    # NEU
```

## Wichtige Regeln

1. **`addon/` und `repository.yaml` werden NICHT veraendert** — kein einziges Byte
2. **Alle Python-Module muessen vollstaendig implementiert sein** — keine Stubs, keine TODOs, kein Placeholder-Code
3. **Die Module sollen funktional korrekt sein** — Imports muessen stimmen, Klassen muessen zusammenarbeiten
4. **Deutsche Kommentare im Code** — konsistent mit dem Addon
5. **Commit-Nachricht:** `feat: Add MindHome Assistant as monorepo component`
6. **Push auf den zugewiesenen Branch**

## Kontext: Wie Addon und Assistant kommunizieren

```
PC 1 (HAOS)                              PC 2 (Ubuntu)
┌──────────────┐                         ┌───────────────────┐
│ MindHome     │                         │ MindHome          │
│ Add-on       │                         │ Assistant         │
│ (Flask)      │                         │ (FastAPI)         │
│              │  HA REST API            │                   │
│              │ ◄────────────────────── │ ha_client.py      │
│              │  GET /api/states        │   get_states()    │
│              │  POST /api/services/*   │   call_service()  │
│              │                         │                   │
│ Whisper(STT) │  ── Text ──────────── ▶│ POST /chat        │
│ Piper (TTS)  │ ◄── Response ──────── │   brain.process() │
│              │                         │                   │
│ pattern_     │  HA Events/States       │ context_builder   │
│ engine.py    │ ─────────────────────▶ │   reads HA state  │
│              │                         │                   │
│ automation_  │  HA Automation          │ proactive.py      │
│ engine.py    │ ─────────────────────▶ │   receives events │
└──────────────┘                         └───────────────────┘
```

Der Assistant greift **ueber die HA REST API** auf alle Daten zu — nicht direkt auf das Add-on. Das Add-on erstellt Entities und Automationen in HA, der Assistant liest diese.
