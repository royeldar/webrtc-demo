#!/bin/bash

: "${HTTP_PORT:=8080}"
: "${SSL_PASSWORD:=}"
: "${TURN_PORT:=3478}"
: "${TURN_TLS_PORT:=5349}"
: "${TURN_MIN_PORT:=50000}"
: "${TURN_MAX_PORT:=50001}"
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
python3 server.py --port "$HTTP_PORT" &
PY_PID=$!

turnserver \
    -n --no-cli \
    --listening-port "$TURN_PORT" \
    --tls-listening-port "$TURN_TLS_PORT" \
    --min-port "$TURN_MIN_PORT" \
    --max-port "$TURN_MAX_PORT" \
    --cert "$SSL_CERTFILE" \
    --pkey "$SSL_KEYFILE" \
    --pkey-pwd "$SSL_PASSWORD" \
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
