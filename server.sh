#!/bin/bash

: "${PY_PORT:=8080}"

: "${TURN_PORT:=3478}"
: "${TURN_MIN_PORT:=49152}"
: "${TURN_MAX_PORT:=65535}"
: "${TURN_REALM:=localhost}"
: "${TURN_USERNAME:=username}"
: "${TURN_PASSWORD:=password}"
: "${TURN_EXTRA_FLAGS:=}"

TURN_DB="./turnserver.db"
TURN_LOGFILE="./turnserver.log"
TURN_PIDFILE="./turnserver.pid"

cleanup() {
    kill $PY_PID $TURN_PID
    exit 0
}

trap cleanup SIGINT SIGTERM

python3 server.py --port "$PY_PORT" &
PY_PID=$!

turnserver \
    -n \
    --listening-port "$TURN_PORT" \
    --min-port "$TURN_MIN_PORT" \
    --max-port "$TURN_MAX_PORT" \
    --realm "$TURN_REALM" \
    --user "$TURN_USERNAME:$TURN_PASSWORD" \
    --lt-cred-mech \
    --db "$TURN_DB" \
    --log-file "$TURN_LOGFILE" \
    --pidfile "$TURN_PIDFILE" \
    $TURN_EXTRA_FLAGS &
TURN_PID=$!

wait
