// BOB-111 §11.4.196(F) guard: boba-jackett's :7189 surface is rate limited
// BECAUSE THE BINARY WIRES THE LIMITER, not merely because a limiter exists.
//
// WHY THIS FILE IS NOT A DUPLICATE of internal/middleware/ratelimit_test.go.
// Those tests drive WithRateLimit against a stub handler and prove the token
// bucket works. They pass identically whether or not THIS binary wraps its
// mux — delete the wrap from the http.Server literal and every one of them
// stays GREEN while :7189 serves an unbounded surface. This file closes that
// gap by driving newServerHandler, the exact chain main() installs.
//
// EVIDENCE CLASS (§11.4.226): RUNTIME-OVER-A-REAL-SOCKET. httptest.NewServer
// binds a real TCP listener and the requests are real HTTP round-trips through
// the real handler chain. The only thing stubbed is the Deps payload — the
// probe path is deliberately one the mux 404s, so no handler body is entered
// and no DB or Jackett instance is required. That is the point: the limiter
// sits IN FRONT of the mux, so it must refuse a 404 flood too. An attacker
// does not politely restrict themselves to routes that exist.
package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/milos85vasic/qBitTorrent-go/internal/jackettapi"
	"github.com/milos85vasic/qBitTorrent-go/internal/middleware"
)

// stubDeps is the minimum NewMux can be constructed from: /healthz is
// registered as a method value (d.Health.HandleHealth), so Health must be
// non-nil at CONSTRUCTION time. Every other route is a closure and is never
// entered by this file's probes.
func stubDeps() *jackettapi.Deps {
	return &jackettapi.Deps{Health: &jackettapi.HealthDeps{}}
}

// probePath is deliberately a route the mux does not serve. It proves the
// limiter runs BEFORE dispatch and needs no live DB or Jackett.
const probePath = "/definitely-not-a-route"

func burst(t *testing.T, url string, n int) (codes []int, bodies []string) {
	t.Helper()
	for i := 0; i < n; i++ {
		resp, err := http.Get(url) //nolint:gosec,noctx // fixed httptest loopback URL
		if err != nil {
			t.Fatalf("request %d: %v", i+1, err)
		}
		b, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		codes = append(codes, resp.StatusCode)
		bodies = append(bodies, string(b))
	}
	return codes, bodies
}

// TestWiring_ServerHandlerRateLimitsTheRealMux is the §11.4.196(F) assertion.
func TestWiring_ServerHandlerRateLimitsTheRealMux(t *testing.T) {
	// rpm=6/burst=3 keeps the case at milliseconds while still exercising the
	// real token bucket rather than a special-cased path.
	h := newServerHandler(middleware.NewRateLimiter(6, 3), stubDeps())
	srv := httptest.NewServer(h)
	defer srv.Close()

	codes, bodies := burst(t, srv.URL+probePath, 12)

	saw429 := false
	var body429 string
	for i, c := range codes {
		if c == http.StatusTooManyRequests {
			saw429 = true
			body429 = bodies[i]
			break
		}
	}
	if !saw429 {
		t.Fatalf("boba-jackett's server handler accepted an unbounded burst: %v — "+
			"the rate limiter is NOT wired into the chain main() installs", codes)
	}

	// §11.4.10: the refusal body is an opaque token, never bucket internals
	// and never the caller's address.
	if strings.TrimSpace(body429) != `{"error":"rate_limited"}` {
		t.Fatalf("429 body = %q, want the minimal opaque token", body429)
	}
	if strings.Contains(body429, "127.0.0.1") {
		t.Fatalf("429 body leaked the client address: %q", body429)
	}
}

// TestControl_UnderBudgetIsNotRefused is the §11.4.201(1) other direction: a
// limiter that refuses everything is exactly as broken as one that refuses
// nothing, and on :7189 blanket refusal would take the Jackett management UI
// down AND fail the container healthcheck.
func TestControl_UnderBudgetIsNotRefused(t *testing.T) {
	h := newServerHandler(middleware.NewRateLimiter(600, 50), stubDeps())
	srv := httptest.NewServer(h)
	defer srv.Close()

	codes, _ := burst(t, srv.URL+probePath, 20)
	for i, c := range codes {
		if c == http.StatusTooManyRequests {
			t.Fatalf("request %d refused at 600rpm/burst50 — the limiter is "+
				"refusing traffic well under its budget: %v", i+1, codes)
		}
	}
}

// TestControl_DisabledLimiterStillServes proves the RATE_LIMIT_DISABLED escape
// leaves a working handler chain rather than a nil Handler.
func TestControl_DisabledLimiterStillServes(t *testing.T) {
	h := newServerHandler(middleware.NewRateLimiter(0, 0), stubDeps()) // rpm<=0 == disabled
	srv := httptest.NewServer(h)
	defer srv.Close()

	codes, _ := burst(t, srv.URL+probePath, 30)
	for _, c := range codes {
		if c == http.StatusTooManyRequests {
			t.Fatalf("429 appeared with the limiter disabled: %v", codes)
		}
	}
}
