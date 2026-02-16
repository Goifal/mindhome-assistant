# MindHome Assistant

> Dieses Projekt lebt jetzt in einem eigenen Repository.

**Repository:** [github.com/Goifal/mindhome-assistant](https://github.com/Goifal/mindhome-assistant)

## Warum getrennt?

MindHome (HA Add-on) und MindHome Assistant (KI-Sprachassistent) sind bewusst getrennte Projekte:

- **Verschiedene Deployment-Modelle**: HA Add-on vs. Docker-Compose Stack
- **Verschiedene Tech-Stacks**: Node.js/Web vs. Python/AI/ML
- **Verschiedene Ressourcen**: Leicht vs. Schwer (LLM, ChromaDB, Redis)
- **Lose Kopplung**: Kommunikation ueber HTTP API (Port 8200)

## Architektur

```
PC 1: Home Assistant (NUC)       PC 2: MindHome Assistant Server
┌─────────────────────┐          ┌─────────────────────────────┐
│  Home Assistant      │          │  Ollama (LLM)               │
│  MindHome Add-on     │◄── LAN──►│  MindHome Assistant (:8200) │
│  Whisper (STT)       │          │  ChromaDB (Memory)          │
│  Piper (TTS)         │          │  Redis (Cache)              │
└─────────────────────┘          └─────────────────────────────┘
```

## Installation & Docs

Siehe [mindhome-assistant Repository](https://github.com/Goifal/mindhome-assistant).
