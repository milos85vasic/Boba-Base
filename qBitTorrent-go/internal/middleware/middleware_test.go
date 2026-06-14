package middleware

import (
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

func init() {
	gin.SetMode(gin.TestMode)
}

// legacyVulnerableCORS reproduces the pre-fix RW-04 middleware verbatim so the
// §11.4.115 RED test can prove the defect was genuinely present on the broken
// artifact (RED_MODE=1). It is test-only and never wired into production.
func legacyVulnerableCORS(allowOrigin string) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", allowOrigin)
		c.Writer.Header().Set("Access-Control-Allow-Credentials", "true")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS, GET, PUT, DELETE")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	}
}

func TestCORS_Headers(t *testing.T) {
	r := gin.New()
	r.Use(CORS("http://localhost:7187"))
	r.GET("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest("GET", "/test", nil)
	req.Header.Set("Origin", "http://localhost:7187")
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "http://localhost:7187", w.Header().Get("Access-Control-Allow-Origin"))
	assert.Equal(t, "true", w.Header().Get("Access-Control-Allow-Credentials"))
	assert.Equal(t, "Origin", w.Header().Get("Vary"))
}

func TestCORS_Options(t *testing.T) {
	r := gin.New()
	r.Use(CORS("http://localhost:7187"))
	r.OPTIONS("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest("OPTIONS", "/test", nil)
	req.Header.Set("Origin", "http://localhost:7187")
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusNoContent, w.Code)
}

// TestCORS_NoWildcardWithCredentials is the §11.4.115 RED-first security guard
// for RW-04: a wildcard Access-Control-Allow-Origin together with
// Access-Control-Allow-Credentials: true is a forbidden combination — it lets
// ANY website make credentialed cross-origin calls. The middleware MUST NEVER
// emit "*" while also emitting credentials, and MUST NOT echo a non-allowlisted
// (e.g. attacker) Origin.
//
// RED_MODE=1 reproduces the defect against the pre-fix CORS("*") impl (which set
// Allow-Origin:* + Allow-Credentials:true for any origin); RED_MODE=0 (the
// default standing guard) asserts the fixed behaviour: a disallowed origin gets
// NO credentialed wildcard, an allow-listed origin is echoed verbatim.
func TestCORS_NoWildcardWithCredentials(t *testing.T) {
	redMode := os.Getenv("RED_MODE") == "1"

	allowlist := []string{"http://localhost:7187", "http://127.0.0.1:7187"}

	newRouter := func() *gin.Engine {
		r := gin.New()
		if redMode {
			// Pre-fix vulnerable middleware: wildcard + credentials for everyone.
			r.Use(legacyVulnerableCORS("*"))
		} else {
			r.Use(CORS(allowlist...))
		}
		r.GET("/test", func(c *gin.Context) { c.String(http.StatusOK, "ok") })
		r.OPTIONS("/test", func(c *gin.Context) { c.String(http.StatusOK, "ok") })
		return r
	}

	// --- Disallowed (attacker) origin: MUST NOT get wildcard+credentials. ---
	w := httptest.NewRecorder()
	req, _ := http.NewRequest("GET", "/test", nil)
	req.Header.Set("Origin", "http://evil.example")
	newRouter().ServeHTTP(w, req)

	allowOrigin := w.Header().Get("Access-Control-Allow-Origin")
	allowCreds := w.Header().Get("Access-Control-Allow-Credentials")

	forbidden := allowOrigin == "*" && allowCreds == "true"
	assert.False(t, forbidden,
		"RW-04: response MUST NOT combine Allow-Origin:* with Allow-Credentials:true (got origin=%q creds=%q)",
		allowOrigin, allowCreds)
	assert.NotEqual(t, "http://evil.example", allowOrigin,
		"a non-allowlisted (attacker) Origin MUST NOT be echoed back")

	// --- Allowlisted origin: MUST be echoed back exactly (never "*"). ---
	w2 := httptest.NewRecorder()
	req2, _ := http.NewRequest("GET", "/test", nil)
	req2.Header.Set("Origin", "http://localhost:7187")
	newRouter().ServeHTTP(w2, req2)
	assert.Equal(t, "http://localhost:7187", w2.Header().Get("Access-Control-Allow-Origin"),
		"an allow-listed Origin MUST be echoed verbatim so credentialed requests work")
	assert.NotEqual(t, "*", w2.Header().Get("Access-Control-Allow-Origin"),
		"the echoed origin MUST be the specific origin, never the wildcard")
}

func TestLogger_NoPanic(t *testing.T) {
	r := gin.New()
	r.Use(Logger())
	r.GET("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest("GET", "/test", nil)
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
}
