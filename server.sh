#!/bin/bash

: "${IP_ADDRESS:=localhost}"

: "${PY_PORT:=80}"

: "${TURN_PORT:=3478}"
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

python3 server.py --address "$IP_ADDRESS" --port "$PY_PORT" &
PY_PID=$!

turnserver \
    -n \
    --listening-ip "$IP_ADDRESS" \
    --listening-port "$TURN_PORT" \
    --realm "$TURN_REALM" \
    --user "$TURN_USERNAME:$TURN_PASSWORD" \
    --lt-cred-mech \
    --db "$TURN_DB" \
    --log-file "$TURN_LOGFILE" \
    --pidfile "$TURN_PIDFILE" \
    $TURN_EXTRA_FLAGS &
TURN_PID=$!

wait
