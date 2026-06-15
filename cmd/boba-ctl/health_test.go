package main

import (
	"context"
	"net"
	"strings"
	"testing"
	"time"
)

// TestHealthDetail_HostNetService_ProbesKnownPort is the §11.4.115 RED-baseline
// regression guard for the "no ports exposed" host-net bug: every Boba service
// uses network_mode: host, so ServiceStatus.Ports is empty and the old loop
// emitted the misleading "no ports exposed" for a service that IS serving.
//
// RED (against pre-fix code): healthDetail did not exist OR returned
// "no ports exposed" for a host-net service with a known listening port.
// GREEN: healthDetail derives the real port from hostNetServicePorts and emits
// a genuine probe result, never the misleading "no ports exposed".
func TestHealthDetail_HostNetService_ProbesKnownPort(t *testing.T) {
	// Start a real listener on an ephemeral port to act as the service endpoint.
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()
	_, portStr, _ := net.SplitHostPort(ln.Addr().String())

	// Service with NO published ports (host-net) but a known listening port.
	s := serviceStatusLite{Name: "qbittorrent", State: "running", Health: "", Ports: nil}
	knownPorts := map[string]string{"qbittorrent": portStr}

	dialer := net.Dialer{Timeout: 2 * time.Second}
	ok, detail := healthDetail(context.Background(), dialer, s, knownPorts)

	if strings.Contains(detail, "no ports exposed") {
		t.Fatalf("host-net service with a serving endpoint must NOT report the misleading "+
			"'no ports exposed'; got detail=%q", detail)
	}
	if !ok {
		t.Fatalf("expected OK for a reachable host-net endpoint; got detail=%q", detail)
	}
	wantAddr := "127.0.0.1:" + portStr
	if !strings.Contains(detail, wantAddr) || !strings.Contains(detail, "reachable") {
		t.Fatalf("expected detail to cite the probed endpoint %q as reachable; got %q", wantAddr, detail)
	}
}

// TestHealthDetail_HostNetService_UnreachableKnownPort verifies a host-net
// service whose known port is NOT reachable OVER THE HOST LOOPBACK is NOT
// reported as FAIL — because on a remote-VM runtime (macOS podman) the host can
// only reach host-net ports that are tunnel-forwarded, so an unreachable result
// does not confirm the service is down (§11.4.1: no false-FAIL; §11.4.6: do not
// claim "down" when the host genuinely cannot tell). It must cite the endpoint
// with an honest "not a confirmed failure" detail, never "no ports exposed".
func TestHealthDetail_HostNetService_UnreachableKnownPort(t *testing.T) {
	// Bind+close to obtain a port that is now free (nothing listening).
	ln, _ := net.Listen("tcp", "127.0.0.1:0")
	_, portStr, _ := net.SplitHostPort(ln.Addr().String())
	ln.Close()

	s := serviceStatusLite{Name: "jackett", State: "running", Health: "", Ports: nil}
	knownPorts := map[string]string{"jackett": portStr}

	dialer := net.Dialer{Timeout: 500 * time.Millisecond}
	ok, detail := healthDetail(context.Background(), dialer, s, knownPorts)

	if !ok {
		t.Fatalf("a host-net port unreachable over the host loopback must NOT be a FAIL (VM boundary, not a confirmed failure); got detail=%q", detail)
	}
	if !strings.Contains(detail, "not a confirmed failure") {
		t.Fatalf("expected an honest 'not a confirmed failure' detail for an unreachable host-net port; got %q", detail)
	}
	if strings.Contains(detail, "no ports exposed") {
		t.Fatalf("must not report 'no ports exposed' for a service with a known port; got %q", detail)
	}
	if !strings.Contains(detail, "127.0.0.1:"+portStr) {
		t.Fatalf("expected detail to cite the probed endpoint; got %q", detail)
	}
}

// TestHealthDetail_PublishedPort_UnreachableIsAuthoritativeFail verifies that an
// unreachable PUBLISHED port (non-host-net) IS still an authoritative FAIL —
// the host->container mapping means unreachable genuinely equals down.
func TestHealthDetail_PublishedPort_UnreachableIsAuthoritativeFail(t *testing.T) {
	ln, _ := net.Listen("tcp", "127.0.0.1:0")
	_, portStr, _ := net.SplitHostPort(ln.Addr().String())
	ln.Close()

	s := serviceStatusLite{Name: "svc", State: "running", Health: "", Ports: []string{"127.0.0.1:" + portStr + "->8080/tcp"}}

	dialer := net.Dialer{Timeout: 500 * time.Millisecond}
	ok, detail := healthDetail(context.Background(), dialer, s, map[string]string{})

	if ok {
		t.Fatalf("an unreachable PUBLISHED port must be an authoritative FAIL; got detail=%q", detail)
	}
	if !strings.Contains(detail, "127.0.0.1:"+portStr) {
		t.Fatalf("expected detail to cite the probed endpoint; got %q", detail)
	}
}

// TestHealthDetail_HostNetService_UnknownPort verifies a host-net service with
// neither published ports nor a known port reports the honest host-net detail,
// never the misleading "no ports exposed".
func TestHealthDetail_HostNetService_UnknownPort(t *testing.T) {
	s := serviceStatusLite{Name: "mystery-svc", State: "running", Health: "", Ports: nil}
	dialer := net.Dialer{Timeout: 500 * time.Millisecond}
	ok, detail := healthDetail(context.Background(), dialer, s, map[string]string{})

	if strings.Contains(detail, "no ports exposed") {
		t.Fatalf("must not emit the misleading 'no ports exposed'; got %q", detail)
	}
	if !ok {
		t.Fatalf("an unprobeable running service should report OK (running) honestly; got %q", detail)
	}
	if !strings.Contains(detail, "host-net") || !strings.Contains(detail, "not probed") {
		t.Fatalf("expected an honest 'host-net, endpoint not probed' detail; got %q", detail)
	}
}

// TestHealthDetail_PublishedPort_PreservesExistingBehavior guards the
// non-host-net path: a service WITH a published port mapping is probed exactly
// as before, and the known-port map is not consulted.
func TestHealthDetail_PublishedPort_PreservesExistingBehavior(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()
	_, portStr, _ := net.SplitHostPort(ln.Addr().String())

	// Published-port mapping form "0.0.0.0:PORT->PORT/tcp".
	mapping := "0.0.0.0:" + portStr + "->" + portStr + "/tcp"
	s := serviceStatusLite{Name: "published-svc", State: "running", Health: "", Ports: []string{mapping}}

	dialer := net.Dialer{Timeout: 2 * time.Second}
	ok, detail := healthDetail(context.Background(), dialer, s, map[string]string{})

	if !ok {
		t.Fatalf("expected OK for reachable published port; got %q", detail)
	}
	if !strings.Contains(detail, "127.0.0.1:"+portStr) || !strings.Contains(detail, "reachable") {
		t.Fatalf("expected published-port probe detail; got %q", detail)
	}
}

// TestHostNetServicePorts_CoversAllBobaServices guards the compose→port map
// against drift: every host-net Boba service must have a known listening port
// so health never falls back to the honest-but-uninformative host-net detail.
func TestHostNetServicePorts_CoversAllBobaServices(t *testing.T) {
	want := map[string]string{
		"qbittorrent":          "7185",
		"jackett":              "9117",
		"qbittorrent-proxy-go": "7187",
		"download-proxy":       "7186",
		"boba-jackett":         "7189",
	}
	for svc, port := range want {
		got, ok := hostNetServicePorts[svc]
		if !ok {
			t.Errorf("hostNetServicePorts missing entry for host-net service %q", svc)
			continue
		}
		if got != port {
			t.Errorf("hostNetServicePorts[%q] = %q, want %q", svc, got, port)
		}
	}
}
