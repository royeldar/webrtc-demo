FROM debian:trixie-slim

RUN apt-get update && apt-get install -y \
    python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY static static/
COPY server.py server.sh turnsrv.py ./

RUN chmod +x server.sh turnsrv.py

EXPOSE 8080/tcp
EXPOSE 3478/tcp 3478/udp
EXPOSE 50000/udp

CMD ["./server.sh"]
