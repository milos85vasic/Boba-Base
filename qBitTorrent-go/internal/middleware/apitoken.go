// Package middleware — APIToken.
//
// BOB-203: wires a Go equivalent of the Python merge service's
// api/routes.py::require_api_token dependency onto qbittorrent-proxy-go's
// mutating routes, for parity with the Python fix. This binary was left
// with NO auth mechanism when BOB-198 (operator decision, 2026-08-26)
// mitigated its exposure by REFUSING TO START on a non-loopback bind
// (cmd/qbittorrent-proxy/main.go::checkLoopbackBind) rather than adding
// auth middleware — that decision is UNCHANGED and UNWEAKENED by this file:
// the loopback-bind guard stays exactly as it was, this middleware is
// additive defense-in-depth so that IF that guard is ever bypassed, relaxed,
// or the binary is deployed differently, the mutating surface still demands
// the same shared secret the Python service already requires.
package middleware

import (
	"crypto/subtle"
	"net/http"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
)

// APIToken returns a Gin middleware mirroring
// download-proxy/src/api/routes.py::require_api_token EXACTLY:
//
//   - BOBA_API_TOKEN unset/empty -> every request passes through (OPEN).
//     This is the DEFAULT and preserves the existing no-auth contract
//     (§11.4.122) -- unchanged by this middleware's mere presence.
//   - BOBA_API_TOKEN set -> a GET/HEAD/OPTIONS request still passes through
//     unconditionally: it is read-only, and OPTIONS must stay
//     credential-free for CORS preflight (mirrors
//     internal/jackettapi.WithAuth's identical reasoning for the same
//     browser-preflight requirement). Any OTHER method on a route this
//     middleware is installed on MUST present a MATCHING token via
//     "Authorization: Bearer <token>" OR "X-Boba-Token: <token>", compared
//     with crypto/subtle.ConstantTimeCompare (constant-time, the Go
//     equivalent of hmac.compare_digest on the Python side). Missing or
//     mismatched -> 401 with the SAME response body shape as the Python
//     dependency's 401 (`{"detail": "..."}`), so a caller of :7186, :7187,
//     or this Go alternative sees one consistent contract.
//
// The token is read from the environment on EVERY request (not cached at
// startup) so an operator can arm or rotate it without restarting -- the
// same contract as the Python dependency, and load-bearing for the same
// reason: tests monkeypatch/override the env var per-case.
//
// §11.4.10: the token value and the supplied header value are NEVER logged.
//
// Install this per ROUTE GROUP that should require it (mirrors the Python
// side's per-route Depends(require_api_token) selectivity) rather than
// globally on the engine -- some mutating-shaped POST routes on this
// service (e.g. /api/v1/search, /api/v1/search/sync,
// /api/v1/search/:id/abort, /api/v1/auth/qbittorrent) are deliberately left
// open on the Python side (public-by-design or a separately tracked
// known-gap) and installing this globally would silently protect MORE than
// the Python service does, breaking the parity this middleware exists to
// establish. See cmd/qbittorrent-proxy/main.go for exactly which groups
// carry it.
func APIToken() gin.HandlerFunc {
	return func(c *gin.Context) {
		switch c.Request.Method {
		case http.MethodGet, http.MethodHead, http.MethodOptions:
			c.Next()
			return
		}

		token := strings.TrimSpace(os.Getenv("BOBA_API_TOKEN"))
		if token == "" {
			c.Next()
			return
		}

		supplied := ""
		if auth := c.GetHeader("Authorization"); len(auth) >= 7 && strings.EqualFold(auth[:7], "bearer ") {
			supplied = strings.TrimSpace(auth[7:])
		}
		if supplied == "" {
			supplied = strings.TrimSpace(c.GetHeader("X-Boba-Token"))
		}

		if supplied == "" || subtle.ConstantTimeCompare([]byte(supplied), []byte(token)) != 1 {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"detail": "Unauthorized: valid API token required"})
			return
		}

		c.Next()
	}
}
