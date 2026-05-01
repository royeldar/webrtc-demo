#!/bin/bash

: "${HTTP_PORT:=8080}"
: "${TURN_PORT:=3478}"
: "${RELAY_PORT:=50000}"
: "${TURN_REALM:=localhost}"
: "${TURN_USERNAME:=username}"
: "${TURN_PASSWORD:=password}"
: "${EXTERNAL_IP:=127.0.0.1}"

cleanup() {
    kill $PY_PID $TURN_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

python3 server.py --port "$HTTP_PORT" &
PY_PID=$!

LISTEN_PORT="$TURN_PORT" RELAY_PORT="$RELAY_PORT" \
EXTERNAL_IP="$EXTERNAL_IP" \
TURN_REALM="$TURN_REALM" TURN_USERNAME="$TURN_USERNAME" TURN_PASSWORD="$TURN_PASSWORD" \
    ./turnsrv &
TURN_PID=$!

wait
