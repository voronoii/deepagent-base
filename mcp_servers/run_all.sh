#!/usr/bin/env bash
# MCP 서버 일괄 실행 (로컬 개발용)
# 사용법: ./mcp_servers/run_all.sh [start|stop]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"

# ── 서버 목록: "디렉토리명 포트" ──
SERVERS=(
    "news 1879"
    "apt-metadata 1880"
    "apt-review 1881"
    "apt-develop 1882"
    "hug-rag 1883"
    # 새 MCP 서버 추가 시 여기에 한 줄 추가
)

start_servers() {
    mkdir -p "$PID_DIR"
    mkdir -p "$SCRIPT_DIR/logs"
    echo "Starting MCP servers..."

    for entry in "${SERVERS[@]}"; do
        read -r name port <<< "$entry"
        server_dir="$SCRIPT_DIR/$name"

        if [ ! -f "$server_dir/server.py" ]; then
            echo "  [SKIP] $name - server.py not found"
            continue
        fi

        if [ -f "$PID_DIR/$name.pid" ] && kill -0 "$(cat "$PID_DIR/$name.pid")" 2>/dev/null; then
            echo "  [SKIP] $name - already running (PID $(cat "$PID_DIR/$name.pid"))"
            continue
        fi

        log_file="$SCRIPT_DIR/logs/$name.log"
        nohup env MCP_PORT=$port MCP_TRANSPORT=streamable-http \
            python "$server_dir/server.py" \
            >> "$log_file" 2>&1 &
        echo $! > "$PID_DIR/$name.pid"
        disown
        echo "  [OK]   $name → http://localhost:$port/mcp/ (PID $!, log: logs/$name.log)"
    done

    echo "Done. PID files in $PID_DIR/"
}

stop_servers() {
    echo "Stopping MCP servers..."

    if [ ! -d "$PID_DIR" ]; then
        echo "  No running servers found."
        return
    fi

    for entry in "${SERVERS[@]}"; do
        read -r name port <<< "$entry"
        pid_file="$PID_DIR/$name.pid"

        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid"
                echo "  [STOP] $name (PID $pid)"
            else
                echo "  [SKIP] $name - not running"
            fi
            rm -f "$pid_file"
        fi
    done
}

case "${1:-start}" in
    start) start_servers ;;
    stop)  stop_servers ;;
    *)     echo "Usage: $0 [start|stop]" ;;
esac
