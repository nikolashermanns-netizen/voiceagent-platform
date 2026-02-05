#!/bin/bash
# VoiceAgent Platform - Server Setup & Update Script
# Verbindet sich per SSH auf den Server und richtet alles ein.
#
# Verwendung:
#   ./update_server.sh          - Komplett-Setup (erster Start oder Update)
#   ./update_server.sh update   - Nur Git pull + rebuild + restart
#   ./update_server.sh logs     - Live-Logs vom Server anzeigen
#   ./update_server.sh status   - Service-Status anzeigen
#   ./update_server.sh stop     - Services stoppen
#   ./update_server.sh ssh      - SSH-Session oeffnen

set -e

SSH_HOST="bot"
REMOTE_DIR="/opt/voiceagent-platform"
GIT_REPO="git@github.com:nikolashermanns-netizen/voiceagent-platform.git"

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[Server]${NC} $1"; }
warn() { echo -e "${YELLOW}[Server]${NC} $1"; }
error(){ echo -e "${RED}[Server]${NC} $1"; exit 1; }
info() { echo -e "${CYAN}[Server]${NC} $1"; }

# Lokale Aenderungen pruefen, committen und pushen
check_local_changes() {
    cd "$(dirname "$0")"
    cd "$(git -C . rev-parse --show-toplevel)"

    if [ -n "$(git status --porcelain)" ]; then
        warn "Lokale Aenderungen gefunden:"
        echo ""
        git status --short
        echo ""
        read -p "$(echo -e "${YELLOW}[Lokal]${NC} Aenderungen committen und pushen? (j/n): ")" answer
        if [ "$answer" = "j" ] || [ "$answer" = "J" ] || [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
            log "Committe und pushe..."
            git add -A
            git commit -m "auto"
            git push
            log "Push erfolgreich."
        else
            warn "Uebersprungen. Aenderungen bleiben lokal."
        fi
    else
        log "Keine lokalen Aenderungen."
    fi
}

# SSH-Verbindung testen
check_ssh() {
    log "Teste SSH-Verbindung zu '$SSH_HOST'..."
    ssh -o ConnectTimeout=5 "$SSH_HOST" "echo ok" > /dev/null 2>&1 \
        || error "SSH-Verbindung zu '$SSH_HOST' fehlgeschlagen. Pruefe ~/.ssh/config"
    log "SSH-Verbindung OK."
}

# Komplett-Setup: Docker, Git, Env, Build, Start
setup() {
    check_local_changes
    check_ssh

    log "Starte Server-Setup auf '$SSH_HOST'..."

    ssh "$SSH_HOST" bash -s -- "$REMOTE_DIR" "$GIT_REPO" << 'REMOTE_SCRIPT'
set -e
REMOTE_DIR="$1"
GIT_REPO="$2"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
log()  { echo -e "${GREEN}[Remote]${NC} $1"; }
warn() { echo -e "${YELLOW}[Remote]${NC} $1"; }
error(){ echo -e "${RED}[Remote]${NC} $1"; exit 1; }

# Docker Compose Befehl erkennen (v2 Plugin oder v1 Standalone)
detect_compose() {
    if docker compose version &> /dev/null; then
        COMPOSE="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE="docker-compose"
    else
        COMPOSE=""
    fi
}

# 1. Docker pruefen/installieren
if ! command -v docker &> /dev/null; then
    log "Docker nicht gefunden. Installiere Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo systemctl enable docker
    sudo systemctl start docker
    sudo usermod -aG docker "$USER"
    log "Docker installiert."
else
    log "Docker gefunden: $(docker --version)"
fi

# 2. Docker Compose pruefen/installieren
detect_compose
if [ -z "$COMPOSE" ]; then
    log "Docker Compose nicht gefunden. Installiere..."
    # Versuche erst das Plugin
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin 2>/dev/null && detect_compose
    # Falls Plugin nicht verfuegbar, installiere standalone
    if [ -z "$COMPOSE" ]; then
        log "Plugin nicht verfuegbar, installiere docker-compose standalone..."
        sudo apt-get install -y docker-compose 2>/dev/null || {
            COMPOSE_VERSION="2.24.5"
            sudo curl -L "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
            sudo chmod +x /usr/local/bin/docker-compose
        }
        detect_compose
    fi
fi

if [ -z "$COMPOSE" ]; then
    error "Docker Compose konnte nicht installiert werden"
fi
log "Docker Compose: $COMPOSE ($($COMPOSE version 2>/dev/null || echo 'unbekannt'))"

# 3. Git pruefen
if ! command -v git &> /dev/null; then
    log "Git installieren..."
    sudo apt-get update && sudo apt-get install -y git
fi

# 4. Repo clonen oder aktualisieren
if [ -d "$REMOTE_DIR/.git" ]; then
    log "Repo existiert. Pulling latest..."
    cd "$REMOTE_DIR"
    git pull || error "Git pull fehlgeschlagen"
else
    log "Repo clonen nach $REMOTE_DIR..."
    sudo mkdir -p "$(dirname "$REMOTE_DIR")"
    sudo chown "$USER:$USER" "$(dirname "$REMOTE_DIR")"
    git clone "$GIT_REPO" "$REMOTE_DIR" || error "Git clone fehlgeschlagen"
    cd "$REMOTE_DIR"
fi

# 5. In voiceagent-platform Unterordner wechseln
cd "$REMOTE_DIR/voiceagent-platform"

# 6. .env erstellen falls nicht vorhanden
if [ ! -f .env ]; then
    warn ".env existiert nicht. Erstelle aus .env.example..."
    cp .env.example .env
    warn "WICHTIG: .env auf dem Server bearbeiten mit: ssh bot 'nano $REMOTE_DIR/voiceagent-platform/.env'"
fi

# 7. Datenverzeichnisse erstellen
mkdir -p data workspace config

# 7b. Firewall pruefen/konfigurieren fuer SIP/RTP
log "Pruefe Firewall-Regeln..."

# Sipgate IP Ranges
SIPGATE_SIP="217.10.68.0/24"
SIPGATE_MEDIA="217.10.64.0/20"

# SIP Port 5060 nur von Sipgate (pruefen ob Regel existiert)
if ! sudo iptables -C INPUT -p udp -s "$SIPGATE_SIP" --dport 5060 -j ACCEPT 2>/dev/null; then
    log "Fuege Firewall-Regel hinzu: SIP 5060 von Sipgate"
    sudo iptables -I INPUT 8 -p udp -s "$SIPGATE_SIP" --dport 5060 -j ACCEPT
else
    log "SIP 5060 Regel existiert bereits"
fi

# RTP Ports 4000-4100 nur von Sipgate Media Servern
# Alte offene Regel entfernen falls vorhanden
if sudo iptables -C INPUT -p udp --dport 4000:4100 -j ACCEPT 2>/dev/null; then
    log "Entferne offene RTP-Regel (4000-4100 von allen)"
    sudo iptables -D INPUT -p udp --dport 4000:4100 -j ACCEPT
fi
# Sipgate-only Regel hinzufuegen
if ! sudo iptables -C INPUT -p udp -s "$SIPGATE_MEDIA" --dport 4000:4100 -j ACCEPT 2>/dev/null; then
    log "Fuege Firewall-Regel hinzu: RTP 4000-4100 von Sipgate Media"
    sudo iptables -I INPUT 8 -p udp -s "$SIPGATE_MEDIA" --dport 4000:4100 -j ACCEPT
else
    log "RTP 4000-4100 Regel existiert bereits"
fi

# API Port 8085 nur ueber WireGuard (10.200.200.0/24)
if sudo iptables -C INPUT -p tcp --dport 8085 -j ACCEPT 2>/dev/null; then
    log "Entferne offene API-Regel (8085 von allen)"
    sudo iptables -D INPUT -p tcp --dport 8085 -j ACCEPT
fi
if ! sudo iptables -C INPUT -p tcp -s 10.200.200.0/24 --dport 8085 -j ACCEPT 2>/dev/null; then
    log "Fuege Firewall-Regel hinzu: API 8085 nur via WireGuard"
    sudo iptables -I INPUT 8 -p tcp -s 10.200.200.0/24 --dport 8085 -j ACCEPT
else
    log "API 8085 WireGuard-Regel existiert bereits"
fi

log "Firewall-Regeln konfiguriert"

# 8. Docker Images bauen
log "Baue Docker Images..."
$COMPOSE build || error "Docker build fehlgeschlagen"

# Sandbox-Image
if [ -d agents/code_agent/sandbox ]; then
    log "Baue Sandbox-Image..."
    docker build -t code-sandbox-python agents/code_agent/sandbox/ || warn "Sandbox build fehlgeschlagen (nicht kritisch)"
fi

# 9. Services starten
log "Starte Services..."
$COMPOSE down 2>/dev/null || true
$COMPOSE up -d voiceagent-core || error "Service-Start fehlgeschlagen"

# 10. Status
echo ""
log "Setup abgeschlossen!"
echo ""
$COMPOSE ps
echo ""
log "Server laeuft auf Port 8085"
REMOTE_SCRIPT

    echo ""
    log "Server-Setup abgeschlossen!"
    info "Env bearbeiten:  ssh $SSH_HOST 'nano $REMOTE_DIR/voiceagent-platform/.env'"
    info "Logs anzeigen:   $0 logs"
    info "Status pruefen:  $0 status"
}

# Nur Update: Git pull + rebuild + restart
update() {
    check_local_changes
    check_ssh
    log "Update auf '$SSH_HOST'..."

    ssh "$SSH_HOST" bash -s -- "$REMOTE_DIR" << 'REMOTE_SCRIPT'
set -e
REMOTE_DIR="$1"

# Docker Compose Befehl erkennen
if docker compose version &> /dev/null; then
    COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE="docker-compose"
else
    echo -e "\033[0;31m[Remote]\033[0m Docker Compose nicht gefunden"; exit 1
fi

cd "$REMOTE_DIR/voiceagent-platform"

echo -e "\033[0;32m[Remote]\033[0m Pulling latest changes..."
git -C "$REMOTE_DIR" pull

echo -e "\033[0;32m[Remote]\033[0m Stopping services..."
$COMPOSE down 2>/dev/null || true

echo -e "\033[0;32m[Remote]\033[0m Rebuilding..."
$COMPOSE build

echo -e "\033[0;32m[Remote]\033[0m Starting services..."
$COMPOSE up -d voiceagent-core

echo ""
echo -e "\033[0;32m[Remote]\033[0m Update abgeschlossen!"
$COMPOSE ps
REMOTE_SCRIPT

    log "Update abgeschlossen!"
}

# Live-Logs
logs() {
    check_ssh
    log "Zeige Live-Logs von '$SSH_HOST'..."
    ssh "$SSH_HOST" "cd $REMOTE_DIR/voiceagent-platform && if docker compose version &>/dev/null; then docker compose logs -f --tail=100; else docker-compose logs -f --tail=100; fi"
}

# Status
status() {
    check_ssh
    log "Service-Status auf '$SSH_HOST':"
    echo ""
    ssh "$SSH_HOST" "cd $REMOTE_DIR/voiceagent-platform && if docker compose version &>/dev/null; then docker compose ps; else docker-compose ps; fi && echo '' && docker ps --filter 'name=voiceagent' --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
}

# Stop
stop() {
    check_ssh
    log "Stoppe Services auf '$SSH_HOST'..."
    ssh "$SSH_HOST" "cd $REMOTE_DIR/voiceagent-platform && if docker compose version &>/dev/null; then docker compose down; else docker-compose down; fi"
    log "Services gestoppt."
}

# SSH-Session
open_ssh() {
    log "Oeffne SSH-Session zu '$SSH_HOST'..."
    ssh "$SSH_HOST"
}

# Hauptmenue
case "${1:-setup}" in
    setup)   setup ;;
    update)  update ;;
    logs)    logs ;;
    status)  status ;;
    stop)    stop ;;
    ssh)     open_ssh ;;
    *)
        echo "VoiceAgent Platform - Server Management"
        echo ""
        echo "Verwendung: $0 {setup|update|logs|status|stop|ssh}"
        echo ""
        echo "  setup    - Komplett-Setup (Docker, Git, Build, Start)"
        echo "  update   - Git pull + rebuild + restart"
        echo "  logs     - Live-Logs anzeigen"
        echo "  status   - Service-Status"
        echo "  stop     - Services stoppen"
        echo "  ssh      - SSH-Session oeffnen"
        echo ""
        echo "SSH-Host: $SSH_HOST"
        echo "Remote-Verzeichnis: $REMOTE_DIR"
        ;;
esac
