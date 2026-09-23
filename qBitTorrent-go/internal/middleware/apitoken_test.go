// BOB-203 — APIToken middleware tests.
//
// Mirrors the RED/GREEN/golden-FALSE discipline of the Python
// require_api_token test suite (tests/security/test_hooks_schedules_auth.py
// and tests/security/test_download_proxy_boba_token_auth.py):
//
//   - unset BOBA_API_TOKEN -> every method passes (fail-open, §11.4.122);
//   - set + no/wrong header -> mutating methods get 401, GET/HEAD/OPTIONS
//     still pass;
//   - set + correct header (either form) -> the request reaches the inner
//     handler (golden-FALSE: proves the gate is not refusing everything
//     unconditionally).
package middleware

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/gin-gonic/gin"
)

func init() {
	gin.SetMode(gin.TestMode)
}

func withAPITokenRouter(reached *bool) *gin.Engine {
	r := gin.New()
	r.Use(APIToken())
	handler := func(c *gin.Context) {
		*reached = true
		c.JSON(http.StatusOK, gin.H{"ok": true})
	}
	r.GET("/x", handler)
	r.POST("/x", handler)
	r.PUT("/x", handler)
	r.DELETE("/x", handler)
	return r
}

func doRequest(r *gin.Engine, method string, headers map[string]string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, "/x", nil)
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	rr := httptest.NewRecorder()
	r.ServeHTTP(rr, req)
	return rr
}

func TestRED_UnsetToken_EveryMethodPasses(t *testing.T) {
	t.Setenv("BOBA_API_TOKEN", "")
	for _, m := range []string{"GET", "POST", "PUT", "DELETE"} {
		reached := false
		r := withAPITokenRouter(&reached)
		rr := doRequest(r, m, nil)
		if rr.Code != http.StatusOK || !reached {
			t.Fatalf("%s with no token configured: code=%d reached=%v — fail-open contract broken", m, rr.Code, reached)
		}
	}
}

func TestGREEN_SetToken_MutatingMethodWithNoHeaderIs401(t *testing.T) {
	t.Setenv("BOBA_API_TOKEN", "s3cr3t-test-token")
	for _, m := range []string{"POST", "PUT", "DELETE"} {
		reached := false
		r := withAPITokenRouter(&reached)
		rr := doRequest(r, m, nil)
		if rr.Code != http.StatusUnauthorized {
			t.Fatalf("%s with no token header: expected 401, got %d", m, rr.Code)
		}
		if reached {
			t.Fatalf("%s: inner handler was reached despite missing token", m)
		}
		var body map[string]string
		if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
			t.Fatalf("401 body not JSON: %v (%s)", err, rr.Body.String())
		}
		if body["detail"] != "Unauthorized: valid API token required" {
			t.Fatalf("unexpected 401 body: %v", body)
		}
	}
}

func TestGREEN_SetToken_WrongTokenIs401(t *testing.T) {
	t.Setenv("BOBA_API_TOKEN", "s3cr3t-test-token")
	reached := false
	r := withAPITokenRouter(&reached)
	rr := doRequest(r, "POST", map[string]string{"X-Boba-Token": "not-the-token"})
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("wrong token: expected 401, got %d", rr.Code)
	}
	if reached {
		t.Fatal("inner handler reached with a wrong token")
	}
}

// TestGREEN_SetToken_CorrectTokenSucceeds is the golden-FALSE: proves the
// gate is not refusing everything unconditionally, via BOTH accepted header
// forms.
func TestGREEN_SetToken_CorrectTokenSucceeds(t *testing.T) {
	t.Setenv("BOBA_API_TOKEN", "s3cr3t-test-token")

	reached := false
	r := withAPITokenRouter(&reached)
	rr := doRequest(r, "POST", map[string]string{"X-Boba-Token": "s3cr3t-test-token"})
	if rr.Code != http.StatusOK || !reached {
		t.Fatalf("X-Boba-Token form: code=%d reached=%v", rr.Code, reached)
	}

	reached = false
	r2 := withAPITokenRouter(&reached)
	rr2 := doRequest(r2, "PUT", map[string]string{"Authorization": "Bearer s3cr3t-test-token"})
	if rr2.Code != http.StatusOK || !reached {
		t.Fatalf("Authorization: Bearer form: code=%d reached=%v", rr2.Code, reached)
	}
}

func TestGREEN_SetToken_ReadMethodsAlwaysPass(t *testing.T) {
	t.Setenv("BOBA_API_TOKEN", "s3cr3t-test-token")
	for _, m := range []string{"GET"} {
		reached := false
		r := withAPITokenRouter(&reached)
		rr := doRequest(r, m, nil)
		if rr.Code != http.StatusOK || !reached {
			t.Fatalf("%s (read) must pass even with the token armed and no header: code=%d reached=%v", m, rr.Code, reached)
		}
	}

	// OPTIONS has no registered route on this test router (no CORS preflight
	// wiring here), so assert directly against the middleware instead of
	// via 404-from-no-route — the gate itself must let it through to
	// whatever handles it next.
	reached := false
	r := gin.New()
	r.Use(APIToken())
	r.Use(func(c *gin.Context) { reached = true; c.Status(http.StatusNoContent) })
	rr := doRequest(r, "OPTIONS", nil)
	if !reached || rr.Code != http.StatusNoContent {
		t.Fatalf("OPTIONS must pass through unconditionally (CORS preflight): code=%d reached=%v", rr.Code, reached)
	}
}

func TestGREEN_EmptyBearerIsRejected(t *testing.T) {
	t.Setenv("BOBA_API_TOKEN", "s3cr3t-test-token")
	reached := false
	r := withAPITokenRouter(&reached)
	rr := doRequest(r, "POST", map[string]string{"Authorization": "Bearer "})
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("empty bearer token: expected 401, got %d", rr.Code)
	}
}

// TestGREEN_TokenReadPerRequest proves the token is read from the
// environment AT REQUEST TIME, not cached at middleware construction —
// mirrors require_api_token's own documented contract (operators can arm
// or rotate it without restarting).
func TestGREEN_TokenReadPerRequest(t *testing.T) {
	os.Setenv("BOBA_API_TOKEN", "") //nolint:usetesting // must persist across the router build below
	defer os.Unsetenv("BOBA_API_TOKEN")

	reached := false
	r := withAPITokenRouter(&reached)

	rr := doRequest(r, "POST", nil)
	if rr.Code != http.StatusOK {
		t.Fatalf("expected open access before arming, got %d", rr.Code)
	}

	os.Setenv("BOBA_API_TOKEN", "now-armed")
	reached = false
	rr2 := doRequest(r, "POST", nil)
	if rr2.Code != http.StatusUnauthorized {
		t.Fatalf("token armed mid-run but SAME router still allowed an unauthenticated POST: %d", rr2.Code)
	}
}
