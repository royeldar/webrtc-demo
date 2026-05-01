FROM golang:1.22-alpine AS turnbuild
WORKDIR /src
COPY turnsrv/go.mod turnsrv/go.sum ./
RUN go mod download
COPY turnsrv/ ./
RUN CGO_ENABLED=0 go build -o /out/turnsrv .

FROM debian:trixie-slim

RUN apt-get update && apt-get install -y \
    python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY static static/
COPY server.py server.sh ./
COPY --from=turnbuild /out/turnsrv ./turnsrv

RUN chmod +x server.sh turnsrv

EXPOSE 8080/tcp
EXPOSE 3478/tcp 3478/udp
EXPOSE 50000/udp

CMD ["./server.sh"]
