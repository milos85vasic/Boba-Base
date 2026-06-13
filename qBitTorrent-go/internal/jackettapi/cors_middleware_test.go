package jackettapi

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// markerPostHandler is a stand-in inner handler that records that it was
// reached. CORS+OPTIONS must NOT reach it; the OPTIONS short-circuit
// is the critical CONST-XII assertion.
func markerPostHandler(reached *bool) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		*reached = true
		w.WriteHeader(http.StatusOK)
	})
}

func TestWithCORS_AllowedOriginGetsACAOHeader(t *testing.T) {
	var reached bool
	h := WithCORS(nil, markerPostHandler(&reached))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/x", nil)
	req.Header.Set("Origin", "http://localhost:4200")
	h.ServeHTTP(rec, req)
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "http://localhost:4200" {
		t.Fatalf("want ACAO=http://localhost:4200, got %q", got)
	}
	if got := rec.Header().Get("Vary"); !strings.Contains(got, "Origin") {
		t.Fatalf("want Vary contains Origin, got %q", got)
	}
	if !reached {
		t.Fatal("inner handler NOT reached on GET — CORS should not block")
	}
}

// Operator-reported (2026-06-13): the dashboard accessed via a LAN IP
// (http://192.168.0.132:7187) hit "0 Unknown Error" on the Jackett page because
// boba-jackett's CORS only allowed hardcoded localhost origins. The same-host
// rule allows any Origin co-hosted with this service (derives from the request
// Host), so the dashboard works from localhost, a LAN IP, or any hostname.
func TestWithCORS_SameHostDifferentPortAllowed(t *testing.T) {
	var reached bool
	h := WithCORS(nil, markerPostHandler(&reached))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/api/v1/jackett/credentials", nil)
	req.Host = "192.168.0.132:7189" // this service, reached via the LAN IP
	req.Header.Set("Origin", "http://192.168.0.132:7187")
	h.ServeHTTP(rec, req)
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "http://192.168.0.132:7187" {
		t.Fatalf("LAN-IP dashboard origin (same host) must be allowed, got %q", got)
	}
	if !reached {
		t.Fatal("inner handler NOT reached on same-host GET")
	}
}

// Anti-bluff polarity (§11.4.115): the same-host rule must NOT be over-permissive
// — an Origin on a DIFFERENT host is still blocked.
func TestWithCORS_DifferentHostStillBlocked(t *testing.T) {
	var reached bool
	h := WithCORS(nil, markerPostHandler(&reached))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/api/v1/jackett/credentials", nil)
	req.Host = "192.168.0.132:7189"
	req.Header.Set("Origin", "http://192.168.0.99:7187") // different host
	h.ServeHTTP(rec, req)
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Fatalf("a different-host origin must NOT get a CORS header, got %q", got)
	}
}

// SECURITY guard (DNS rebinding): the same-host rule must match ONLY IP-literal
// hosts. A DNS-rebinding attacker re-points a NAME (evil.example) at the
// victim's LAN IP, so the browser sends that NAME in both Origin and Host —
// which would match a naive name-equality check and leak the response. The
// IP-literal restriction blocks it. This test FAILS against a name-equality
// sameHost and PASSES against the IP-literal one (§11.4.115 polarity).
func TestWithCORS_DNSRebindingNameHostBlocked(t *testing.T) {
	var reached bool
	h := WithCORS(nil, markerPostHandler(&reached))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/api/v1/jackett/credentials", nil)
	req.Host = "attacker.example:7189"                  // DNS-rebound NAME → victim LAN IP
	req.Header.Set("Origin", "http://attacker.example") // same NAME as Host
	h.ServeHTTP(rec, req)
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Fatalf("DNS-rebinding (matching NAME host+origin) must NOT get a CORS header, got %q", got)
	}
}

// IPv6 literal same-host must work (net.SplitHostPort handles [::1]:port).
func TestWithCORS_SameHostIPv6LiteralAllowed(t *testing.T) {
	var reached bool
	h := WithCORS(nil, markerPostHandler(&reached))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/api/v1/jackett/credentials", nil)
	req.Host = "[fd00::1]:7189"
	req.Header.Set("Origin", "http://[fd00::1]:7187")
	h.ServeHTTP(rec, req)
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "http://[fd00::1]:7187" {
		t.Fatalf("IPv6 same-host literal must be allowed, got %q", got)
	}
}

func TestWithCORS_DisallowedOriginGetsNoCORSHeaders(t *testing.T) {
	var reached bool
	h := WithCORS(nil, markerPostHandler(&reached))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/x", nil)
	req.Header.Set("Origin", "http://evil.example")
	h.ServeHTTP(rec, req)
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Fatalf("disallowed origin should NOT echo ACAO; got %q", got)
	}
	// Inner handler IS reached (we don't block at the server) — the
	// browser will block based on missing ACAO. This matches the W3C
	// spec; CORS is browser-side enforcement.
	if !reached {
		t.Fatal("inner handler should still be reached even for disallowed origin")
	}
}

func TestWithCORS_OPTIONSPreflightShortCircuits(t *testing.T) {
	var reached bool
	h := WithCORS(nil, markerPostHandler(&reached))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodOptions, "/api/v1/jackett/credentials", nil)
	req.Header.Set("Origin", "http://localhost:4200")
	req.Header.Set("Access-Control-Request-Method", "POST")
	req.Header.Set("Access-Control-Request-Headers", "Authorization, Content-Type")
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("OPTIONS preflight: want 204, got %d", rec.Code)
	}
	if reached {
		t.Fatal("inner handler MUST NOT be reached for OPTIONS preflight (CONST-XII)")
	}
	allowMethods := rec.Header().Get("Access-Control-Allow-Methods")
	for _, m := range []string{"GET", "POST", "PATCH", "DELETE", "OPTIONS"} {
		if !strings.Contains(allowMethods, m) {
			t.Errorf("Allow-Methods missing %s: %q", m, allowMethods)
		}
	}
	allowHeaders := rec.Header().Get("Access-Control-Allow-Headers")
	for _, h := range []string{"Authorization", "Content-Type"} {
		if !strings.Contains(allowHeaders, h) {
			t.Errorf("Allow-Headers missing %s: %q", h, allowHeaders)
		}
	}
}

func TestWithCORS_CustomOriginsList(t *testing.T) {
	var reached bool
	h := WithCORS([]string{"https://prod.example"}, markerPostHandler(&reached))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/x", nil)
	req.Header.Set("Origin", "https://prod.example")
	h.ServeHTTP(rec, req)
	if rec.Header().Get("Access-Control-Allow-Origin") != "https://prod.example" {
		t.Fatalf("custom origin should be allowed; got %q", rec.Header().Get("Access-Control-Allow-Origin"))
	}
	// Default origins NOT applied when a custom list is passed:
	rec2 := httptest.NewRecorder()
	req2 := httptest.NewRequest("GET", "/x", nil)
	req2.Header.Set("Origin", "http://localhost:4200")
	h.ServeHTTP(rec2, req2)
	if rec2.Header().Get("Access-Control-Allow-Origin") != "" {
		t.Fatalf("default localhost:4200 should NOT be allowed when custom list given; got %q",
			rec2.Header().Get("Access-Control-Allow-Origin"))
	}
}

func TestWithCORS_WildcardAllowsAnyOrigin(t *testing.T) {
	var reached bool
	h := WithCORS([]string{"*"}, markerPostHandler(&reached))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/x", nil)
	req.Header.Set("Origin", "http://192.168.1.42:7187")
	h.ServeHTTP(rec, req)
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "http://192.168.1.42:7187" {
		t.Fatalf("wildcard: want ACAO echoed back, got %q", got)
	}
	if !reached {
		t.Fatal("inner handler NOT reached")
	}
}

func TestWithCORS_EnvVarOverridesDefaults(t *testing.T) {
	t.Setenv("ALLOWED_ORIGINS", "http://phone.local:7187")
	var reached bool
	h := WithCORS(nil, markerPostHandler(&reached))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/x", nil)
	req.Header.Set("Origin", "http://phone.local:7187")
	h.ServeHTTP(rec, req)
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "http://phone.local:7187" {
		t.Fatalf("env var origin: want ACAO=http://phone.local:7187, got %q", got)
	}
	// Default origin should no longer be allowed
	rec2 := httptest.NewRecorder()
	req2 := httptest.NewRequest("GET", "/x", nil)
	req2.Header.Set("Origin", "http://localhost:7187")
	h.ServeHTTP(rec2, req2)
	if rec2.Header().Get("Access-Control-Allow-Origin") != "" {
		t.Fatalf("default origin should NOT be allowed when env var overrides; got %q",
			rec2.Header().Get("Access-Control-Allow-Origin"))
	}
}

func TestAuthMiddleware_OPTIONSPassesWithoutAuth(t *testing.T) {
	// Anti-bluff regression for the auth middleware fix: OPTIONS
	// (browser CORS preflight) must pass through without auth.
	var reached bool
	h := WithAuth(markerPostHandler(&reached))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodOptions, "/api/v1/jackett/credentials", nil)
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("OPTIONS without auth: want 200 (passed through to inner), got %d", rec.Code)
	}
	if !reached {
		t.Fatal("inner handler NOT reached for OPTIONS — auth middleware should pass it through")
	}
}
