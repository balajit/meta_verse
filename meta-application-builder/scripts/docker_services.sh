#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker-compose.yml"

usage() {
    echo "Usage: $0 {start|stop|restart|status|logs|clean}"
    echo "  start   - Spin up containers in background and wait for healthchecks"
    echo "  stop    - Gracefully stop containers (preserves data volumes)"
    echo "  restart - Stop and start infrastructure"
    echo "  status  - Show container status and health"
    echo "  logs    - Tail container logs (e.g., '$0 logs redpanda')"
    echo "  clean   - Stop containers and remove volumes (WIPES DATABASE)"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

COMMAND="$1"

case "$COMMAND" in
    start)
        echo "Starting meta-application-builder infrastructure..."
        docker compose -f "$COMPOSE_FILE" up -d
        echo "Waiting for services to pass healthchecks..."

        # Poll container health
        #until [ "$(docker compose -f "$COMPOSE_FILE" ps --filter "health=healthy" -q | wc -l | tr -d ' ')" -ge 4 ]; do
        until [ "$(docker ps --filter "health=healthy" -q | wc -l | tr -d ' ')" -ge 4 ]; do
            printf "."
            sleep 2
        done
        echo ""
        echo "All core services are online and healthy."
        docker compose -f "$COMPOSE_FILE" ps
        ;;

    stop)
        echo "Stopping meta-application-builder services..."
        docker compose -f "$COMPOSE_FILE" stop
        echo "Services stopped cleanly."
        ;;

    restart)
        "$0" stop
        "$0" start
        ;;

    status)
        docker compose -f "$COMPOSE_FILE" ps
        ;;

    logs)
        SERVICE="${2:-}"
        docker compose -f "$COMPOSE_FILE" logs -f $SERVICE
        ;;

    clean)
        read -p "Warning: This will destroy all local data volumes (PostgreSQL, Redpanda). Proceed? [y/N] " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Tearing down containers and volume data..."
            docker compose -f "$COMPOSE_FILE" down -v
            echo "Cleanup complete."
        else
            echo "Aborted."
        fi
        ;;

    *)
        usage
        ;;
esac