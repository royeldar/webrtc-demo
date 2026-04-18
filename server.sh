#!/bin/bash

: "${TURN_PORT:=3478}"
: "${TURN_REALM:=localhost}"
: "${TURN_USERNAME:=username}"
: "${TURN_PASSWORD:=password}"
: "${TURN_EXTRA_FLAGS:=}"

cleanup() {
    kill $TURN_PID $PY_PID
    exit 0
}

trap cleanup SIGINT SIGTERM

turnserver \
    --listening-port "$TURN_PORT" \
    --realm "$TURN_REALM" \
    --user "$TURN_USERNAME:$TURN_PASSWORD" \
    --lt-cred-mech \
    $TURN_EXTRA_FLAGS &
TURN_PID=$!

python3 server.py &
PY_PID=$!

wait
