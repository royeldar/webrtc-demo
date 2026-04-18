#!/bin/bash

PORT="${TURN_PORT:-3478}"
REALM="${TURN_REALM:-localhost}"
USERNAME="${TURN_USERNAME:-username}"
PASSWORD="${TURN_PASSWORD:-password}"

cleanup() {
    kill $TURN_PID $PY_PID
    exit 0
}

trap cleanup SIGINT SIGTERM

turnserver --listening-port "$PORT" --lt-cred-mech --realm "$REALM" --user "$USERNAME:$PASSWORD" &
TURN_PID=$!

python3 server.py &
PY_PID=$!

wait
