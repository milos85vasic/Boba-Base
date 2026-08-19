// BOB-111 — Go per-IP rate limiter tests. RED-first (paired-mutation
// discipline per §11.4.115(F)): a disabled limiter accepts every request; an
// enabled limiter refuses over-budget requests from the same IP but keeps
// serving a DIFFERENT IP normally (per-IP scope proof + no service brown-out
// under §11.4.85 burst).
package middleware

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/gin-gonic/gin"
)

func okHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"ok":true}`))
	})
}

// TestRED_DisabledLimiter_NeverGates — paired-mutation baseline: with a
// disabled limiter, 50 back-to-back requests all succeed.
func TestRED_DisabledLimiter_NeverGates(t *testing.T) {
	r := NewRateLimiter(0, 0) // disabled
	h := WithRateLimit(r, okHandler())

	for i := 0; i < 50; i++ {
		req := httptest.NewRequest("GET", "/", nil)
		req.RemoteAddr = "10.0.0.1:1234"
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, req)
		if rr.Code != http.StatusOK {
			t.Fatalf("disabled limiter must allow every request, iteration %d got %d", i, rr.Code)
		}
	}
}

// TestGREEN_OverBudgetReturns429 — request #(burst+1) from the same IP must
// be refused; the response body carries the exact minimal token.
func TestGREEN_OverBudgetReturns429(t *testing.T) {
	// 30/minute + burst 5 → the first 5 back-to-back requests fill the
	// bucket; the 6th (before a token regenerates) is refused.
	r := NewRateLimiter(30, 5)
	h := WithRateLimit(r, okHandler())

	for i := 0; i < 5; i++ {
		req := httptest.NewRequest("GET", "/", nil)
		req.RemoteAddr = "10.0.0.1:9999"
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, req)
		if rr.Code != http.StatusOK {
			t.Fatalf("burst request %d should succeed, got %d", i+1, rr.Code)
		}
	}

	// The 6th request within the same instant exceeds the burst.
	req := httptest.NewRequest("GET", "/", nil)
	req.RemoteAddr = "10.0.0.1:9999"
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusTooManyRequests {
		t.Fatalf("6th burst request must be 429, got %d", rr.Code)
	}

	// §11.4.10 — minimal body, opaque token, no IP echoed.
	var body map[string]string
	if err := json.NewDecoder(rr.Body).Decode(&body); err != nil {
		t.Fatalf("429 body must be JSON, err=%v", err)
	}
	if body["error"] != "rate_limited" {
		t.Fatalf("429 body must be {error: rate_limited}, got %v", body)
	}
	raw := rr.Body.String()
	for _, forbidden := range []string{"10.0.0.1", "9999", "30", "5"} {
		if strings.Contains(raw, forbidden) {
			t.Fatalf("429 body leaked %q: %s", forbidden, raw)
		}
	}
	if rr.Header().Get("Retry-After") == "" {
		t.Fatalf("Retry-After header required on 429")
	}
}

// TestGREEN_PerIPScope_DifferentIPNotThrottled — throttling one caller must
// NOT throttle a different caller (per-IP scope proof, §11.4.85 chaos).
func TestGREEN_PerIPScope_DifferentIPNotThrottled(t *testing.T) {
	r := NewRateLimiter(30, 2)
	h := WithRateLimit(r, okHandler())

	// Exhaust caller A's burst.
	for i := 0; i < 2; i++ {
		req := httptest.NewRequest("GET", "/", nil)
		req.RemoteAddr = "10.0.0.1:1111"
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, req)
		if rr.Code != http.StatusOK {
			t.Fatalf("A burst %d should be 200, got %d", i+1, rr.Code)
		}
	}
	// A is now throttled.
	rrA := httptest.NewRecorder()
	reqA := httptest.NewRequest("GET", "/", nil)
	reqA.RemoteAddr = "10.0.0.1:1111"
	h.ServeHTTP(rrA, reqA)
	if rrA.Code != http.StatusTooManyRequests {
		t.Fatalf("A over-budget should be 429, got %d", rrA.Code)
	}

	// B (different IP) has a fresh bucket.
	rrB := httptest.NewRecorder()
	reqB := httptest.NewRequest("GET", "/", nil)
	reqB.RemoteAddr = "10.0.0.2:2222"
	h.ServeHTTP(rrB, reqB)
	if rrB.Code != http.StatusOK {
		t.Fatalf("B should NOT be throttled by A's exhaustion, got %d", rrB.Code)
	}
}

// TestChaos_ConcurrentBurst_NoCrashNo5xx — 100 concurrent requests from ONE
// IP produce a mix of 200 + 429 with ZERO 5xx (§11.4.85). Service stays
// responsive.
func TestChaos_ConcurrentBurst_NoCrashNo5xx(t *testing.T) {
	r := NewRateLimiter(30, 5)
	h := WithRateLimit(r, okHandler())

	var wg sync.WaitGroup
	var ok, throttled, err5xx int64
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			req := httptest.NewRequest("GET", "/", nil)
			req.RemoteAddr = "10.0.0.9:5555"
			rr := httptest.NewRecorder()
			h.ServeHTTP(rr, req)
			switch {
			case rr.Code == http.StatusOK:
				atomic.AddInt64(&ok, 1)
			case rr.Code == http.StatusTooManyRequests:
				atomic.AddInt64(&throttled, 1)
			case rr.Code >= 500:
				atomic.AddInt64(&err5xx, 1)
			}
		}()
	}
	wg.Wait()
	if err5xx != 0 {
		t.Fatalf("no 5xx allowed during burst; got %d", err5xx)
	}
	if ok == 0 {
		t.Fatalf("some requests should succeed in burst, ok=%d", ok)
	}
	if throttled == 0 {
		t.Fatalf("some requests should be throttled in burst, throttled=%d", throttled)
	}
	if ok+throttled != 100 {
		t.Fatalf("every response should be 200 or 429; ok=%d throttled=%d", ok, throttled)
	}
}

// TestGin_RateLimit_Integrates — the Gin middleware form used by
// qbittorrent-proxy also refuses over-budget calls.
func TestGin_RateLimit_Integrates(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := NewRateLimiter(30, 2)
	engine := gin.New()
	engine.Use(GinRateLimit(r))
	engine.GET("/ping", func(c *gin.Context) { c.JSON(http.StatusOK, gin.H{"pong": true}) })

	// First 2 OK.
	for i := 0; i < 2; i++ {
		rr := httptest.NewRecorder()
		req := httptest.NewRequest("GET", "/ping", nil)
		req.RemoteAddr = "10.1.1.1:8080"
		engine.ServeHTTP(rr, req)
		if rr.Code != http.StatusOK {
			t.Fatalf("burst %d should be 200, got %d", i+1, rr.Code)
		}
	}
	// 3rd = 429.
	rr := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/ping", nil)
	req.RemoteAddr = "10.1.1.1:8080"
	engine.ServeHTTP(rr, req)
	if rr.Code != http.StatusTooManyRequests {
		t.Fatalf("over-budget Gin request must be 429, got %d", rr.Code)
	}
}
