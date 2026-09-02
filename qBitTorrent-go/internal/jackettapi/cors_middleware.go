package jackettapi

import (
	"net"
	"net/http"
	"net/url"
	"strings"

	"github.com/milos85vasic/qBitTorrent-go/internal/corsorigins"
)

// resolveOrigins returns the effective allow-list. Priority:
//  1. explicit allowedOrigins slice (non-empty)
//  2. ALLOWED_ORIGINS env var (comma-separated; any "*" entry = wildcard)
//  3. the shared default allowlist
//
// The implementation lives in internal/corsorigins, shared with the merge
// service's middleware, so the two cannot drift (§11.4.251). This function had
// its own copy of the logic and HAD drifted on two measured points, each fixed
// by delegating:
//
//   - WILDCARD DETECTION was whole-string (`TrimSpace(env) == "*"`), so
//     ALLOWED_ORIGINS="https://a.example,*" produced a NON-wildcard list holding
//     a literal "*" entry that no real Origin can equal — the operator's
//     wildcard silently did nothing. The reference tests each element after
//     splitting, so that value IS a wildcard.
//
//   - EMPTY-AFTER-PARSE ("   ", " , ,") produced an EMPTY allowlist, silently
//     revoking every default origin. The reference falls back to its defaults.
//
// The defaults also now derive their port from MERGE_SERVICE_PORT instead of
// hardcoding 7187, matching the reference's own derivation.
func resolveOrigins(explicit []string) ([]string, bool) {
	return corsorigins.Resolve(explicit)
}

// WithCORS wraps an inner handler with permissive-but-allowlisted CORS:
//   - the request's Origin header must match one of allowedOrigins
//     (exact prefix match; no wildcards) — otherwise no CORS headers are
//     emitted and the browser blocks the response per same-origin policy.
//   - Set ALLOWED_ORIGINS="*" to allow any origin (echoes back the request's
//     Origin header so credentials still work for mutating endpoints).
//   - all standard methods (GET/HEAD/POST/PATCH/PUT/DELETE/OPTIONS) are
//     allowed.
//   - Authorization + Content-Type are the allowed request headers
//     (matches what the dashboard actually sends).
//   - OPTIONS preflight short-circuits with 204 + CORS headers BEFORE
//     reaching the inner handler. The inner handler (auth middleware)
//     also passes OPTIONS through, but the short-circuit avoids the
//     extra round-trip when the preflight has nothing to do.
//
// CONST-XII: this middleware is regression-guarded by the Playwright
// walkthroughs in frontend/e2e/ — if CORS breaks, every dialog-driven
// POST/PATCH/DELETE in the dashboard fails at the browser layer, and
// the Playwright assertion on the post-action DOM state catches it.
// sameHost reports whether the Origin header and the request's Host refer to
// the same machine by IP LITERAL (ignoring port) — e.g. Origin
// "http://192.168.0.132:7187" and Host "192.168.0.132:7189". This lets the
// dashboard reach boba-jackett over a LAN IP without a hardcoded allow-list,
// regardless of which IP the operator used.
//
// SECURITY — DNS rebinding: the match is deliberately restricted to IP-LITERAL
// hosts. A DNS-rebinding attack needs a domain NAME (so the attacker can
// re-point it at the victim's LAN IP); the browser would then send a matching
// name in BOTH Origin and Host. Refusing to match on names — only on literal
// IPs, which an external attacker cannot serve a page from — closes that hole
// while still allowing genuine LAN-IP access. localhost / 127.0.0.1 are covered
// by the static allow-list, not here. r.Host is attacker-influenceable, so it
// is used ONLY to widen the grant to a literal IP that equals the Origin's
// literal IP — never to trust an arbitrary hostname.
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

func WithCORS(allowedOrigins []string, inner http.Handler) http.Handler {
	origins, wildcard := resolveOrigins(allowedOrigins)
	allow := corsorigins.Index(origins)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		matched := false
		if wildcard {
			matched = origin != ""
		} else if origin != "" {
			matched = allow[corsorigins.Key(origin)]
			if !matched {
				// Same-machine sibling-port: the dashboard (:7187) and this
				// service (:7189) are served from the SAME host, whichever
				// address the operator uses (localhost, a LAN IP like
				// 192.168.0.132, a hostname). Allow any Origin whose host matches
				// the request's own Host — deriving the allowed origin FROM THE
				// REQUEST rather than a hardcoded localhost list (CLAUDE.md
				// anti-bluff: no hardcoded localhost for client-facing CORS).
				matched = sameHost(origin, r.Host)
			}
		}
		if matched {
			// Echo the specific Origin (never literal "*") so credentialed
			// requests work — for both the wildcard and allow-list/same-host paths.
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Vary", "Origin")
			w.Header().Set("Access-Control-Allow-Methods",
				"GET, HEAD, POST, PATCH, PUT, DELETE, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers",
				"Authorization, Content-Type")
			w.Header().Set("Access-Control-Max-Age", "600") // cache preflight 10 min
		}
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		inner.ServeHTTP(w, r)
	})
}
