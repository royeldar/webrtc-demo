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

python3 turnsrv.py \
    --listen-port "$TURN_PORT" \
    --relay-port "$RELAY_PORT" \
    --external-ip "$EXTERNAL_IP" \
    --realm "$TURN_REALM" \
    --username "$TURN_USERNAME" \
    --password "$TURN_PASSWORD" &
TURN_PID=$!

wait
