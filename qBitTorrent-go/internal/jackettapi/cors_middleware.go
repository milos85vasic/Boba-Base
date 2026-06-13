package jackettapi

import (
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
)

// defaultAllowedOrigins are the dashboard origins permitted by CORS by
// default. Add more via WithCORSOrigins if needed in production.
var defaultAllowedOrigins = []string{
	"http://localhost:4200",   // ng serve dev server
	"http://127.0.0.1:4200",   // ng serve dev server (IPv4)
	"http://localhost:7187",   // merge service Angular SPA
	"http://127.0.0.1:7187",   // merge service Angular SPA (IPv4)
}

// resolveOrigins returns the effective allow-list.  Priority:
//   1. explicit allowedOrigins slice (non-empty)
//   2. ALLOWED_ORIGINS env var (comma-separated; "*" = wildcard)
//   3. defaultAllowedOrigins
func resolveOrigins(explicit []string) ([]string, bool) {
	if len(explicit) > 0 {
		for _, o := range explicit {
			if strings.TrimSpace(o) == "*" {
				return nil, true
			}
		}
		return explicit, false
	}
	if env := os.Getenv("ALLOWED_ORIGINS"); env != "" {
		if strings.TrimSpace(env) == "*" {
			return nil, true
		}
		parts := strings.Split(env, ",")
		out := make([]string, 0, len(parts))
		for _, p := range parts {
			if t := strings.TrimSpace(p); t != "" {
				out = append(out, t)
			}
		}
		return out, false
	}
	return defaultAllowedOrigins, false
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
	allow := make(map[string]bool, len(origins))
	for _, o := range origins {
		allow[strings.ToLower(strings.TrimRight(o, "/"))] = true
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		matched := false
		if wildcard {
			matched = origin != ""
		} else if origin != "" {
			matched = allow[strings.ToLower(strings.TrimRight(origin, "/"))]
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
