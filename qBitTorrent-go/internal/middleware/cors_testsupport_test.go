package middleware

import (
	"os"
	"testing"

	"github.com/milos85vasic/qBitTorrent-go/internal/corsorigins"
)

// splitAllowedOrigins is the SAME call cmd/qbittorrent-proxy/main.go's
// parseAllowedOrigins makes, so the parity tests drive the real production
// chain (config -> split -> middleware) rather than a re-implementation of it.
//
// During the RED phase this held a verbatim copy of main.go's then-current
// body, so the failures reported were production behaviour and not an artefact
// of the test; it now delegates to the shared package main.go delegates to, so
// the two cannot drift apart.
func splitAllowedOrigins(raw string) []string {
	return corsorigins.Split(raw)
}

// unsetEnvForTest removes a variable for the duration of the test and restores
// the previous value (including "was not present") afterwards. t.Setenv can
// only SET a value; the "operator never configured this" case needs a genuine
// absence, which is a distinct branch of the contract under test.
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
