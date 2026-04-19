#!/bin/bash

: "${SSL_PASSWORD:=}"
: "${SSL_CN:=localhost}"

CERTFILE="./cert.pem"
KEYFILE="./key.pem"

if [ -z "$SSL_PASSWORD" ]; then
    AUTH="-nodes"
else
    AUTH="-passout env:SSL_PASSWORD"
fi

openssl req -x509 -newkey rsa:2048 -sha256 \
    -keyout "$KEYFILE" -out "$CERTFILE" $AUTH \
    -subj "/CN=$SSL_CN"
