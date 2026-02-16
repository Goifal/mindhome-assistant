#!/bin/bash
# ============================================================
# MindHome Assistant - Ein-Klick-Installation
# Installiert alles auf dem Assistant-PC (Ubuntu Server)
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

MHA_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}  MindHome Assistant - Installation${NC}"
echo -e "${BLUE}  Lokaler KI-Sprachassistent${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

# --- Schritt 1: System pruefen ---
echo -e "${YELLOW}[1/6] System pruefen...${NC}"

if [ "$(id -u)" -eq 0 ]; then
    echo -e "${RED}Bitte NICHT als root ausfuehren. Nutze deinen normalen User.${NC}"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Docker nicht gefunden. Installiere Docker...${NC}"
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) \
        signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"
    echo -e "${GREEN}Docker installiert.${NC}"
    echo -e "${YELLOW}WICHTIG: Log dich aus und wieder ein, damit Docker ohne sudo geht.${NC}"
    echo -e "${YELLOW}Danach fuehre install.sh nochmal aus.${NC}"
    exit 0
fi

echo -e "${GREEN}Docker: OK${NC}"

if docker compose version &> /dev/null; then
    echo -e "${GREEN}Docker Compose: OK${NC}"
else
    echo -e "${RED}Docker Compose nicht gefunden. Bitte Docker aktualisieren.${NC}"
    exit 1
fi

# --- Schritt 2: Ollama installieren ---
echo ""
echo -e "${YELLOW}[2/6] Ollama pruefen...${NC}"

if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}Ollama nicht gefunden. Installiere...${NC}"
    curl -fsSL https://ollama.ai/install.sh | sh
    echo -e "${GREEN}Ollama installiert.${NC}"
else
    echo -e "${GREEN}Ollama: OK${NC}"
fi

# Ollama von aussen erreichbar machen
if ! grep -q "OLLAMA_HOST=0.0.0.0" /etc/systemd/system/ollama.service.d/override.conf 2>/dev/null; then
    echo -e "${YELLOW}Konfiguriere Ollama fuer Netzwerk-Zugriff...${NC}"
    sudo mkdir -p /etc/systemd/system/ollama.service.d/
    echo -e "[Service]\nEnvironment=\"OLLAMA_HOST=0.0.0.0\"" | \
        sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null
    sudo systemctl daemon-reload
    sudo systemctl restart ollama
    echo -e "${GREEN}Ollama hoert jetzt auf 0.0.0.0:11434${NC}"
fi

# --- Schritt 3: Modelle herunterladen ---
echo ""
echo -e "${YELLOW}[3/6] LLM-Modelle pruefen...${NC}"

# Warte bis Ollama bereit ist
for i in $(seq 1 10); do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        break
    fi
    echo "  Warte auf Ollama... ($i/10)"
    sleep 2
done

if ! ollama list 2>/dev/null | grep -q "qwen2.5:3b"; then
    echo -e "${YELLOW}Lade Qwen 2.5 3B (schnelles Modell, ~2 GB)...${NC}"
    ollama pull qwen2.5:3b
    echo -e "${GREEN}Qwen 2.5 3B: OK${NC}"
else
    echo -e "${GREEN}Qwen 2.5 3B: bereits vorhanden${NC}"
fi

if ! ollama list 2>/dev/null | grep -q "qwen2.5:14b"; then
    echo ""
    echo -e "${YELLOW}Moechtest du auch das schlaue Modell laden? (Qwen 2.5 14B, ~9 GB)${NC}"
    echo -e "${YELLOW}Das braucht ~16 GB RAM, ist aber viel schlauer.${NC}"
    read -p "Herunterladen? (j/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Jj]$ ]]; then
        ollama pull qwen2.5:14b
        echo -e "${GREEN}Qwen 2.5 14B: OK${NC}"
    else
        echo -e "${YELLOW}Uebersprungen. Kann spaeter mit 'ollama pull qwen2.5:14b' nachgeholt werden.${NC}"
    fi
else
    echo -e "${GREEN}Qwen 2.5 14B: bereits vorhanden${NC}"
fi

# --- Schritt 4: Konfiguration ---
echo ""
echo -e "${YELLOW}[4/6] Konfiguration...${NC}"

cd "$MHA_DIR"

if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo -e "${YELLOW}============================================================${NC}"
    echo -e "${YELLOW}  WICHTIG: .env Datei konfigurieren!${NC}"
    echo -e "${YELLOW}============================================================${NC}"
    echo ""
    echo "  Bearbeite die Datei: $MHA_DIR/.env"
    echo ""
    echo "  Mindestens diese Werte anpassen:"
    echo "    HA_URL=http://DEINE-HA-IP:8123"
    echo "    HA_TOKEN=DEIN_LONG_LIVED_ACCESS_TOKEN"
    echo "    USER_NAME=DEIN_NAME"
    echo ""
    read -p "Moechtest du die .env jetzt bearbeiten? (j/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Jj]$ ]]; then
        if command -v nano &> /dev/null; then
            nano .env
        else
            vi .env
        fi
    else
        echo -e "${YELLOW}Vergiss nicht, die .env spaeter zu bearbeiten!${NC}"
    fi
else
    echo -e "${GREEN}.env existiert bereits${NC}"
fi

# --- Schritt 5: Daten-Verzeichnisse ---
echo ""
echo -e "${YELLOW}[5/6] Verzeichnisse erstellen...${NC}"
mkdir -p data/chroma data/redis data/assistant
echo -e "${GREEN}Daten-Verzeichnisse: OK${NC}"

# --- Schritt 6: Docker starten ---
echo ""
echo -e "${YELLOW}[6/6] MindHome Assistant starten...${NC}"

docker compose build
docker compose up -d

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  MindHome Assistant ist installiert und gestartet!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  Status:     docker compose ps"
echo "  Logs:       docker compose logs -f assistant"
echo "  Stoppen:    docker compose down"
echo "  Neustarten: docker compose restart"
echo ""
echo "  API:        http://$(hostname -I | awk '{print $1}'):8200"
echo "  Docs:       http://$(hostname -I | awk '{print $1}'):8200/docs"
echo "  Health:     http://$(hostname -I | awk '{print $1}'):8200/api/assistant/health"
echo ""
echo "  Test:"
echo "    curl -X POST http://localhost:8200/api/assistant/chat \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"text\": \"Hallo\", \"person\": \"Max\"}'"
echo ""
echo -e "${BLUE}Viel Spass mit MindHome Assistant!${NC}"
