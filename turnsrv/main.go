package main

import (
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"strconv"
	"syscall"

	"github.com/pion/turn/v2"
)

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func mustAtoi(name, value string) int {
	n, err := strconv.Atoi(value)
	if err != nil {
		log.Fatalf("invalid %s=%q: %v", name, value, err)
	}
	return n
}

func resolveExternalIP(s string) net.IP {
	if ip := net.ParseIP(s); ip != nil {
		if v4 := ip.To4(); v4 != nil {
			return v4
		}
		return ip
	}
	ips, err := net.LookupIP(s)
	if err != nil || len(ips) == 0 {
		log.Fatalf("EXTERNAL_IP=%q is neither an IP nor a resolvable hostname: %v", s, err)
	}
	for _, ip := range ips {
		if v4 := ip.To4(); v4 != nil {
			return v4
		}
	}
	return ips[0]
}

func main() {
	realm := envOr("TURN_REALM", "localhost")
	username := envOr("TURN_USERNAME", "username")
	password := envOr("TURN_PASSWORD", "password")
	externalIP := resolveExternalIP(envOr("EXTERNAL_IP", "127.0.0.1"))
	listenPort := mustAtoi("LISTEN_PORT", envOr("LISTEN_PORT", "3478"))
	relayPort := mustAtoi("RELAY_PORT", envOr("RELAY_PORT", "50000"))

	udpListener, err := net.ListenPacket("udp4", fmt.Sprintf(":%d", listenPort))
	if err != nil {
		log.Fatalf("listen UDP :%d: %v", listenPort, err)
	}
	tcpListener, err := net.Listen("tcp4", fmt.Sprintf(":%d", listenPort))
	if err != nil {
		log.Fatalf("listen TCP :%d: %v", listenPort, err)
	}

	shared, err := NewSharedRelay(
		&net.UDPAddr{IP: net.IPv4zero, Port: relayPort},
		&net.UDPAddr{IP: externalIP, Port: relayPort},
	)
	if err != nil {
		log.Fatalf("shared relay :%d: %v", relayPort, err)
	}

	authKey := turn.GenerateAuthKey(username, realm, password)
	authHandler := func(u, r string, _ net.Addr) ([]byte, bool) {
		if u == username && r == realm {
			return authKey, true
		}
		return nil, false
	}

	relayGen := &SharedRelayAddressGenerator{Shared: shared}

	server, err := turn.NewServer(turn.ServerConfig{
		Realm:       realm,
		AuthHandler: authHandler,
		PacketConnConfigs: []turn.PacketConnConfig{
			{PacketConn: udpListener, RelayAddressGenerator: relayGen},
		},
		ListenerConfigs: []turn.ListenerConfig{
			{Listener: tcpListener, RelayAddressGenerator: relayGen},
		},
	})
	if err != nil {
		log.Fatalf("turn.NewServer: %v", err)
	}

	log.Printf("turnsrv ready: STUN/TURN UDP+TCP :%d, shared relay UDP :%d advertised as %s:%d",
		listenPort, relayPort, externalIP, relayPort)

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig
	log.Println("shutting down")
	if err := server.Close(); err != nil {
		log.Printf("server close: %v", err)
	}
}
