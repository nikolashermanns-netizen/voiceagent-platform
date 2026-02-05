#!/bin/bash
# VoiceAgent Platform - Deployment Script
# Verwendung: ./deploy.sh [build|start|stop|restart|logs|status]

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[Deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[Warn]${NC} $1"; }
error() { echo -e "${RED}[Error]${NC} $1"; }

case "${1:-help}" in
    build)
        log "Building images..."
        docker compose -f "$COMPOSE_FILE" build
        # Sandbox-Image separat bauen
        docker build -t code-sandbox-python "$PROJECT_DIR/agents/code_agent/sandbox/"
        log "Build complete."
        ;;

    start)
        log "Starting services..."
        docker compose -f "$COMPOSE_FILE" up -d voiceagent-core
        log "Services started."
        docker compose -f "$COMPOSE_FILE" logs -f --tail=50
        ;;

    stop)
        log "Stopping services..."
        docker compose -f "$COMPOSE_FILE" down
        log "Services stopped."
        ;;

    restart)
        log "Restarting services..."
        docker compose -f "$COMPOSE_FILE" down
        docker compose -f "$COMPOSE_FILE" up -d voiceagent-core
        log "Services restarted."
        docker compose -f "$COMPOSE_FILE" logs -f --tail=20
        ;;

    logs)
        docker compose -f "$COMPOSE_FILE" logs -f --tail=100
        ;;

    status)
        docker compose -f "$COMPOSE_FILE" ps
        echo ""
        log "Container Status:"
        docker ps --filter "name=voiceagent" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        ;;

    pull)
        log "Pulling latest code..."
        cd "$PROJECT_DIR"
        git pull
        log "Rebuilding and restarting..."
        docker compose -f "$COMPOSE_FILE" build
        docker compose -f "$COMPOSE_FILE" down
        docker compose -f "$COMPOSE_FILE" up -d voiceagent-core
        log "Deploy complete."
        docker compose -f "$COMPOSE_FILE" logs -f --tail=20
        ;;

    *)
        echo "VoiceAgent Platform - Deployment"
        echo ""
        echo "Usage: $0 {build|start|stop|restart|logs|status|pull}"
        echo ""
        echo "  build    - Build Docker images"
        echo "  start    - Start services"
        echo "  stop     - Stop services"
        echo "  restart  - Restart services"
        echo "  logs     - Show logs (live)"
        echo "  status   - Show service status"
        echo "  pull     - Pull git + rebuild + restart"
        ;;
esac
