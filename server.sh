#!/bin/bash

: "${IP_ADDRESS:=localhost}"

: "${PY_PORT:=80}"

: "${TURN_PORT:=3478}"
: "${TURN_REALM:=localhost}"
: "${TURN_USERNAME:=username}"
: "${TURN_PASSWORD:=password}"
: "${TURN_EXTRA_FLAGS:=}"

cleanup() {
    kill $PY_PID $TURN_PID
    exit 0
}

trap cleanup SIGINT SIGTERM

python3 server.py --address "$IP_ADDRESS" --port "$PY_PORT" &
PY_PID=$!

turnserver \
    --listening-ip "$IP_ADDRESS" \
    --listening-port "$TURN_PORT" \
    --realm "$TURN_REALM" \
    --user "$TURN_USERNAME:$TURN_PASSWORD" \
    --lt-cred-mech \
    $TURN_EXTRA_FLAGS &
TURN_PID=$!

wait
