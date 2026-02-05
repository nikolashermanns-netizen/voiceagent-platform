#!/bin/bash
# VoiceAgent Platform - Server Update Script
# Zieht die neuesten Aenderungen vom Git-Repo, baut neu und startet den Server.
#
# Verwendung: ./update_server.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[Update]${NC} $1"; }
warn() { echo -e "${YELLOW}[Update]${NC} $1"; }
error() { echo -e "${RED}[Update]${NC} $1"; exit 1; }

cd "$SCRIPT_DIR"

# 1. Git Pull
log "Pulling latest changes from git..."
git pull || error "Git pull fehlgeschlagen"

# 2. Services stoppen
log "Stopping running services..."
docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true

# 3. Images neu bauen
log "Rebuilding Docker images..."
docker compose -f "$COMPOSE_FILE" build || error "Docker build fehlgeschlagen"

# Sandbox-Image separat bauen
if [ -d "$SCRIPT_DIR/agents/code_agent/sandbox" ]; then
    log "Building sandbox image..."
    docker build -t code-sandbox-python "$SCRIPT_DIR/agents/code_agent/sandbox/" || warn "Sandbox build fehlgeschlagen (nicht kritisch)"
fi

# 4. Services starten
log "Starting services..."
docker compose -f "$COMPOSE_FILE" up -d voiceagent-core || error "Service-Start fehlgeschlagen"

# 5. Status anzeigen
echo ""
log "Update abgeschlossen!"
echo ""
docker compose -f "$COMPOSE_FILE" ps
echo ""
log "Logs anzeigen mit: docker compose -f $COMPOSE_FILE logs -f"
