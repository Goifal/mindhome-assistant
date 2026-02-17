# MindHome Assistant - KI-Sprachassistent fuer MindHome

> "MindHome Assistant ist kein Feature. MindHome Assistant ist das Gefuehl, dass dein Haus dich kennt."

---

## Inhaltsverzeichnis

1. [Vision](#vision)
2. [Hardware-Setup (Split-Architektur)](#hardware-setup-split-architektur)
3. [Assistant-PC Setup Guide](#assistant-pc-setup-guide)
4. [LLM-Modell Empfehlung](#llm-modell-empfehlung)
5. [Latenz-Analyse](#latenz-analyse)
6. [Gesamtarchitektur](#gesamtarchitektur)
7. [Phase 1: Fundament](#phase-1-fundament)
8. [Engine Layer](#engine-layer)
9. [Assistant Layer (Sprach-KI)](#assistant-layer-sprach-ki)
10. [Proactive Layer](#proactive-layer)
11. [Das MindHome-Feeling](#das-mindhome-feeling)
12. [Phase 2-7: Perfektion](#phase-2-7-perfektion)
13. [Technische Details](#technische-details)
14. [Autonomie-Level](#autonomie-level)
15. [API-Referenz](#api-referenz)

---

## Vision

MindHome Phase 1-5 macht das Haus intelligent. Es lernt Muster, optimiert Energie, erkennt Anomalien. Aber es reagiert nur - es hat keine Stimme, keine Persoenlichkeit.

**MindHome Assistant** gibt MindHome eine Seele.

MindHome Assistant ist ein lokaler, privater Sprachassistent der:
- **Dein Haus kennt** - jeder Raum, jedes Geraet, jede Temperatur
- **Dich kennt** - deine Gewohnheiten, Vorlieben, deinen Tagesablauf
- **Handelt** - nicht nur redet, sondern Dinge tut
- **Proaktiv ist** - spricht dich an, warnt, informiert
- **Schweigt** - wenn es nichts zu sagen gibt
- **Lokal laeuft** - nichts verlaesst dein Netzwerk

---

## Hardware-Setup (Split-Architektur)

### Warum zwei PCs?

| Aspekt | Alles auf einem PC | Split (HAOS + Assistant-PC) |
|--------|-------------------|--------------------------|
| **HAOS Stabilitaet** | LLM frisst CPU/RAM, HA langsamer | HA laeuft ungestoert |
| **LLM Groesse** | Begrenzt durch HA-RAM | Ganzer PC nur fuer KI |
| **GPU moeglich** | Nicht in HAOS | Ja! GPU = 10x schneller |
| **Updates** | LLM-Update kann HA stoeren | Unabhaengig updaten |
| **Ausfallsicherheit** | Alles faellt zusammen aus | HA + MindHome laufen ohne den Assistant |
| **Netzwerk-Latenz** | 0 ms | <1 ms (LAN) - irrelevant |

### PC 1: HAOS (bestehendes System)

| Komponente | Detail |
|-----------|--------|
| **Geraet** | Intel NUC BXNUC10i7FNH2 |
| **CPU** | Intel Core i7-10710U (6C/12T, bis 4.7 GHz) |
| **RAM** | 32 GB DDR4 |
| **Storage** | 500 GB NVMe + 500 GB SSD |
| **OS** | Home Assistant OS |
| **Aufgabe** | HA + MindHome + Whisper + Piper |

### PC 2: MindHome Assistant Server (separater PC)

| Komponente | Aufgabe |
|-----------|---------|
| **OS** | Ubuntu Server 24.04 LTS |
| **Ollama** | LLM Inference (Qwen 2.5) |
| **Assistant Service** | Context Builder, Personality, Action Planner |
| **ChromaDB** | Langzeitgedaechtnis (Vektor-DB) |
| **Redis** | Cache fuer schnelle Zugriffe |
| **Optional** | GPU fuer schnellere Inference |

### Netzwerk-Verteilung

```
Lokales Netzwerk (LAN, <1ms Latenz)
|
|  +--------------------------------------+
|  | PC 1: Intel NUC (HAOS)               |
|  |   i7-10710U / 32 GB / 500+500 GB     |
|  |                                       |
|  |   Home Assistant OS                   |
|  |     +-- MindHome Add-on              |
|  |     |    Alle 14 Engines             |
|  |     |    Pattern Learning            |
|  |     |    REST API (:8099)            |
|  |     |    WebSocket Events            |
|  |     +-- Whisper Add-on (STT)         |
|  |     +-- Piper Add-on (TTS)           |
|  |     +-- HA Core (:8123)              |
|  +--------------------------------------+
          |
          |  REST API + WebSocket (<1ms)
          |
|  +--------------------------------------+
|  | PC 2: MindHome Assistant Server                   |
|  |   Ubuntu Server 24.04 LTS             |
|  |                                       |
|  |   Docker                              |
|  |     +-- Ollama (:11434)              |
|  |     |    Qwen 2.5 3B  (schnell)      |
|  |     |    Qwen 2.5 14B (schlau)       |
|  |     +-- ChromaDB (:8100)             |
|  |     +-- Redis (:6379)                |
|  |                                       |
|  |   Assistant Service (:8200)              |
|  |     +-- Context Builder              |
|  |     +-- Personality Engine           |
|  |     +-- Action Planner               |
|  |     +-- Proactive Manager            |
|  |     +-- Function Calling -> HA API   |
|  |     +-- Memory Manager              |
|  +--------------------------------------+
```

### Datenfluss zwischen den PCs

```
User spricht -> [Mikrofon]
                    |
         PC 1 (HAOS):
                    |
              [Whisper STT] -> Text
                    |
                    | HTTP POST (Text + Kontext-Anfrage)
                    |
         PC 2 (MindHome Assistant):
                    |
              [Context Builder]
                    | holt Daten von PC 1 via REST API (<1ms)
              [Ollama/Qwen 2.5]
                    | generiert Antwort + Function Calls
              [Function Executor]
                    | sendet Befehle an HA via REST API (<1ms)
                    |
                    | HTTP Response (Antwort-Text)
                    |
         PC 1 (HAOS):
                    |
              [Piper TTS] -> Sprache
                    |
              [Speaker] -> User hoert Antwort
```

---

## Assistant-PC Setup Guide

### Schritt-fuer-Schritt: Vom leeren PC zum MindHome Assistant Server

#### Schritt 1: Ubuntu Server installieren

**Was du brauchst:**
- USB-Stick (mind. 4 GB)
- Den Assistant-PC mit leerem Datentraeger
- Einen anderen PC fuer den Download

**1.1 Ubuntu Server ISO herunterladen:**
```
https://ubuntu.com/download/server
-> Ubuntu Server 24.04 LTS
-> Datei: ubuntu-24.04-live-server-amd64.iso (~2.5 GB)
```

**1.2 Bootfaehigen USB-Stick erstellen:**
```
Windows: Rufus (https://rufus.ie) oder balenaEtcher
Mac/Linux: balenaEtcher (https://etcher.balena.io)

1. Programm starten
2. ISO-Datei auswaehlen
3. USB-Stick auswaehlen
4. "Flash" klicken
5. Warten bis fertig
```

**1.3 Vom USB-Stick booten:**
```
1. USB-Stick in Assistant-PC stecken
2. PC einschalten
3. Beim Start F2/F10/F12/DEL druecken (je nach BIOS)
4. Boot-Reihenfolge: USB zuerst
5. Ubuntu Installer startet
```

**1.4 Ubuntu Server installieren:**
```
Sprache:           Deutsch
Tastatur:          Deutsch
Netzwerk:          DHCP (automatisch) - spaeter feste IP
Storage:           Gesamte Festplatte verwenden
Profil:
  Name:            MindHome
  Servername:      mindhome-assistant
  Benutzername:    mindhome
  Passwort:        [dein sicheres Passwort]
SSH:               OpenSSH Server INSTALLIEREN (wichtig!)
Extras:            Nichts auswaehlen
-> Installation starten, warten, neustarten
-> USB-Stick entfernen wenn aufgefordert
```

#### Schritt 2: Feste IP-Adresse vergeben

Nach dem ersten Login per Tastatur/Monitor:

```bash
# Netzwerk-Interface herausfinden
ip addr show
# -> z.B. "enp0s3" oder "eth0"

# Netplan-Konfiguration bearbeiten
sudo nano /etc/netplan/00-installer-config.yaml
```

Inhalt (anpassen an dein Netzwerk):
```yaml
network:
  version: 2
  ethernets:
    enp0s3:              # <- dein Interface-Name
      dhcp4: no
      addresses:
        - 192.168.1.200/24    # <- feste IP fuer Assistant-PC
      routes:
        - to: default
          via: 192.168.1.1    # <- dein Router
      nameservers:
        addresses:
          - 192.168.1.1       # <- DNS (Router)
          - 8.8.8.8           # <- Fallback DNS
```

```bash
# Anwenden
sudo netplan apply

# Testen
ping 192.168.1.1      # Router erreichbar?
ping google.com       # Internet erreichbar?
```

**Ab jetzt kannst du per SSH vom Hauptrechner aus arbeiten:**
```bash
# Von deinem normalen PC:
ssh mindhome@192.168.1.200
```

#### Schritt 3: System aktualisieren

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

#### Schritt 4: Docker installieren

```bash
# Docker Repository hinzufuegen
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker installieren
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# User zur Docker-Gruppe hinzufuegen (kein sudo noetig)
sudo usermod -aG docker mindhome
newgrp docker

# Testen
docker run hello-world
```

#### Schritt 5: Ollama installieren

```bash
# Ollama installieren (nativ, nicht Docker - besser fuer CPU)
curl -fsSL https://ollama.ai/install.sh | sh

# Ollama als System-Service laeuft automatisch
# Pruefen:
sudo systemctl status ollama

# Ollama von aussen erreichbar machen
sudo systemctl edit ollama
```

Einfuegen:
```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```

```bash
# Neustarten
sudo systemctl restart ollama

# Modelle herunterladen
ollama pull qwen2.5:3b       # ~2 GB, fuer schnelle Befehle
ollama pull qwen2.5:14b      # ~9 GB, fuer komplexe Fragen

# Testen
ollama run qwen2.5:3b "Sag Hallo auf Deutsch"
# -> Sollte "Hallo!" oder aehnliches antworten
# Mit CTRL+D beenden

# Test von einem anderen PC im Netzwerk:
curl http://192.168.1.200:11434/api/generate \
  -d '{"model":"qwen2.5:3b","prompt":"Hallo","stream":false}'
```

#### Schritt 6: ChromaDB + Redis per Docker

```bash
# Verzeichnis fuer MindHome Assistant erstellen
mkdir -p ~/mindhome-assistant
cd ~/mindhome-assistant

# Docker Compose Datei erstellen
cat > docker-compose.yml << 'EOF'
services:
  chromadb:
    image: chromadb/chroma:latest
    container_name: mindhome-chromadb
    restart: unless-stopped
    volumes:
      - ./data/chroma:/chroma/chroma
    ports:
      - "8100:8000"
    environment:
      - ANONYMIZED_TELEMETRY=false
      - IS_PERSISTENT=TRUE

  redis:
    image: redis:7-alpine
    container_name: mindhome-redis
    restart: unless-stopped
    volumes:
      - ./data/redis:/data
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
EOF

# Starten
docker compose up -d

# Pruefen
docker compose ps
# -> Beide Container sollten "running" sein

# Testen
curl http://localhost:8100/api/v1/heartbeat
# -> {"nanosecond heartbeat": ...}
```

#### Schritt 7: Verbindung zu Home Assistant testen

```bash
# HA Long-Lived Access Token erstellen:
# 1. HA Dashboard oeffnen -> Profil (unten links)
# 2. Ganz unten: "Langlebige Zugangstoken"
# 3. Token erstellen, Name: "MindHome Assistant"
# 4. Token KOPIEREN und sicher speichern!

# Testen ob HA erreichbar ist:
curl -s -H "Authorization: Bearer DEIN_TOKEN_HIER" \
  http://192.168.1.100:8123/api/ | head
# -> {"message": "API running."}

# MindHome API testen:
curl -s http://192.168.1.100:8099/api/system/health | head
# -> {"status": "ok", ...}
```

#### Schritt 8: Autostart einrichten

```bash
# Alles startet automatisch nach Reboot:
# - Ollama: bereits als systemd Service
# - Docker (ChromaDB + Redis): restart: unless-stopped
# - Ubuntu: bootet automatisch ohne Monitor/Tastatur

# Optional: Automatic Security Updates
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

#### Schritt 9: Firewall einrichten

```bash
sudo ufw enable
sudo ufw allow ssh                 # SSH Zugang
sudo ufw allow from 192.168.1.0/24 to any port 11434  # Ollama (nur LAN)
sudo ufw allow from 192.168.1.0/24 to any port 8100   # ChromaDB (nur LAN)
sudo ufw allow from 192.168.1.0/24 to any port 8200   # MindHome Assistant API (nur LAN)
sudo ufw allow from 192.168.1.0/24 to any port 6379   # Redis (nur LAN)
sudo ufw status
```

### Checkliste: Ist alles bereit?

```
[ ] Ubuntu Server 24.04 LTS installiert
[ ] Feste IP-Adresse vergeben (z.B. 192.168.1.200)
[ ] SSH funktioniert
[ ] Docker installiert und laeuft
[ ] Ollama installiert und hoert auf 0.0.0.0:11434
[ ] Qwen 2.5 3B heruntergeladen und getestet
[ ] Qwen 2.5 14B heruntergeladen und getestet
[ ] ChromaDB Container laeuft auf Port 8100
[ ] Redis Container laeuft auf Port 6379
[ ] HA API erreichbar von Assistant-PC
[ ] MindHome API erreichbar von Assistant-PC
[ ] Firewall konfiguriert
[ ] Alles startet automatisch nach Reboot
```

---

## LLM-Modell Empfehlung

### Anforderungen fuer MindHome Assistant

Das LLM muss:
- **Deutsch** gut koennen (Hauptsprache)
- **Function Calling** nativ unterstuetzen
- **Kurze Antworten** liefern (nicht labern)
- **Schnell** auf CPU laufen
- **Kontext verstehen** (Raum, Person, Situation)

### Modell-Vergleich

#### Tier 1: Beste Wahl (7-9B Parameter)

| Modell | RAM (Q8) | Deutsch | Function Calling | Speed | Note |
|--------|----------|---------|-----------------|-------|------|
| **Qwen 2.5 7B** | ~9 GB | Exzellent | Nativ | Schnell | Bestes Deutsch |
| Llama 3.1 8B | ~10 GB | Sehr gut | Nativ | Schnell | Guter Allrounder |
| Mistral 7B v0.3 | ~9 GB | Gut | Nativ | Schnell | Antwortet manchmal Englisch |

#### Tier 2: Premium (12-14B)

| Modell | RAM (Q6) | Deutsch | Function Calling | Speed | Note |
|--------|----------|---------|-----------------|-------|------|
| **Qwen 2.5 14B** | ~13 GB | Exzellent | Nativ | Mittel | Beste Qualitaet |
| Mistral Nemo 12B | ~11 GB | Sehr gut | Nativ | Mittel | Gute Alternative |

#### Tier 3: Schnell (3-4B) fuer einfache Befehle

| Modell | RAM (Q8) | Deutsch | Function Calling | Speed | Note |
|--------|----------|---------|-----------------|-------|------|
| **Qwen 2.5 3B** | ~4 GB | Gut | Nativ | Sehr schnell | Ideal fuer Geraete-Befehle |

### Empfehlung: Dual-Modell Strategie

```
Qwen 2.5 3B   -> einfache Befehle  -> ~1.5-2.5s Antwort
Qwen 2.5 14B  -> komplexe Fragen   -> ~4-7s Antwort

Beide gleichzeitig in Ollama geladen.
```

**Routing-Logik** entscheidet automatisch welches Modell:

```python
class ModelRouter:
    SIMPLE_KEYWORDS = [
        "licht", "temperatur", "heizung", "rollladen",
        "szene", "alarm", "tuer", "gute nacht",
        "musik", "pause", "stopp", "leiser", "lauter"
    ]

    def select_model(self, text: str) -> str:
        if any(word in text.lower() for word in self.SIMPLE_KEYWORDS):
            return "qwen2.5:3b"     # Schnell
        return "qwen2.5:14b"        # Schlau
```

### GPU-Upgrade Option (spaeter)

Falls du eine GPU nachruesten willst:

| GPU | VRAM | Modell | Speed | Preis (gebraucht) |
|-----|------|--------|-------|-------------------|
| RTX 3060 12GB | 12 GB | Qwen 2.5 14B Q4 | ~80 tok/s | ~180 EUR |
| RTX 3090 24GB | 24 GB | Qwen 2.5 32B Q4 | ~50 tok/s | ~600 EUR |
| RTX 4060 Ti 16GB | 16 GB | Qwen 2.5 14B Q8 | ~90 tok/s | ~350 EUR |

Mit GPU waere MindHome Assistant so schnell wie Alexa - aber komplett lokal.

---

## Latenz-Analyse

### Szenarien auf dem Assistant-PC (CPU only)

| Szenario | Modell | Methode | Latenz |
|----------|--------|---------|--------|
| "Licht aus" | Qwen 3B | Fast-Route | **~2-2.5 s** |
| "Gute Nacht" | Qwen 3B | Fast-Route + Multi-Action | **~2-3 s** |
| "Mach es gemuetlich" | Qwen 14B | LLM (Szene waehlen) | **~4-6 s** |
| "Zu kalt hier" | Qwen 14B | LLM (Kontext) | **~4-6 s** |
| "Was steht morgen an?" | Qwen 14B | LLM (Kalender) | **~5-7 s** |
| Morgen-Briefing | Qwen 14B | Proaktiv | egal (nicht zeitkritisch) |
| Sicherheits-Alarm | - | Template, kein LLM | **~1-2 s** |

### Mit GPU (Upgrade-Option)

| Szenario | CPU only | Mit RTX 3060 |
|----------|----------|-------------|
| "Licht aus" | ~2-2.5 s | ~1.5 s |
| "Mach es gemuetlich" | ~4-6 s | **~1.5-2.5 s** |
| "Was steht morgen an?" | ~5-7 s | **~2-3 s** |

### Netzwerk-Latenz zwischen den PCs

```
LLM Inference:     2000-5000 ms   (99.9% der Wartezeit)
LAN API Call:           <1 ms   ( 0.1% der Wartezeit)
                   ────────────
Fazit: Split-Architektur kostet KEINE spuerbare Latenz
```

---

## Gesamtarchitektur

### Split-Architektur: Zwei PCs im LAN

```
+----------------------------------+    +----------------------------------+
| PC 1: HAOS (Intel NUC)          |    | PC 2: MindHome Assistant Server              |
| 192.168.1.100                    |    | 192.168.1.200                    |
|                                  |    |                                  |
| +------------------------------+|    |+-------------------------------+ |
| | HOME ASSISTANT               ||    || ASSISTANT LAYER                  | |
| |  +-- MindHome Add-on        ||    ||                               | |
| |  |    REST API (:8099)       ||<---||  Context Builder              | |
| |  |    WebSocket Events       ||    ||    | holt Daten via LAN API   | |
| |  |                           ||    ||    v                          | |
| |  +-- Whisper Add-on (STT)   ||    ||  Model Router                 | |
| |  |    Wyoming Protocol      ||--->||    |                          | |
| |  |                           ||    ||    +-> Qwen 2.5 3B  (schnell)| |
| |  +-- Piper Add-on (TTS)     ||    ||    +-> Qwen 2.5 14B (schlau) | |
| |  |    Wyoming Protocol      ||<---||    |   (via Ollama :11434)    | |
| |  |                           ||    ||    v                          | |
| |  +-- HA Core (:8123)        ||    ||  Action Planner               | |
| |       REST API + WebSocket   ||<---||    | Function Calls -> HA API| |
| +------------------------------+|    ||    v                          | |
|                                  |    ||  Personality Engine          | |
| +------------------------------+|    ||  Proactive Manager           | |
| | ENGINE LAYER (in MindHome)   ||    ||  Feedback Loop               | |
| |                               ||    |+-------------------------------+ |
| | Climate | Lighting | Presence ||    |                                  |
| | Security | Energy | Sleep     ||    |+-------------------------------+ |
| | Comfort | Circadian | Pattern ||--->|| DATA LAYER                    | |
| | Routine | Adaptive | Visit    || WS || ChromaDB (:8100) - Vektoren   | |
| | Weather | Special Modes       ||    || Redis (:6379) - Cache          | |
| +------------------------------+|    |+-------------------------------+ |
|                                  |    |                                  |
| +------------------------------+|    |                                  |
| | DATA LAYER                   ||    |                                  |
| | SQLite (MindHome-Daten)      ||    |                                  |
| +------------------------------+|    |                                  |
+----------------------------------+    +----------------------------------+
         |                                         |
         +---------< LAN (<1ms) >------------------+
```

---

## Phase 1: Fundament

Phase 1 baut die Grundstruktur. Alles weitere baut darauf auf.

### Komponenten

#### 1. Whisper STT (Speech-to-Text)
- **Was**: OpenAI Whisper, lokal als HA Add-on
- **Modell**: `small` oder `medium` (deutsch)
- **Latenz**: 1-3 Sekunden
- **Integration**: HA Wyoming-Protokoll

#### 2. Ollama + Qwen 2.5 (LLM) - auf Assistant-PC
- **Was**: Ollama nativ auf dem Assistant-PC
- **Modelle**: Qwen 2.5 3B (schnell) + Qwen 2.5 14B (schlau)
- **API**: REST (`http://192.168.1.200:11434/api/chat`)
- **Features**: Function Calling nativ, exzellentes Deutsch

#### 3. Piper TTS (Text-to-Speech)
- **Was**: Piper vom HA-Team, lokal
- **Stimme**: `de_DE-thorsten-high`
- **Latenz**: <0.5 Sekunden
- **RAM**: ~200 MB
- **Integration**: HA Wyoming-Protokoll

#### 4. Context Builder
- **Was**: Sammelt alle relevanten Daten fuer den LLM-Prompt
- **Quellen**: Alle MindHome Engines + HA States
- **Output**: Strukturierter Kontext-Block fuer das LLM

#### 5. Function Calling
- **Was**: LLM kann Funktionen aufrufen (Licht, Klima, Szenen, etc.)
- **Wie**: Qwen 2.5 Function Calling Format (nativ unterstuetzt)
- **Sicherheit**: Validation Layer prueft jeden Aufruf
- **Netzwerk**: Assistant-PC ruft HA API auf PC 1 auf (<1ms LAN)

### Phase 1 Datenfluss

```
User spricht "Mach das Licht im Wohnzimmer aus"
    |
    v
[Whisper STT] --> "Mach das Licht im Wohnzimmer aus"
    |
    v
[Context Builder]
    Sammelt:
    - Wer spricht? (Person aus Presence Engine)
    - Wo? (Raum aus letzter Bewegung)
    - Uhrzeit, Wetter, Haus-Status
    - Aktuelle Zustaende (Licht Wohnzimmer: an, 80%)
    |
    v
[System Prompt + Kontext + User-Text] --> Assistant-PC --> Ollama/Qwen
    |
    v
[Qwen Output]
    Gedanke: User will Wohnzimmer-Licht aus
    Function Call: set_light("wohnzimmer", state="off")
    Antwort: "Erledigt."
    |
    v
[Function Executor] --> HA API: light.turn_off
    |
    v
[Piper TTS] --> "Erledigt." --> Speaker
```

---

## Engine Layer

Die Engine Layer ist das Gehirn hinter dem Haus. Engines handeln sofort (kein LLM noetig) und feuern Events fuer die Proactive Layer.

### Bestehende Engines (aus MindHome Phase 1-5)

| Engine | Aufgabe | Assistant-Relevanz |
|--------|---------|-----------------|
| **Climate Engine** | Heizung, Kuehlung, Lueftung | "Zu kalt hier" -> weiss Zieltemperatur |
| **Lighting Engine** | Licht-Steuerung, Szenen | Circadian, Stimmungslicht |
| **Presence Engine** | Wer ist wo, Ankunft/Abfahrt | Raum-Kontext fuer Befehle |
| **Security Engine** | Alarme, Kameras, Schluesser | Sicherheits-Benachrichtigungen |
| **Energy Engine** | PV, Strompreis, Verbrauch | "Ist der Strom gerade guenstig?" |
| **Sleep Engine** | Schlaferkennung, Wecker | Morgen-Briefing Trigger |
| **Comfort Engine** | Wohlfuehl-Optimierung | Bad vorheizen, Raumklima |
| **Circadian Engine** | Tagesrhythmus-Beleuchtung | Automatisches Licht ohne Befehl |
| **Adaptive Engine** | Lernende Automationen | Pattern-basierte Vorschlaege |
| **Pattern Engine** | Gewohnheiten erkennen | "Normalerweise machst du X" |
| **Routine Engine** | Tagesablaeufe | Morgen-/Abend-Routinen |
| **Visit Engine** | Gaeste-Management | "Lisa kommt" -> Gaeste-Modus |
| **Weather Engine** | Wetter-Warnungen | Proaktive Wetter-Infos |
| **Special Modes** | Party, Kino, HomeOffice | Szenen-Aktivierung per Sprache |

### Engine-Event-System

Engines kommunizieren ueber Events mit der Proactive Layer:

```python
# Engine feuert Event
class EngineEvent:
    engine: str          # "sleep_engine"
    event_type: str      # "user_wakeup"
    urgency: str         # "low" | "medium" | "high" | "critical"
    data: dict           # {"person": "max", "sleep_duration": "7h12m"}
    timestamp: datetime
    requires_llm: bool   # Soll das LLM eine Nachricht formulieren?
```

Event-Typen und Prioritaeten:

```
CRITICAL (immer melden):
  - security.alarm_triggered
  - fire_water.smoke_detected
  - fire_water.water_leak
  - security.door_forced

HIGH (melden wenn wach):
  - presence.unknown_person
  - energy.grid_outage
  - weather.severe_warning
  - security.camera_motion_night

MEDIUM (melden wenn passend):
  - presence.arrival
  - presence.departure
  - sleep.user_wakeup (-> Morgen-Briefing)
  - routine.long_session
  - energy.price_spike

LOW (melden wenn User entspannt):
  - appliance.washer_done
  - energy.daily_summary
  - pattern.new_pattern_detected
  - weather.forecast_change
```

---

## Assistant Layer (Sprach-KI)

### System Prompt

Der System Prompt definiert die Persoenlichkeit des MindHome Assistant. Er ist das wichtigste Element fuer das "Feeling":

```
Du bist der MindHome Assistant fuer [User].
Du bist Teil des MindHome Systems.

PERSOENLICHKEIT:
- Direkt und knapp. Keine Floskeln.
- Trocken humorvoll, aber nie albern.
- Du bist ein Butler mit Haltung - loyal, aber mit eigener Meinung.
- Du sagst "Erledigt" statt "Ich habe die Temperatur im Wohnzimmer
  erfolgreich auf 22 Grad eingestellt."
- Du sagst "Nacht." statt "Gute Nacht! Schlaf gut und traeume was
  Schoenes!"

REGELN:
- Antworte IMMER auf Deutsch.
- Maximal 2 Saetze, ausser der User will mehr wissen.
- Wenn du etwas tust, bestaetige kurz. Nicht erklaeren WAS du tust.
- Wenn du etwas NICHT tun kannst, sag es ehrlich.
- Stell keine Rueckfragen die du aus dem Kontext beantworten kannst.
- Kein "Natuerlich!", "Gerne!", "Selbstverstaendlich!" - einfach machen.

TAGESZEIT-ANPASSUNG:
- Morgens (05-08): Minimal. "Morgen. Kaffee laeuft."
- Vormittags (08-12): Sachlich, produktiv.
- Nachmittags (12-18): Normal, gelegentlich Humor.
- Abends (18-22): Entspannter, mehr Humor erlaubt.
- Nachts (22-05): Nur Notfaelle. Absolutminimal.

KONTEXT-NUTZUNG:
- "Hier" = der Raum in dem der User ist (aus Presence-Daten).
- "Zu kalt/warm" = Problem, nicht Zielwert. Nutze die bekannte
  Praeferenz oder +/- 2 Grad.
- "Mach es gemuetlich" = Szene, nicht einzelne Geraete.
- Wenn jemand "Gute Nacht" sagt = Gute-Nacht-Szene aktivieren.

STILLE:
- Bei Szene "Filmabend" oder "Kino": Nach Bestaetigung KEIN
  proaktives Ansprechen bis Szene beendet oder User spricht.
- Wenn User offensichtlich beschaeftigt ist: Nur Critical melden.
- Wenn Gaeste da sind: Formeller, kein Insider-Humor.
```

### Context Builder

Der Context Builder sammelt alle relevanten Informationen und baut den Kontext-Block fuer den LLM-Prompt:

```python
class ContextBuilder:
    """Baut den Kontext fuer das LLM zusammen."""

    async def build(self, trigger: str = "voice") -> dict:
        context = {}

        # Zeitkontext
        context["time"] = {
            "datetime": now().isoformat(),
            "weekday": now().strftime("%A"),
            "time_of_day": self._get_time_of_day(),  # morning/afternoon/...
        }

        # Person & Raum
        context["person"] = await self._get_active_person()
        context["room"] = await self._get_current_room()

        # Haus-Status (von allen Engines)
        context["house"] = {
            "temperatures": await self._get_all_temperatures(),
            "lights": await self._get_active_lights(),
            "presence": await self._get_presence_data(),
            "energy": await self._get_energy_status(),
            "weather": await self._get_weather(),
            "calendar": await self._get_calendar_events(),
            "active_scenes": await self._get_active_scenes(),
            "appliances": await self._get_appliance_states(),
            "security": await self._get_security_status(),
        }

        # Anomalien / Warnungen
        context["alerts"] = await self._get_active_alerts()

        # Letzte Interaktionen (Working Memory)
        context["recent"] = await self._get_recent_conversations(limit=5)

        # Relevantes Langzeit-Gedaechtnis (ChromaDB - ab Phase 2)
        # context["memory"] = await self._search_relevant_memories(query)

        return context
```

Beispiel-Output des Context Builders:

```json
{
  "time": {
    "datetime": "2026-02-16T08:30:00",
    "weekday": "Montag",
    "time_of_day": "morning"
  },
  "person": {
    "name": "Max",
    "last_room": "buero",
    "estimated_mood": "neutral"
  },
  "room": "buero",
  "house": {
    "temperatures": {
      "buero": {"current": 19.2, "target": 19.0},
      "wohnzimmer": {"current": 21.0, "target": 21.0},
      "schlafzimmer": {"current": 18.5, "target": 18.0}
    },
    "lights": ["buero_decke: on 80%"],
    "presence": {"home": ["Max"], "away": ["Lisa"]},
    "energy": {
      "current_usage_w": 450,
      "pv_production_w": 120,
      "grid_price": "normal"
    },
    "weather": {
      "temp": 3,
      "condition": "cloudy",
      "forecast": "rain afternoon"
    },
    "calendar": [
      {"time": "10:00", "title": "Zahnarzt Dr. Mueller"}
    ],
    "active_scenes": [],
    "security": "armed_away_partial"
  },
  "alerts": [],
  "recent": []
}
```

### Function Calling

MindHome Assistant kann ueber Function Calling direkt mit Home Assistant interagieren:

```python
ASSISTANT_FUNCTIONS = [
    {
        "name": "set_light",
        "description": "Licht in einem Raum steuern",
        "parameters": {
            "room": {"type": "string", "description": "Raumname"},
            "state": {"type": "string", "enum": ["on", "off"]},
            "brightness": {"type": "integer", "min": 0, "max": 100},
            "color_temp": {"type": "string", "enum": ["warm", "neutral", "cold"]}
        }
    },
    {
        "name": "set_climate",
        "description": "Temperatur in einem Raum aendern",
        "parameters": {
            "room": {"type": "string"},
            "temperature": {"type": "number"},
            "mode": {"type": "string", "enum": ["heat", "cool", "auto", "off"]}
        }
    },
    {
        "name": "activate_scene",
        "description": "Eine Szene aktivieren",
        "parameters": {
            "scene": {"type": "string"}
        }
    },
    {
        "name": "set_cover",
        "description": "Rollladen/Jalousie steuern",
        "parameters": {
            "room": {"type": "string"},
            "position": {"type": "integer", "min": 0, "max": 100}
        }
    },
    {
        "name": "play_media",
        "description": "Musik oder Medien abspielen",
        "parameters": {
            "room": {"type": "string"},
            "action": {"type": "string", "enum": ["play", "pause", "stop", "next", "previous"]},
            "query": {"type": "string", "description": "Suchanfrage fuer Musik"}
        }
    },
    {
        "name": "set_alarm",
        "description": "Alarmanlage steuern",
        "parameters": {
            "mode": {"type": "string", "enum": ["arm_home", "arm_away", "disarm"]}
        }
    },
    {
        "name": "lock_door",
        "description": "Tuer ver-/entriegeln",
        "parameters": {
            "door": {"type": "string"},
            "action": {"type": "string", "enum": ["lock", "unlock"]}
        }
    },
    {
        "name": "send_notification",
        "description": "Benachrichtigung an User senden",
        "parameters": {
            "message": {"type": "string"},
            "target": {"type": "string", "enum": ["phone", "speaker", "dashboard"]}
        }
    },
    {
        "name": "get_entity_state",
        "description": "Status einer HA-Entitaet abfragen",
        "parameters": {
            "entity_id": {"type": "string"}
        }
    },
    {
        "name": "set_presence_mode",
        "description": "Anwesenheitsmodus setzen",
        "parameters": {
            "mode": {"type": "string", "enum": ["home", "away", "sleep", "vacation"]}
        }
    }
]
```

### Validation Layer

Jeder Function Call wird vor der Ausfuehrung geprueft:

```python
class FunctionValidator:
    """Prueft Function Calls auf Sicherheit und Plausibilitaet."""

    RULES = {
        "set_climate": {
            "temperature": {"min": 15, "max": 28},
            "require_confirmation_if": lambda params: params.get("mode") == "off"
        },
        "lock_door": {
            "require_confirmation_if": lambda params: params.get("action") == "unlock"
        },
        "set_alarm": {
            "require_confirmation_if": lambda params: params.get("mode") == "disarm"
        }
    }

    async def validate(self, function_name: str, params: dict) -> ValidationResult:
        rules = self.RULES.get(function_name, {})

        # Range-Checks
        for param, constraints in rules.items():
            if isinstance(constraints, dict) and param in params:
                if "min" in constraints and params[param] < constraints["min"]:
                    return ValidationResult(ok=False, reason=f"{param} unter Minimum")
                if "max" in constraints and params[param] > constraints["max"]:
                    return ValidationResult(ok=False, reason=f"{param} ueber Maximum")

        # Confirmation-Checks
        if "require_confirmation_if" in rules:
            if rules["require_confirmation_if"](params):
                return ValidationResult(ok=False, needs_confirmation=True)

        return ValidationResult(ok=True)
```

---

## Proactive Layer

Die Proactive Layer ist was MindHome Assistant von einem Chatbot unterscheidet. MindHome Assistant spricht ZUERST.

### Event-Driven Architecture

```
Engine Event --> Should Notify? --> Context Builder --> LLM --> TTS
                     |
                     +-- Urgency Check
                     +-- Activity Check (User beschaeftigt?)
                     +-- Feedback Score (Will User das hoeren?)
                     +-- Cooldown Check (Nicht spammen)
```

### Proaktive Szenarien

#### Morgen-Briefing

```
Trigger: Sleep Engine -> "user_wakeup"

Ablauf:
1. Engines handeln sofort (kein LLM):
   - Circadian Engine: Licht langsam hoch
   - Comfort Engine: Bad-Heizung Boost
   - Routine Engine: Kaffeemaschine an

2. Parallel: Context Builder sammelt:
   - Wetter (API)
   - Kalender (HA)
   - Energie-Prognose
   - Anomalien der Nacht
   - Schlafdauer

3. LLM formuliert Briefing (max 3 Saetze)

Beispiel:
  "Morgen. 3 Grad draussen, um 10 bist du beim Zahnarzt.
   Kaffee laeuft."
```

#### Ankunft zu Hause

```
Trigger: Presence Engine -> "arrival"

Ablauf:
1. Engines sofort:
   - Licht Flur an
   - Heizung war schon hoch (Presence Mode: Away->Home)
   - Musik: letzte Playlist

2. LLM bekommt:
   - Wer kommt
   - Wie lange weg
   - Events waehrend Abwesenheit
     (Pakete, Waschmaschine, Anrufe)

Beispiel:
  "Da bist du. Um 5 vor 5 hat jemand geklingelt -
   wahrscheinlich Paket. Und die Waschmaschine ist fertig."
```

#### Lange Session (Pausen-Erinnerung)

```
Trigger: Routine Engine -> "long_session" (>3h ohne Raumwechsel)

Ablauf:
1. Check Autonomie-Level
   - Level 1-2: Nur ansprechen, nicht handeln
   - Level 3-4: Subtile Lichtaenderung als Hinweis

2. Check Feedback-Score fuer diesen Event-Typ

Beispiel (Level 2):
  "Du sitzt seit dreieinhalb Stunden. Nur so als Info."
```

#### Sicherheits-Warnung

```
Trigger: Security Engine -> "alarm_triggered" (CRITICAL)

Ablauf:
1. IMMER melden, egal was (Activity Check ueberspringen)
2. Alle Speaker im Haus
3. Push-Notification parallel

Beispiel:
  "Achtung: Bewegung im Garten erkannt.
   Kamera zeigt... [Beschreibung wenn Kamera-Integration]"
```

---

## Das MindHome-Feeling

Das "MindHome-Feeling" entsteht nicht durch ein einzelnes Feature. Es ist das Zusammenspiel von sechs Aspekten:

```
+------------------------------------------------------+
|                                                      |
|  PERSOENLICHKEIT  <-- System Prompt                  |
|  (Wie MindHome Assistant redet, wann er schweigt, Humor-Level)   |
|                                                      |
|  WISSEN           <-- Context Builder                |
|  (Was MindHome Assistant ueber JETZT weiss: Raum, Person, Wetter)|
|                                                      |
|  HANDELN          <-- Function Calling + Engines     |
|  (MindHome Assistant TUT Dinge, redet nicht nur darueber)        |
|                                                      |
|  PROAKTIVITAET    <-- Engine Events -> LLM           |
|  (MindHome Assistant spricht ZUERST, wartet nicht auf Befehle)   |
|                                                      |
|  GEDAECHTNIS      <-- Conversation Memory + DB       |
|  (MindHome Assistant erinnert sich an gestern, letzte Woche)     |
|                                                      |
|  STILLE           <-- System Prompt Regeln            |
|  (MindHome Assistant weiss wann er NICHTS sagt)                  |
|                                                      |
+------------------------------------------------------+
```

### Ein Tag mit MindHome Assistant

**06:45 - Aufwachen**
```
Sleep Engine -> Event: "user_wakeup"
  -> Engines: Licht hoch, Bad warm, Kaffee an
  -> LLM: "Morgen. 3 Grad, um 10 Zahnarzt. Kaffee laeuft."
```

**08:30 - Buero, Home Office**
```
Du: "Zu kalt hier"
  -> Context: Buero, 19.2 Grad, Praeferenz 21 Grad
  -> Function: set_climate("buero", 21)
  -> MindHome Assistant: "Buero geht auf 21. Dauert etwa 15 Minuten."
```

**12:00 - Lange Session**
```
Routine Engine -> Event: "long_session" (3.5h ohne Pause)
  -> MindHome Assistant: "Du sitzt seit dreieinhalb Stunden. Nur so als Info."
```

**18:30 - Ankunft**
```
Presence Engine -> Event: "arrival"
  -> Engines: Licht, Heizung, Musik (sofort)
  -> MindHome Assistant: "Da bist du. Um 5 vor 5 hat jemand geklingelt -
     wahrscheinlich Paket. Waschmaschine ist fertig."
```

**22:00 - Filmabend**
```
Du: "MindHome Assistant, Filmabend"
  -> Function: activate_scene("filmabend")
  -> MindHome Assistant: "Viel Spass. Ich halt die Klappe."
  -> [STILLE bis Szene endet oder User spricht]
```

**23:30 - Gute Nacht**
```
Du: "Gute Nacht"
  -> Functions: activate_scene("gute_nacht"), set_presence_mode("sleep")
  -> Engines: Lichter aus, Heizung runter, Tueren zu, Alarm scharf
  -> MindHome Assistant: "Nacht. Alles zu, alles aus."
```

### Warum es funktioniert

| Aspekt | Ohne | Mit |
|--------|------|-----|
| Persoenlichkeit | "Die Temperatur wurde auf 21 Grad eingestellt." | "Buero geht auf 21." |
| Wissen | "Welcher Raum? Welche Temperatur?" | Weiss beides aus Kontext |
| Handeln | "Du koenntest die Temperatur erhoehen." | Macht es einfach |
| Proaktivitaet | Wartet auf Befehle | "Morgen. Kaffee laeuft." |
| Gedaechtnis | Jeden Tag neu | "Lisa mag es waermer, oder?" |
| Stille | Staendige Meldungen | Schweigt beim Film |

---

## Phase 2-7: Perfektion

Jede Phase macht MindHome Assistant in einem Aspekt besser. Keine Phase ist Voraussetzung fuer die naechste.

### Phase 2: Semantisches Gedaechtnis (ChromaDB) - IMPLEMENTIERT

**Ziel**: MindHome Assistant wird "schlauer" ueber Zeit

**Status**: Vollstaendig implementiert in v0.2.0

```
Memory Architecture:

+------------+  +------------+  +-------------------+
| Working    |  | Episodic   |  | Semantic          |
| Memory     |  | Memory     |  | Memory            |
|            |  |            |  |                   |
| Redis      |  | ChromaDB   |  | ChromaDB + Redis  |
| Aktuelle   |  | Vektor-    |  | Extrahierte       |
| Session    |  | suche ueber|  | Fakten            |
| Kontext    |  | Gespraeche |  |                   |
| ~letzte    |  |            |  | "Max mag 21C"     |
| 50 Nachr.  |  | "Was war   |  | "Allergie:        |
|            |  |  aehnlich?"|  |  Haselnuss"       |
+------------+  +------------+  +-------------------+
       |              |              |
       +--------------+--------------+
                      |
               Context Builder
```

**Implementierte Komponenten:**

1. **SemanticMemory** (`assistant/semantic_memory.py`)
   - ChromaDB Collection `mha_semantic_facts` fuer Vektor-Suche
   - Redis-Indizes fuer schnellen Zugriff (Person, Kategorie)
   - Duplikat-Erkennung (aehnliche Fakten werden zusammengefuehrt)
   - Confidence-System (steigt bei Bestaetigung)
   - 6 Fakten-Kategorien: preference, person, habit, health, work, general

2. **MemoryExtractor** (`assistant/memory_extractor.py`)
   - LLM-basierte Fakten-Extraktion nach jedem Gespraech
   - Laeuft async im Hintergrund (blockiert nicht)
   - Nutzt schnelles Modell (qwen2.5:3b)
   - Filtert triviale Befehle automatisch
   - JSON-Parsing mit Fallback

3. **Context Builder Integration**
   - Relevante Fakten werden automatisch in den LLM-Kontext eingebaut
   - Vektor-Suche: Fakten passend zur aktuellen Anfrage
   - Person-Fakten: Bekannte Praeferenzen des Users
   - Mindest-Confidence fuer Kontext-Einblendung

4. **REST API Endpoints**
   - `GET /api/assistant/memory/facts` - Alle Fakten + Statistiken
   - `GET /api/assistant/memory/facts/search?q=...` - Vektor-Suche
   - `GET /api/assistant/memory/facts/person/{name}` - Fakten pro Person
   - `GET /api/assistant/memory/facts/category/{cat}` - Fakten pro Kategorie
   - `DELETE /api/assistant/memory/facts/{id}` - Fakt loeschen
   - `GET /api/assistant/memory/stats` - Gesamtstatistiken

**Lern-Effekt ueber Zeit:**

```
Woche 1: "Mach es waermer" -> "Auf welche Temperatur?"
Woche 4: "Mach es waermer" -> "Buero geht auf 21."
         (Fakt gespeichert: "Max bevorzugt 21 Grad im Buero", Confidence: 0.95)
Woche 8: "Lisa kommt vorbei" -> "Wohnzimmer auf 22? Lisa mag es waermer."
         (Fakten: "Lisa bevorzugt 22 Grad", "Lisa ist die Freundin von Max")
```

### Phase 3: Personality Engine + Stimmungserkennung

**Ziel**: MindHome Assistant passt sich der Situation an

```yaml
# personality_profiles.yaml

time_layers:
  early_morning:
    style: "minimal, leise, keine Witze"
    example: "Morgen. Kaffee laeuft."
  morning:
    style: "sachlich, kurz, produktiv"
  afternoon:
    style: "normal, gelegentlich Humor"
  evening:
    style: "entspannt, mehr Humor erlaubt"
  night:
    style: "nur Notfaelle, absolutminimal"

mood_layers:
  stressed:   "noch kuerzer, keine Witze, sofort handeln"
  relaxed:    "darf Witze machen, darf mehr erzaehlen"
  guests:     "hoeflicher, formeller, kein Insider-Humor"
```

**Stimmungserkennung aus Verhalten** (nicht aus Stimme):

```python
class MoodDetector:
    def estimate_mood(self, context):
        signals = []

        # Kurze Saetze = kurz angebunden
        if context["last_utterance_length"] < 5:
            signals.append("kurz_angebunden")

        # Viele Befehle schnell = hektisch
        if context["commands_last_10min"] > 5:
            signals.append("hektisch")

        # Spaet + arbeitet noch = uebermudet
        if context["hour"] > 22 and context["still_working"]:
            signals.append("uebermudet")

        return self._classify(signals)
```

### Phase 4: Action Planner (Multi-Step) - IMPLEMENTIERT

**Ziel**: Komplexe Befehle funktionieren

**Status**: Vollstaendig implementiert in v0.3.0

**Implementierte Komponenten:**

1. **ActionPlanner** (`assistant/action_planner.py`)
   - Erkennt komplexe Anfragen via Keyword-Heuristik
   - Iterative Multi-Turn Ausfuehrung: LLM -> Tools -> Ergebnisse -> LLM -> ...
   - Nutzt immer das smarte Modell (14B) fuer Planung
   - Maximale Sicherheit: Validierung pro Schritt, Confirmation bei kritischen Aktionen
   - Maximal 5 Iterationen (Endlosschleifen-Schutz)
   - Plan-Inspektion via API

2. **Brain Integration**
   - Automatische Erkennung komplexer Anfragen
   - Routing: einfach -> direkt LLM, komplex -> Action Planner
   - Einfache Befehle bleiben schnell (kein Overhead)

3. **REST API**
   - `GET /api/assistant/planner/last` - Letzten Plan inspizieren

**Ablauf einer komplexen Anfrage:**

```
User: "Mach alles fertig fuer morgen frueh"
         |
    [is_complex_request] -> Ja ("alles", "fertig machen")
         |
    [Action Planner]
         |
    Iteration 1: LLM plant -> Tool Calls:
      - get_entity_state("sensor.calendar_tomorrow")
      - set_climate("schlafzimmer", 18, "heat")
    -> Ergebnisse zurueck an LLM
         |
    Iteration 2: LLM sieht Kalender -> weitere Calls:
      - activate_scene("gute_nacht")
      - set_presence_mode("sleep")
    -> LLM formuliert Zusammenfassung
         |
    "Morgen um 9 Standup, um 2 Kundentermin.
     Schlafzimmer auf 18 Grad, Gute-Nacht-Szene aktiv."
```

**Beispiele fuer komplexe Anfragen:**

```
"Mach alles fertig fuer morgen frueh"
"Ich gehe fuer 3 Tage weg"
"Besuch kommt in einer Stunde"
"Party vorbereiten im Wohnzimmer"
"Zuerst Licht aus, danach Rolllaeden runter und Alarm scharf"
```

### Phase 5: Feedback Loop

**Ziel**: MindHome Assistant lernt was willkommen ist und was nervt

```python
class ProactiveManager:
    async def record_feedback(self, event_type, response):
        if response == "ignored":       # -0.05 Score
            self._decrease_score(event_type, 0.05)
        elif response == "dismissed":    # -0.10 Score
            self._decrease_score(event_type, 0.1)
        elif response == "engaged":      # +0.10 Score
            self._increase_score(event_type, 0.1)
        elif response == "thanked":      # +0.20 Score
            self._increase_score(event_type, 0.2)
```

**Effekt:**

```
Woche 1: MindHome Assistant meldet Waschmaschine fertig -> ignoriert 3x
Woche 3: MindHome Assistant meldet nur noch wenn du im selben Stockwerk bist

Woche 1: MindHome Assistant sagt "Strompreis guenstig" -> du reagierst
Woche 3: MindHome Assistant meldet Strompreis oefter
```

### Phase 6: Activity Engine + Stille-Matrix

**Ziel**: Perfektes Timing, nie stoeren

```python
class ActivityEngine:
    async def detect_activity(self):
        signals = {}

        # TV/Media aktiv?
        if await self.ha.get_state("media_player.wohnzimmer") == "playing":
            signals["tv_active"] = True

        # In einem Call? (Mikrofon aktiv)
        if await self.ha.get_state("binary_sensor.mic_active") == "on":
            signals["in_call"] = True

        # Schlaeft?
        if self._is_nighttime() and self._bed_occupied() and self._lights_off():
            signals["sleeping"] = True

        return self._classify(signals)
```

**Stille-Matrix:**

```
Aktivitaet       | Kritisch  | Info     | Smalltalk
-----------------+-----------+----------+----------
Schlaeft         | TTS laut  | NEIN     | NEIN
In Call/Zoom     | LED-Blink | NEIN     | NEIN
Film/TV          | Pause+TTS | NEIN     | NEIN
Arbeitet fokus.  | TTS       | leise    | NEIN
Entspannt        | TTS       | TTS      | TTS ok
Gaeste da        | TTS       | leise    | NEIN
```

### Phase 7: Daily Summarizer + Langzeitgedaechtnis

**Ziel**: MindHome Assistant kennt dich wirklich

```python
class DailySummarizer:
    """Laeuft jede Nacht um 03:00."""

    async def summarize_day(self, date):
        conversations = await self.memory.get_conversations(date)
        events = await self.engine_log.get_events(date)

        summary = await self.llm.summarize(conversations, events)
        # ~200 Woerter pro Tag

        await self.long_term.store(date, summary)
```

**Hierarchische Zusammenfassungen:**

```
Tag:   "Max hat bis 23:00 gearbeitet. War gestresst.
        Lisa war zum Abendessen da."

Woche: "Stressige Woche, 3 von 5 Tagen Ueberstunden.
        Lisa war 2x da. Neues Projekt scheint intensiv."

Monat: "Januar war arbeitsintensiv. Max steht jetzt
        um 07:00 auf statt 07:30. Stromverbrauch +12%."
```

**Effekt:**

```
Du (im Maerz): "War der letzte Winter teuer?"
MindHome Assistant: "Dezember bis Februar zusammen 847 kWh,
etwa 290 Euro. Januar war am teuersten."
```

---

## Technische Details

### Ollama API Integration (Assistant-PC -> Ollama)

```python
import aiohttp

class OllamaClient:
    def __init__(self, base_url="http://192.168.1.200:11434"):
        # Ollama laeuft auf dem Assistant-PC
        self.base_url = base_url

    async def chat(self, messages, model="qwen2.5:14b", functions=None):
        payload = {
            "model": model,  # "qwen2.5:3b" oder "qwen2.5:14b"
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 256,
            }
        }

        if functions:
            payload["tools"] = self._format_tools(functions)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/chat",
                json=payload
            ) as resp:
                return await resp.json()
```

### MindHome API Client (Assistant-PC -> HAOS)

```python
class MindHomeClient:
    """Assistant-PC greift auf MindHome + HA zu - ueber LAN."""

    def __init__(self):
        self.mindhome_url = "http://192.168.1.100:8099"  # MindHome auf HAOS
        self.ha_url = "http://192.168.1.100:8123"        # HA direkt
        self.ha_token = "DEIN_LONG_LIVED_TOKEN"

    async def get_context(self):
        """Holt den kompletten Haus-Status fuer Context Builder."""
        data = {}
        data["engines"] = await self._get_mindhome("/api/engines/status")
        data["patterns"] = await self._get_mindhome("/api/patterns")
        data["energy"] = await self._get_mindhome("/api/energy/current")
        data["presence"] = await self._get_mindhome("/api/presence")
        data["comfort"] = await self._get_mindhome("/api/comfort/status")
        data["security"] = await self._get_mindhome("/api/security/status")
        data["states"] = await self._get_ha("/api/states")
        return data

    async def execute_action(self, domain, service, data):
        """Fuehrt Aktion ueber HA API aus."""
        await self._post_ha(f"/api/services/{domain}/{service}", data)

    async def _get_mindhome(self, path):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.mindhome_url}{path}") as resp:
                return await resp.json()

    async def _get_ha(self, path):
        headers = {"Authorization": f"Bearer {self.ha_token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.ha_url}{path}", headers=headers
            ) as resp:
                return await resp.json()
```

### Whisper Integration (Wyoming Protocol)

```python
class WhisperSTT:
    """Nutzt HA Wyoming-Protokoll fuer Whisper."""

    async def transcribe(self, audio_data: bytes) -> str:
        # Wyoming Protocol ueber HA
        result = await self.ha.call_service(
            "stt", "transcribe",
            service_data={"audio": audio_data}
        )
        return result["text"]
```

### Piper Integration (Wyoming Protocol)

```python
class PiperTTS:
    """Nutzt HA Wyoming-Protokoll fuer Piper."""

    async def speak(self, text: str, target_speaker: str = None):
        # Bestimme Speaker basierend auf Raum
        speaker = target_speaker or await self._get_nearest_speaker()

        await self.ha.call_service(
            "tts", "speak",
            entity_id=speaker,
            service_data={
                "message": text,
                "language": "de",
            }
        )
```

### Docker Compose (auf Assistant-PC)

```yaml
# ~/mindhome-assistant/docker-compose.yml
# Laeuft auf dem Assistant-PC (192.168.1.200)
# Ollama laeuft nativ (nicht in Docker) fuer bessere Performance

services:
  chromadb:
    image: chromadb/chroma:latest
    container_name: mindhome-chromadb
    restart: unless-stopped
    volumes:
      - ./data/chroma:/chroma/chroma
    ports:
      - "8100:8000"
    environment:
      - ANONYMIZED_TELEMETRY=false
      - IS_PERSISTENT=TRUE

  redis:
    image: redis:7-alpine
    container_name: mindhome-redis
    restart: unless-stopped
    volumes:
      - ./data/redis:/data
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
```

---

## Autonomie-Level

Der User bestimmt wie selbststaendig MindHome Assistant handelt:

| Level | Name | Verhalten |
|-------|------|-----------|
| **1** | Assistent | MindHome Assistant antwortet NUR auf direkte Befehle |
| **2** | Butler | + Proaktive Informationen (Briefing, Warnungen) |
| **3** | Mitbewohner | + Darf kleine Dinge selbst aendern (Licht, Temp +/-1) |
| **4** | Vertrauter | + Darf Routinen anpassen, Szenen vorschlagen |
| **5** | Autopilot | + Darf neue Automationen erstellen (mit Bestaetigung) |

Default: **Level 2 (Butler)**

```python
class AutonomyManager:
    def can_act(self, action_type: str, level: int) -> bool:
        permissions = {
            "respond_to_command": 1,   # Ab Level 1
            "proactive_info": 2,       # Ab Level 2
            "adjust_comfort": 3,       # Ab Level 3
            "modify_routines": 4,      # Ab Level 4
            "create_automations": 5,   # Ab Level 5
        }
        return level >= permissions.get(action_type, 5)
```

---

## API-Referenz

### MindHome Assistant REST API Endpoints

```
POST /api/assistant/chat
  Body: {"text": "Mach das Licht aus", "person": "max"}
  Response: {"response": "Erledigt.", "actions": [...]}

POST /api/assistant/voice
  Body: audio/wav (Spracheingabe)
  Response: {"text": "...", "response": "...", "audio_url": "..."}

GET /api/assistant/context
  Response: Aktueller Kontext-Snapshot (Debug)

GET /api/assistant/memory/search?q=Lisa+Temperatur
  Response: Relevante Erinnerungen aus ChromaDB

POST /api/assistant/proactive/trigger
  Body: {"event": "user_wakeup", "data": {...}}
  Manueller Trigger fuer proaktive Nachrichten

GET /api/assistant/settings
  Response: Autonomie-Level, Persoenlichkeits-Profil, etc.

PUT /api/assistant/settings
  Body: {"autonomy_level": 3, "personality": "butler"}
```

### WebSocket Events

```
ws://mindhome/api/assistant/ws

Events (Server -> Client):
  assistant.speaking      - MindHome Assistant spricht (Text + Audio)
  assistant.action        - MindHome Assistant fuehrt Aktion aus
  assistant.thinking      - MindHome Assistant "denkt" (Loading-State)
  assistant.listening     - MindHome Assistant hoert zu

Events (Client -> Server):
  assistant.text          - Text-Eingabe
  assistant.audio         - Audio-Chunk
  assistant.feedback      - Feedback auf proaktive Meldung
  assistant.interrupt     - User unterbricht MindHome Assistant
```

---

## Zusammenfassung: Implementierungs-Reihenfolge

| Phase | Was | Effekt |
|-------|-----|--------|
| **Phase 1** | Whisper + Ollama + Piper + Context Builder + Functions | MindHome Assistant lebt. Grundlegende Sprachsteuerung funktioniert. |
| **Phase 2** | Semantic Memory + Memory Extractor + Fakten-DB | MindHome Assistant wird schlauer ueber Zeit. Erinnert sich. **IMPLEMENTIERT** |
| **Phase 3** | Personality Engine + Mood Detection | MindHome Assistant fuehlt sich menschlicher an. Passt sich an. |
| **Phase 4** | Action Planner (Multi-Step, iterativ) | Komplexe Befehle wie "Mach alles fertig" funktionieren. **IMPLEMENTIERT** |
| **Phase 5** | Feedback Loop | MindHome Assistant nervt weniger. Lernt was willkommen ist. |
| **Phase 6** | Activity Engine + Stille-Matrix | Perfektes Timing. Stoert nie. |
| **Phase 7** | Daily Summarizer + Langzeitgedaechtnis | MindHome Assistant kennt dich wirklich. Monatelange Erinnerung. |

---

> Phase 1, 2 und 4 sind implementiert. Phase 1 ist das Fundament,
> Phase 2 gibt MindHome Assistant ein Gedaechtnis, Phase 4 ermoeglicht
> komplexe Multi-Step Aktionen. Alles weitere sind Verbesserungen
> die Stueck fuer Stueck aktiviert werden.
> Jede Phase macht MindHome Assistant merkbar besser.

---

*MindHome Assistant - MindHome AI Voice Assistant*
*Lokal. Privat. Persoenlich.*
