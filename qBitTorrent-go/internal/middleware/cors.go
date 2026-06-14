package middleware

import (
	"net"
	"net/http"
	"net/url"
	"strings"

	"github.com/gin-gonic/gin"
)

// defaultAllowedOrigins are the dashboard origins permitted by CORS when no
// explicit allowlist is supplied. Mirrors the Python merge service
// (download-proxy/src/api/__init__.py _DEFAULT_ORIGINS) for parity: the ng
// serve dev server and the merge-service SPA on :7187, on both localhost and
// the 127.0.0.1 IPv4 literal.
var defaultAllowedOrigins = []string{
	"http://localhost:4200", // ng serve dev server
	"http://127.0.0.1:4200", // ng serve dev server (IPv4)
	"http://localhost:7187", // merge service Angular SPA
	"http://127.0.0.1:7187", // merge service Angular SPA (IPv4)
	"http://localhost:7186", // download proxy
	"http://127.0.0.1:7186", // download proxy (IPv4)
}

// sameHost reports whether the Origin header and the request's Host refer to
// the same machine by IP LITERAL (ignoring port). This lets the dashboard reach
// the service over a LAN IP without a hardcoded allow-list, whichever address
// the operator used (CLAUDE.md anti-bluff: no hardcoded localhost for
// client-facing CORS).
//
// SECURITY — DNS rebinding: the match is deliberately restricted to IP-LITERAL
// hosts. A DNS-rebinding attack needs a domain NAME (so the attacker can
// re-point it at the victim's LAN IP); refusing to match on names — only on
// literal IPs, which an external attacker cannot serve a page from — closes
// that hole while still allowing genuine LAN-IP access. r.Host is
// attacker-influenceable, so it is used ONLY to widen the grant to a literal IP
// that equals the Origin's literal IP — never to trust an arbitrary hostname.
//
// NOTE: this mirrors internal/jackettapi/cors_middleware.go sameHost. The logic
// is replicated here (not imported) to avoid a layering inversion — the generic
// middleware package must not depend on the jackettapi service package.
func sameHost(origin, reqHost string) bool {
	u, err := url.Parse(origin)
	if err != nil {
		return false
	}
	oHost := u.Hostname()
	rHost := reqHost
	if h, _, err := net.SplitHostPort(rHost); err == nil {
		rHost = h // strips the port; handles IPv4 host:port AND IPv6 [::1]:port
	}
	if oHost == "" || rHost == "" {
		return false
	}
	// Only honour IP-literal hosts (defeats DNS rebinding, which requires a name).
	if net.ParseIP(oHost) == nil || net.ParseIP(rHost) == nil {
		return false
	}
	return strings.EqualFold(oHost, rHost)
}

// CORS returns a Gin middleware that emits secure, allowlisted CORS headers.
//
// RW-04 fix: it NEVER emits "Access-Control-Allow-Origin: *" together with
// "Access-Control-Allow-Credentials: true" — that forbidden combination lets
// any website make credentialed cross-origin calls. Instead it ECHOES the
// request's Origin back in Allow-Origin ONLY when that Origin matches the
// allowlist (or is a same-host IP literal); for any other Origin no credentialed
// CORS headers are emitted, so the browser blocks the cross-origin response per
// same-origin policy.
//
// Passing "*" as the only allowlist entry enables a wildcard policy that still
// echoes the specific request Origin (never the literal "*"), so credentials
// keep working without the forbidden wildcard+credentials combination. Supplying
// no origins falls back to defaultAllowedOrigins.
func CORS(allowedOrigins ...string) gin.HandlerFunc {
	wildcard := false
	allow := make(map[string]bool)
	origins := allowedOrigins
	if len(origins) == 0 {
		origins = defaultAllowedOrigins
	}
	for _, o := range origins {
		if strings.TrimSpace(o) == "*" {
			wildcard = true
			continue
		}
		allow[strings.ToLower(strings.TrimRight(strings.TrimSpace(o), "/"))] = true
	}

	return func(c *gin.Context) {
		origin := c.Request.Header.Get("Origin")
		matched := false
		if origin != "" {
			if wildcard {
				matched = true
			} else {
				matched = allow[strings.ToLower(strings.TrimRight(origin, "/"))]
				if !matched {
					matched = sameHost(origin, c.Request.Host)
				}
			}
		}

		if matched {
			// Echo the specific Origin (never literal "*") so credentialed
			// requests work safely.
			c.Writer.Header().Set("Access-Control-Allow-Origin", origin)
			c.Writer.Header().Set("Vary", "Origin")
			c.Writer.Header().Set("Access-Control-Allow-Credentials", "true")
			c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Content-Length, Accept-Encoding, X-CSRF-Token, Authorization, accept, origin, Cache-Control, X-Requested-With")
			c.Writer.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS, GET, PUT, DELETE")
		}

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	}
}
