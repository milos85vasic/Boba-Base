package jackettapi

import (
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
)

// B2 (§11.4.251) — the two Go CORS copies both read ALLOWED_ORIGINS, but they
// disagreed on HOW to parse it. That is the same defect one level down: a
// consistent variable name over inconsistent semantics.
//
// Two measured disagreements against the authoritative Python reference
// (download-proxy/src/api/__init__.py):
//
//  1. WILDCARD DETECTION. Python tests each element after splitting
//     ("*" in _allowed_origins), so "https://a.example,*" IS a wildcard.
//     internal/middleware/cors.go also tests per element. jackettapi tested the
//     WHOLE string (strings.TrimSpace(env) == "*"), so the same value produced
//     a NON-wildcard allowlist containing a literal "*" entry that can never
//     match a real Origin — the operator's wildcard silently did nothing.
//
//  2. EMPTY-AFTER-PARSE. Python falls back to its defaults when the value
//     parses to nothing (" ", " , ,"). jackettapi produced an EMPTY allowlist
//     instead, silently revoking every default origin.
//
// Both assert the real Access-Control-Allow-Origin RESPONSE HEADER.

func jackettACAO(t *testing.T, origin string) string {
	t.Helper()
	h := WithCORS(nil, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.Header.Set("Origin", origin)
	h.ServeHTTP(rec, req)
	return rec.Header().Get("Access-Control-Allow-Origin")
}

func unsetEnvForTest(t *testing.T, key string) {
	t.Helper()
	prev, had := os.LookupEnv(key)
	if err := os.Unsetenv(key); err != nil {
		t.Fatalf("unset %s: %v", key, err)
	}
	t.Cleanup(func() {
		if had {
			_ = os.Setenv(key, prev)
			return
		}
		_ = os.Unsetenv(key)
	})
}

func TestWithCORS_WildcardDetectedPerElement(t *testing.T) {
	// Python: "*" in ["https://a.example", "*"] -> wildcard.
	t.Setenv("ALLOWED_ORIGINS", "https://a.example,*")
	for _, origin := range []string{"https://a.example", "https://anything.example:8443"} {
		if got := jackettACAO(t, origin); got != origin {
			t.Errorf("ALLOWED_ORIGINS=%q is a wildcard (per-element, as Python): origin %q MUST be allowed;\n  want Access-Control-Allow-Origin=%q\n  got  %q",
				"https://a.example,*", origin, origin, got)
		}
	}
}

func TestWithCORS_EmptyAfterParseFallsBackToDefaults(t *testing.T) {
	for _, raw := range []string{"   ", " , ,", ",,"} {
		t.Run(raw, func(t *testing.T) {
			t.Setenv("MERGE_SERVICE_PORT", "7187")
			t.Setenv("ALLOWED_ORIGINS", raw)
			// Python parses these to [] and then falls back to _DEFAULT_ORIGINS.
			if got := jackettACAO(t, "http://localhost:4200"); got != "http://localhost:4200" {
				t.Errorf("ALLOWED_ORIGINS=%q parses to nothing and MUST fall back to the defaults, not an empty allowlist;\n  want Access-Control-Allow-Origin=%q\n  got  %q",
					raw, "http://localhost:4200", got)
			}
			if got := jackettACAO(t, "http://evil.example"); got != "" {
				t.Errorf("ALLOWED_ORIGINS=%q: %q MUST still be rejected; got %q", raw, "http://evil.example", got)
			}
		})
	}
}

func TestWithCORS_DefaultOriginsFollowMergeServicePort(t *testing.T) {
	// Parity with Python's _MERGE_PORT derivation, shared by both Go copies.
	t.Setenv("MERGE_SERVICE_PORT", "9187")
	unsetEnvForTest(t, "ALLOWED_ORIGINS")
	for _, origin := range []string{"http://localhost:9187", "http://127.0.0.1:9187"} {
		if got := jackettACAO(t, origin); got != origin {
			t.Errorf("MERGE_SERVICE_PORT=9187: %q MUST be a default origin;\n  want Access-Control-Allow-Origin=%q\n  got  %q",
				origin, origin, got)
		}
	}
	if got := jackettACAO(t, "http://localhost:7187"); got != "" {
		t.Errorf("MERGE_SERVICE_PORT=9187: stale default http://localhost:7187 MUST NOT be granted; got %q", got)
	}
}
