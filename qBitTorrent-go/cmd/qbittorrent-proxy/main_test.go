// BOB-198 boot-time loopback guard.
//
// qbittorrent-proxy-go registers CORS, Logger and rate-limit middleware but
// NO authentication (see main.go) — 22 LAN-bound routes are open, several
// mutating (POST /api/v1/download, POST /api/v1/magnet, DELETE
// /api/v1/hooks/:id, POST and DELETE /api/v1/schedules). The server bound
// addr := fmt.Sprintf(":%d", cfg.ServerPort) — a bare ":port" Go listen
// string, which binds ALL interfaces — unconditionally, with nothing
// checking whether that bind was safe before r.Run(addr) started serving.
//
// OPERATOR DECISION (2026-08-26, §11.4.66): "REFUSE TO START LAN-BOUND".
// This profile does NOT get auth middleware this cycle — that alternative
// was explicitly considered and REJECTED, as was documenting "dev-only"
// with no enforcing mechanism. It gets a boot-time guard instead: bind
// loopback only, or refuse to start.
//
// RED EVIDENCE (pre-fix, captured 2026-09-22): before this file's guard
// existed, there was no `checkLoopbackBind` function anywhere in this
// package — `go test ./cmd/qbittorrent-proxy/... -run TestGuard -v` failed
// at COMPILE time with "undefined: checkLoopbackBind", because main()
// passed cfg.ServerPort straight into fmt.Sprintf(":%d", ...) and then
// r.Run(addr) with no boot-time check of any kind — a non-loopback bind
// (the exact "0.0.0.0" class this bug report names) was never refused; it
// was simply served. That compile failure IS the reproduction: the gap is
// "no guard exists", so a test asserting the guard's behavior cannot even
// build against the pre-fix source. The guard below (and its wiring into
// main()) is what turns that undefined symbol into a real, callable check.
package main

import (
	"strings"
	"testing"
)

// TestGuard_RefusesNonLoopbackBind is the BOB-198 mutation-style proof: a
// listener configured to bind on anything other than loopback — including
// the empty-string / ":port" all-interfaces shorthand Go's net package
// treats as 0.0.0.0-equivalent — MUST be refused before the server ever
// starts listening, because this binary ships no authentication middleware.
func TestGuard_RefusesNonLoopbackBind(t *testing.T) {
	cases := []struct {
		name string
		host string
	}{
		{"explicit all-interfaces literal", "0.0.0.0"},
		{"empty host (Go's :port all-interfaces shorthand)", ""},
		{"specific LAN IP", "192.168.1.5"},
		{"another specific non-loopback IP", "10.0.0.7"},
		{"unresolvable / arbitrary hostname (fail-closed, no DNS trust)", "qbittorrent"},
		{"IPv6 non-loopback literal", "2001:db8::1"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := checkLoopbackBind(tc.host)
			if err == nil {
				t.Fatalf("checkLoopbackBind(%q) = nil, want a refusal error — "+
					"this binary ships no auth middleware and MUST NOT bind non-loopback (BOB-198)", tc.host)
			}
			if !strings.Contains(strings.ToLower(err.Error()), "loopback") {
				t.Fatalf("checkLoopbackBind(%q) error = %q, want it to name the loopback requirement", tc.host, err.Error())
			}
		})
	}
}

// TestGuard_AllowsGenuineLoopbackBind is the §11.4.201(1) golden-FALSE half
// of the same guard: one that refuses EVERY bind — including a legitimate
// loopback dev setup — is exactly as broken as one that refuses nothing. A
// real loopback bind MUST start cleanly, never be false-positive-refused.
func TestGuard_AllowsGenuineLoopbackBind(t *testing.T) {
	cases := []struct {
		name string
		host string
	}{
		{"IPv4 loopback literal", "127.0.0.1"},
		{"localhost, lowercase", "localhost"},
		{"localhost, mixed case (case-insensitive)", "LocalHost"},
		{"IPv6 loopback literal", "::1"},
		{"any 127.0.0.0/8 literal, not just .1", "127.0.0.53"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := checkLoopbackBind(tc.host); err != nil {
				t.Fatalf("checkLoopbackBind(%q) = %v, want nil — a genuine loopback bind must NOT be refused", tc.host, err)
			}
		})
	}
}
