package middleware

import (
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/corsorigins"
)

// proxyPort returns the download-proxy port, mirroring the way
// corsorigins.MergeServicePort derives the merge port, so neither is hardcoded.
func proxyPort() string {
	if v := strings.TrimSpace(os.Getenv("PROXY_PORT")); v != "" {
		return v
	}
	return "7186"
}

// defaultAllowedOrigins is the merge service's default allowlist.
//
// PARITY, STATED EXACTLY (this comment previously claimed a parity the code did
// not have — a hardcoded :7187 and two extra :7186 entries described as
// "mirrors the Python merge service", which is what kept the divergence
// invisible):
//
//   - The first four entries ARE the Python reference's _DEFAULT_ORIGINS
//     (download-proxy/src/api/__init__.py), including its port DERIVATION from
//     MERGE_SERVICE_PORT. They come from corsorigins.Defaults(), the single
//     definition both Go services share.
//
//   - The last two are a DELIBERATE, GO-ONLY SUPERSET: the download-proxy
//     origin on PROXY_PORT, which the Go merge service has granted since
//     RW-04. The Python reference does not grant it. It is kept because
//     dropping it would silently revoke an origin operators may rely on
//     (§11.4.122 — no silent removal of an existing capability); an operator
//     who wants strict Python parity sets ALLOWED_ORIGINS explicitly. The port
//     is derived from PROXY_PORT rather than hardcoded, matching the
//     derivation mechanism the reference uses for its own port.
//
// Evaluated per call, never cached, so the derived ports track the environment.
func defaultAllowedOrigins() []string {
	port := proxyPort()
	return append(corsorigins.Defaults(),
		"http://localhost:"+port, // download proxy
		"http://127.0.0.1:"+port, // download proxy (IPv4)
	)
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
// Any entry equal to "*" enables a wildcard policy that still echoes the
// specific request Origin (never the literal "*"), so credentials keep working
// without the forbidden wildcard+credentials combination.
//
// ALLOWED_ORIGINS: when no explicit origins are supplied, resolution falls
// through to the ALLOWED_ORIGINS environment variable and then to the defaults,
// via corsorigins.Resolve — the SHARED resolver that also backs boba-jackett,
// with the Python reference's exact semantics (comma-separated; each entry
// trimmed; a value that parses to nothing falls back to the defaults rather
// than revoking every origin; "*" detected PER ELEMENT so "a,*" is a wildcard).
//
// Browser-extension origins (chrome-extension:// / moz-extension://) are
// admitted by pattern, matching the reference's allow_origin_regex, because the
// per-install extension id cannot be allowlisted ahead of time.
func CORS(allowedOrigins ...string) gin.HandlerFunc {
	origins, wildcard := corsorigins.ResolveWithDefaults(allowedOrigins, defaultAllowedOrigins())
	allow := corsorigins.Index(origins)

	return func(c *gin.Context) {
		origin := c.Request.Header.Get("Origin")
		matched := false
		// Tracked separately because an extension origin is admitted by
		// PATTERN, not by an operator naming it: the per-install id is
		// unknowable in advance, so the grant necessarily covers EVERY
		// installed extension. Handing that open set
		// Access-Control-Allow-Credentials:true would let any extension the
		// user has installed read this service's responses with their
		// credentials attached. The Python reference cannot leak that way
		// because it sets allow_credentials=False globally; this service sets
		// it true (RW-04), so the credential grant is withheld on this path
		// specifically, keeping the extension grant no wider than the
		// reference's (§11.4.252 — the narrowest grant that still works).
		matchedByExtensionPattern := false
		if origin != "" {
			if wildcard {
				matched = true
			} else {
				matched = allow[corsorigins.Key(origin)]
				if !matched && corsorigins.IsExtensionOrigin(origin) {
					matched, matchedByExtensionPattern = true, true
				}
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
			if !matchedByExtensionPattern {
				c.Writer.Header().Set("Access-Control-Allow-Credentials", "true")
			}
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
