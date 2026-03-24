#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
PID_FILE="/tmp/gphub.pids"
BACKEND_PORT=8000
FRONTEND_PORT=3000

# ── helpers ───────────────────────────────────────────────────────────────────

kill_port() {
    local port=$1
    local pids
    pids=$(lsof -ti :"$port" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null
        echo "  Killed process(es) on port $port"
    fi
}

wait_for_port() {
    local port=$1
    local label=$2
    local max=15
    local i=0
    while ! lsof -ti :"$port" &>/dev/null; do
        sleep 1
        i=$((i + 1))
        if [ $i -ge $max ]; then
            echo "  ⚠ $label did not start on port $port within ${max}s"
            return 1
        fi
    done
    echo "  ✓ $label ready on port $port"
}

# ── commands ──────────────────────────────────────────────────────────────────

start() {
    echo "Starting GPhub..."

    # Ensure ports are free before starting
    kill_port $BACKEND_PORT
    kill_port $FRONTEND_PORT
    sleep 0.5

    # Restore database from compressed backup if not exists
    if [ -f "$BACKEND_DIR/ai_digest.db.gz" ] && [ ! -f "$BACKEND_DIR/ai_digest.db" ]; then
        echo "  Restoring database from backup..."
        gunzip -k "$BACKEND_DIR/ai_digest.db.gz"
        echo "  ✓ Database restored"
    fi

    # Start backend
    cd "$BACKEND_DIR" || exit 1
    if [ -d ".venv" ]; then
        .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload > /tmp/gphub-backend.log 2>&1 &
    else
        uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload > /tmp/gphub-backend.log 2>&1 &
    fi
    BACKEND_PID=$!

    # Start frontend
    cd "$FRONTEND_DIR" || exit 1
    PORT=$FRONTEND_PORT npm run dev > /tmp/gphub-frontend.log 2>&1 &
    FRONTEND_PID=$!

    echo "$BACKEND_PID $FRONTEND_PID" > "$PID_FILE"

    wait_for_port $BACKEND_PORT  "Backend"
    wait_for_port $FRONTEND_PORT "Frontend"

    echo ""
    echo "  Frontend → http://localhost:$FRONTEND_PORT"
    echo "  Backend  → http://localhost:$BACKEND_PORT"
    echo "  Logs     → /tmp/gphub-{backend,frontend}.log"
}

stop() {
    echo "Stopping GPhub..."

    # Kill by saved PIDs (and their children)
    if [ -f "$PID_FILE" ]; then
        while read -r pid; do
            if kill -0 "$pid" 2>/dev/null; then
                kill -TERM "$pid" 2>/dev/null
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi

    # Also kill by port — catches orphan processes
    kill_port $BACKEND_PORT
    kill_port $FRONTEND_PORT

    # Belt-and-suspenders: kill by process name
    pkill -f "uvicorn app.main:app" 2>/dev/null
    pkill -f "next dev" 2>/dev/null
    pkill -f "next-server" 2>/dev/null

    sleep 0.5
    echo "  All processes stopped"
}

status() {
    echo "GPhub status:"
    for port in $BACKEND_PORT $FRONTEND_PORT; do
        local label
        [ "$port" = "$BACKEND_PORT" ] && label="Backend " || label="Frontend"
        if lsof -ti :"$port" &>/dev/null; then
            local pid
            pid=$(lsof -ti :"$port")
            echo "  $label (port $port) → running [PID $pid]"
        else
            echo "  $label (port $port) → stopped"
        fi
    done
}

logs() {
    local svc="${2:-both}"
    case "$svc" in
        backend)  tail -f /tmp/gphub-backend.log ;;
        frontend) tail -f /tmp/gphub-frontend.log ;;
        *)        tail -f /tmp/gphub-backend.log /tmp/gphub-frontend.log ;;
    esac
}

# ── dispatch ──────────────────────────────────────────────────────────────────

case "$1" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; sleep 1; start ;;
    status)  status ;;
    logs)    logs "$@" ;;
    help|"")
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  start            Start frontend & backend"
        echo "  stop             Stop all services (by port + PID)"
        echo "  restart          Stop then start"
        echo "  status           Show running status"
        echo "  logs [backend|frontend]  Tail logs (default: both)"
        echo "  help             Show this message"
        echo ""
        echo "Ports:  frontend=$FRONTEND_PORT  backend=$BACKEND_PORT"
        ;;
    *) echo "Unknown command: $1. Run '$0 help' for usage." ;;
esac
