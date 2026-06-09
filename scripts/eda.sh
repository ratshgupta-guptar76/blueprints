#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/../.docker/docker-compose.yml"
if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Error: docker-compose file not found at $COMPOSE_FILE" >&2
  exit 1
fi
COMPOSE="docker compose -f $COMPOSE_FILE"

cmd="${1:-help}"
shift || true

case "$cmd" in
  start)
    $COMPOSE up -d
    echo "VNC: http://localhost:80  |  vnc://localhost:5901  (pw: abc123)"
    ;;
  stop)
    $COMPOSE down
    ;;
  restart)
    $COMPOSE restart
    ;;
  shell)
    docker exec -it blueprints-eda bash -lc "cd /foss/blueprints && exec bash"
    ;;
  run)
    # Run a command headlessly inside the container
    # Usage: ./eda.sh run "cd /foss/blueprints/digital && librelane config.json"
    # Default to running from the repository root inside the container so files
    # written by commands are placed under /foss/blueprints (the mounted repo).
    echo "Running inside container at /foss/blueprints: $*"
    docker exec blueprints-eda bash -lc "cd /foss/blueprints && echo Working dir: \$(pwd) && echo Command: '$*' && $*"
    ;;
  librelane)
    # Usage: ./eda.sh librelane digital/config.json
    echo "Running librelane with: $* (from /foss/blueprints)"
    docker exec -it blueprints-eda bash -lc "cd /foss/blueprints && echo Working dir: \$(pwd) && echo Command: librelane $* && librelane $*"
    ;;
  logs)
    $COMPOSE logs -f
    ;;
  status)
    $COMPOSE ps
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|shell|run|librelane|logs|status}"
    echo ""
    echo "  start              Start EDA container (VNC at localhost:80)"
    echo "  stop               Stop container"
    echo "  shell              Open bash inside container"
    echo "  run \"<cmd>\"        Run command headlessly"
    echo "  librelane <cfg>    Run LibreLane on a config file"
    echo "  logs               Tail container logs"
    echo "  status             Show container status"
    ;;
esac
