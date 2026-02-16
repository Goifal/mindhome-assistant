# MindHome Assistant - Lokaler KI-Sprachassistent

> "Dein Zuhause denkt mit - und spricht mit dir."

MindHome Assistant ist ein **lokaler, privater Sprachassistent** der auf einem separaten Server laeuft und mit Home Assistant kommuniziert.

## Architektur

```
PC 1: Home Assistant (NUC)       PC 2: MindHome Assistant Server
┌─────────────────────┐          ┌─────────────────────┐
│  Home Assistant      │          │  Ollama (LLM)       │
│  MindHome Add-on     │◄── LAN──►│  Assistant Service  │
│  Whisper (STT)       │          │  ChromaDB (Memory)  │
│  Piper (TTS)         │          │  Redis (Cache)      │
└─────────────────────┘          └─────────────────────┘
```

## Features

- **Sprachsteuerung**: Licht, Klima, Rollladen, Szenen, Alarm - alles per Sprache
- **Persoenlichkeit**: Redet wie ein Butler - kurz, direkt, trocken humorvoll
- **Kontext-Bewusstsein**: Weiss wer spricht, in welchem Raum, wie das Wetter ist
- **Dual-Modell**: Schnelles Modell (3B) fuer Befehle, schlaues (14B) fuer Fragen
- **Gedaechtnis**: Working Memory (Redis) + Langzeit-Memory (ChromaDB)
- **100% Lokal**: Nichts verlaesst dein Netzwerk

## Voraussetzungen

- Ubuntu Server 24.04 LTS (oder aehnlich)
- Mindestens 8 GB RAM (16+ empfohlen fuer das 14B Modell)
- Home Assistant mit Long-Lived Access Token

## Installation

```bash
git clone https://github.com/Goifal/mindhome-assistant.git
cd mindhome-assistant
./install.sh
```

Das Script installiert automatisch:
- Docker (falls nicht vorhanden)
- Ollama + Qwen 2.5 LLM-Modelle
- ChromaDB + Redis Container
- MindHome Assistant Service

## Manuelle Installation

```bash
# 1. Repo klonen
git clone https://github.com/Goifal/mindhome-assistant.git
cd mindhome-assistant

# 2. .env konfigurieren
cp .env.example .env
nano .env  # HA_URL, HA_TOKEN, USER_NAME anpassen

# 3. Ollama installieren und Modelle laden
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen2.5:3b
ollama pull qwen2.5:14b  # optional, braucht ~16 GB RAM

# 4. Docker Container starten
docker compose up -d
```

## Nutzung

### API

```bash
# Chat
curl -X POST http://localhost:8200/api/assistant/chat \
  -H 'Content-Type: application/json' \
  -d '{"text": "Mach das Licht im Wohnzimmer aus", "person": "Max"}'

# Health Check
curl http://localhost:8200/api/assistant/health

# Kontext anzeigen (Debug)
curl http://localhost:8200/api/assistant/context

# API Docs (Swagger)
# http://localhost:8200/docs
```

### Beispiele

```
"Licht aus"                    -> schaltet Licht im aktuellen Raum aus
"Wohnzimmer auf 22 Grad"      -> setzt Thermostat
"Gute Nacht"                   -> aktiviert Nacht-Szene
"Mach es gemuetlich"           -> waehlt passende Szene
"Wie ist das Wetter morgen?"   -> Wettervorhersage
"Rollladen runter"             -> schliesst Rollladen
```

## Konfiguration

### .env (Pflicht)

| Variable | Beschreibung | Beispiel |
|----------|-------------|---------|
| `HA_URL` | Home Assistant URL | `http://192.168.1.100:8123` |
| `HA_TOKEN` | HA Long-Lived Token | `eyJ0eX...` |
| `USER_NAME` | Dein Name | `Max` |

### config/settings.yaml

Hier kannst du anpassen:
- **Autonomie-Level** (1-5): Wie selbststaendig der Assistent handelt
- **Persoenlichkeit**: Stil je nach Tageszeit
- **Modell-Routing**: Keywords fuer schnelles/schlaues Modell
- **Sicherheit**: Temperatur-Grenzen, Bestaetigung fuer kritische Aktionen

## Autonomie-Level

| Level | Name | Verhalten |
|-------|------|-----------|
| 1 | Assistent | Nur auf Befehle reagieren |
| 2 | Butler | + Proaktive Infos (Standard) |
| 3 | Mitbewohner | + Kleine Aenderungen selbst |
| 4 | Vertrauter | + Routinen anpassen |
| 5 | Autopilot | + Automationen erstellen |

## Projektstruktur

```
mindhome-assistant/
├── install.sh              # Ein-Klick-Installation
├── docker-compose.yml      # Alle Container
├── Dockerfile              # Assistant Service Image
├── .env.example            # Konfiguration (Template)
├── requirements.txt        # Python Dependencies
├── config/
│   └── settings.yaml       # Hauptkonfiguration
└── assistant/
    ├── main.py             # FastAPI Server
    ├── brain.py            # Zentrales Gehirn
    ├── config.py           # Settings laden
    ├── ollama_client.py    # LLM-Kommunikation
    ├── ha_client.py        # Home Assistant API
    ├── model_router.py     # Modell-Auswahl (3B vs 14B)
    ├── personality.py      # System Prompt + Stil
    ├── context_builder.py  # Kontext sammeln
    ├── function_calling.py # HA-Aktionen ausfuehren
    ├── function_validator.py # Sicherheits-Checks
    ├── memory.py           # Redis + ChromaDB
    └── autonomy.py         # Autonomie-Level
```

## Verwandte Projekte

- [MindHome](https://github.com/Goifal/mindhome) - KI-basiertes Home Assistant Add-on

---

*MindHome Assistant - Lokal. Privat. Persoenlich.*
