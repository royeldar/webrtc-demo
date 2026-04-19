#!/bin/bash

: "${HTTPS_PORT:=8443}"
: "${SSL_PASSWORD:=}"
: "${TURN_PORT:=3478}"
: "${TURN_MIN_PORT:=49152}"
: "${TURN_MAX_PORT:=65535}"
: "${TURN_REALM:=localhost}"
: "${TURN_USERNAME:=username}"
: "${TURN_PASSWORD:=password}"
: "${TURN_EXTRA_FLAGS:=}"

SSL_CERTFILE="./cert.pem"
SSL_KEYFILE="./key.pem"
TURN_DB="./turnserver.db"
TURN_LOGFILE="./turnserver.log"
TURN_PIDFILE="./turnserver.pid"

cleanup() {
    kill $PY_PID $TURN_PID
    exit 0
}

trap cleanup SIGINT SIGTERM

export SSL_PASSWORD
python3 server.py --port "$HTTPS_PORT" --certfile "$SSL_CERTFILE" --keyfile "$SSL_KEYFILE" &
PY_PID=$!

turnserver \
    -n --no-cli \
    --listening-port "$TURN_PORT" \
    --min-port "$TURN_MIN_PORT" \
    --max-port "$TURN_MAX_PORT" \
    --realm "$TURN_REALM" \
    --user "$TURN_USERNAME:$TURN_PASSWORD" \
    --lt-cred-mech \
    --db "$TURN_DB" \
    --no-stdout-log \
    --simple-log \
    --log-file "$TURN_LOGFILE" \
    --pidfile "$TURN_PIDFILE" \
    $TURN_EXTRA_FLAGS &
TURN_PID=$!

wait
