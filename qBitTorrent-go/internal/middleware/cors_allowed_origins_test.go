package middleware

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/config"
)

// B2 — ALLOWED_ORIGINS parity with the authoritative Python merge service.
//
// The Python reference is download-proxy/src/api/__init__.py
// (_MERGE_PORT / _DEFAULT_ORIGINS / _parse_allowed_origins). Its contract was
// MEASURED, not read, by exec'ing the real function over its own source:
//
//	unset (None)        -> defaults
//	""                  -> defaults   (NOT an empty allowlist)
//	" "                 -> defaults
//	" , ,"              -> defaults
//	"a"                 -> ["a"]
//	"a, b ,c"           -> ["a","b","c"]      (comma-separated, each stripped)
//	"*"                 -> ["*"]              (wildcard)
//	"a,*"               -> ["a","*"]          (wildcard — detected PER ELEMENT)
//
// and defaults derive the port from MERGE_SERVICE_PORT:
//
//	http://localhost:4200, http://127.0.0.1:4200,
//	http://localhost:$MERGE_SERVICE_PORT, http://127.0.0.1:$MERGE_SERVICE_PORT
//
// These tests assert the ACTUAL Access-Control-Allow-Origin RESPONSE HEADER
// (never merely "the middleware ran"), driving the SAME expression production
// uses in cmd/qbittorrent-proxy/main.go:
//
//	middleware.CORS(<split of cfg.AllowedOrigins>...)
//
// so a regression anywhere in config -> split -> middleware is caught.

// productionCORS builds the middleware exactly as cmd/qbittorrent-proxy/main.go
// does, from a freshly loaded config, so the env var travels the real chain.
func productionCORS(t *testing.T) gin.HandlerFunc {
	t.Helper()
	cfg := config.Load()
	return CORS(splitAllowedOrigins(cfg.AllowedOrigins)...)
}

// acao drives one request through the middleware and returns the
// Access-Control-Allow-Origin response header verbatim ("" when absent).
func acao(t *testing.T, h gin.HandlerFunc, origin string) string {
	t.Helper()
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(h)
	r.GET("/x", func(c *gin.Context) { c.String(http.StatusOK, "ok") })
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.Header.Set("Origin", origin)
	r.ServeHTTP(rec, req)
	return rec.Header().Get("Access-Control-Allow-Origin")
}

func TestCORS_AllowedOriginsEnv_PythonParity(t *testing.T) {
	const (
		set   = true
		unset = false
	)
	cases := []struct {
		name    string
		envSet  bool
		env     string
		allowed []string // MUST be echoed back in Access-Control-Allow-Origin
		denied  []string // MUST get no Access-Control-Allow-Origin at all
	}{
		{
			name:   "unset falls back to the Python default allowlist",
			envSet: unset,
			allowed: []string{
				"http://localhost:4200",
				"http://127.0.0.1:4200",
				"http://localhost:7187",
				"http://127.0.0.1:7187",
			},
			denied: []string{"http://evil.example", "https://attacker.test:7187"},
		},
		{
			name:   "empty string falls back to defaults, never an empty allowlist",
			envSet: set,
			env:    "",
			allowed: []string{
				"http://localhost:4200",
				"http://127.0.0.1:4200",
				"http://localhost:7187",
				"http://127.0.0.1:7187",
			},
			denied: []string{"http://evil.example"},
		},
		{
			name:   "whitespace-only falls back to defaults",
			envSet: set,
			env:    "   ",
			allowed: []string{
				"http://localhost:4200",
				"http://127.0.0.1:7187",
			},
			denied: []string{"http://evil.example"},
		},
		{
			name:   "commas-only falls back to defaults",
			envSet: set,
			env:    " , ,",
			allowed: []string{
				"http://localhost:4200",
				"http://127.0.0.1:7187",
			},
			denied: []string{"http://evil.example"},
		},
		{
			name:    "single origin replaces the defaults entirely",
			envSet:  set,
			env:     "https://dash.example",
			allowed: []string{"https://dash.example"},
			denied: []string{
				"http://localhost:4200", // default no longer granted
				"http://localhost:7187", // default no longer granted
				"http://evil.example",
				"https://dash.example.evil.test", // NOT a prefix match
			},
		},
		{
			name:   "several origins, comma-separated and individually trimmed",
			envSet: set,
			env:    "https://a.example, https://b.example ,https://c.example",
			allowed: []string{
				"https://a.example",
				"https://b.example",
				"https://c.example",
			},
			denied: []string{"http://localhost:4200", "https://d.example"},
		},
		{
			name:    "wildcard alone echoes the specific origin",
			envSet:  set,
			env:     "*",
			allowed: []string{"https://anything.example", "http://localhost:4200"},
		},
		{
			name:    "wildcard mixed with a host is still a wildcard (per-element, as Python)",
			envSet:  set,
			env:     "https://a.example,*",
			allowed: []string{"https://a.example", "https://anything.example"},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			// t.Setenv restores the previous state at test end.
			t.Setenv("MERGE_SERVICE_PORT", "7187")
			if tc.envSet {
				t.Setenv("ALLOWED_ORIGINS", tc.env)
			} else {
				unsetEnvForTest(t, "ALLOWED_ORIGINS")
			}
			h := productionCORS(t)

			// An unset variable and a variable set to "" are different inputs
			// that must reach the same result; the failure message has to tell
			// them apart or a reader cannot know which branch broke.
			shown := "<unset>"
			if tc.envSet {
				shown = fmt.Sprintf("%q", tc.env)
			}

			for _, origin := range tc.allowed {
				if got := acao(t, h, origin); got != origin {
					t.Errorf("ALLOWED_ORIGINS=%s: origin %q MUST be allowed;\n  want Access-Control-Allow-Origin=%q\n  got  %q",
						shown, origin, origin, got)
				}
			}
			for _, origin := range tc.denied {
				if got := acao(t, h, origin); got != "" {
					t.Errorf("ALLOWED_ORIGINS=%s: origin %q MUST be REJECTED;\n  want no Access-Control-Allow-Origin\n  got  %q",
						shown, origin, got)
				}
			}
		})
	}
}

// TestCORS_DefaultOriginsFollowMergeServicePort pins the port DERIVATION the
// Python reference performs (_MERGE_PORT = os.getenv("MERGE_SERVICE_PORT",
// "7187")). A hardcoded 7187 in the Go copy passes every test that happens to
// use the default port and fails the operator the moment they move the service.
func TestCORS_DefaultOriginsFollowMergeServicePort(t *testing.T) {
	t.Setenv("MERGE_SERVICE_PORT", "9187")
	unsetEnvForTest(t, "ALLOWED_ORIGINS")
	h := productionCORS(t)

	for _, origin := range []string{"http://localhost:9187", "http://127.0.0.1:9187"} {
		if got := acao(t, h, origin); got != origin {
			t.Errorf("MERGE_SERVICE_PORT=9187: %q MUST be a default origin;\n  want Access-Control-Allow-Origin=%q\n  got  %q",
				origin, origin, got)
		}
	}
	// The OLD port must no longer be granted — proving the value is derived,
	// not merely appended to a hardcoded list.
	if got := acao(t, h, "http://localhost:7187"); got != "" {
		t.Errorf("MERGE_SERVICE_PORT=9187: stale default http://localhost:7187 MUST NOT be granted; got %q", got)
	}
}

// TestCORS_ExtensionOrigins covers the browser-extension schemes the Python
// reference admits via allow_origin_regex (the BobaLink WebExtension calls the
// merge service from a background fetch whose Origin is
// chrome-extension://<id> / moz-extension://<uuid>; the per-install id cannot
// be allowlisted). The regex is anchored end-to-end, so an http(s) site whose
// host merely CONTAINS "chrome-extension" is NOT matched.
func TestCORS_ExtensionOrigins(t *testing.T) {
	unsetEnvForTest(t, "ALLOWED_ORIGINS")
	h := productionCORS(t)

	allowed := []string{
		"chrome-extension://abcdefghijklmnopabcdefghijklmnop",
		"moz-extension://0c2f2a1e-1111-2222-3333-444455556666",
	}
	denied := []string{
		"http://chrome-extension.evil.example",
		"https://evil.example/chrome-extension://x",
		"chrome-extension://bad id/with/slashes",
	}
	for _, origin := range allowed {
		if got := acao(t, h, origin); got != origin {
			t.Errorf("extension origin %q MUST be allowed; want %q, got %q", origin, origin, got)
		}
	}
	for _, origin := range denied {
		if got := acao(t, h, origin); got != "" {
			t.Errorf("origin %q MUST NOT be treated as an extension origin; got %q", origin, got)
		}
	}
}

// TestCORS_ExtensionOriginsGetNoCredentials pins the security boundary of the
// extension grant.
//
// An extension origin is admitted by PATTERN, so the grant covers every
// installed extension rather than a set the operator chose. Combining that open
// set with Access-Control-Allow-Credentials:true would let any extension the
// user happens to have installed read this service's responses with credentials
// attached. The Python reference is immune by construction
// (allow_credentials=False globally); this service sets it true for its real
// allowlist, so the credential grant must be withheld on the extension path.
func TestCORS_ExtensionOriginsGetNoCredentials(t *testing.T) {
	unsetEnvForTest(t, "ALLOWED_ORIGINS")
	t.Setenv("MERGE_SERVICE_PORT", "7187")

	headers := func(origin string) http.Header {
		gin.SetMode(gin.TestMode)
		r := gin.New()
		r.Use(productionCORS(t))
		r.GET("/x", func(c *gin.Context) { c.String(http.StatusOK, "ok") })
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/x", nil)
		req.Header.Set("Origin", origin)
		r.ServeHTTP(rec, req)
		return rec.Header()
	}

	const ext = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
	extHeaders := headers(ext)
	if got := extHeaders.Get("Access-Control-Allow-Origin"); got != ext {
		t.Fatalf("extension origin should still be allowed; want %q, got %q", ext, got)
	}
	if got := extHeaders.Get("Access-Control-Allow-Credentials"); got != "" {
		t.Errorf("extension origins are admitted by PATTERN (every installed extension), so they "+
			"MUST NOT receive Access-Control-Allow-Credentials; got %q", got)
	}

	// Control: a genuine allowlisted origin DOES still get credentials, proving
	// the check above is not passing merely because the header vanished
	// everywhere (§11.4.201(7)(b)).
	allowlisted := "http://localhost:4200"
	if got := headers(allowlisted).Get("Access-Control-Allow-Credentials"); got != "true" {
		t.Errorf("allowlisted origin %q MUST still receive Access-Control-Allow-Credentials:true; got %q",
			allowlisted, got)
	}
}
