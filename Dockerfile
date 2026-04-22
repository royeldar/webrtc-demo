FROM debian:trixie-slim

RUN apt-get update && apt-get install -y \
    python3 \
    coturn \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY static static/
COPY server.py server.sh .

RUN chmod +x server.sh

EXPOSE 8443
EXPOSE 3478/tcp 3478/udp
EXPOSE 5349/tcp 5349/udp
EXPOSE 50000-50100/tcp 50000-50100/udp

CMD ["./server.sh"]
