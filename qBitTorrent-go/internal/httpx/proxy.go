// Package httpx provides the shared outbound-HTTP wiring the qBitTorrent-go
// tracker-bound clients use to reach the internet.
//
// The single responsibility today is a CONFIGURABLE OUTBOUND PROXY. The Boba
// stack may run from an egress IP some upstream trackers block at the network
// layer (DNS failure / TLS interception). To let the operator route around the
// block with a residential / VPN / SOCKS egress, the tracker-bound transport
// routes through the proxy this package resolves.
//
// No proxy address is baked in. The proxy is supplied at runtime via
// BOBA_UPSTREAM_PROXY (parsed by internal/config) or, when that is unset, via
// the standard HTTP_PROXY / HTTPS_PROXY / ALL_PROXY / NO_PROXY environment
// variables (http.ProxyFromEnvironment). The default resolver (before Configure
// runs) is http.ProxyFromEnvironment, so the standard env mechanism works with
// zero extra wiring.
//
// Loopback / sidecar bypass: internal sidecars (qBittorrent, Jackett,
// FlareSolverr) are reached at 127.0.0.1 / localhost or by their service name
// (qbittorrent, jackett). Those hosts are NEVER routed through the upstream
// proxy — an external proxy cannot reach the operator's loopback, and a sidecar
// call must stay direct. The bypass set is loopback + NO_PROXY entries + the
// sidecar service names, mirroring http.ProxyFromEnvironment's built-in
// localhost exemption (http.ProxyURL alone does NOT honor it).
//
// SOCKS5 note: net/http's Transport natively dials "socks5://" proxy URLs
// returned by Transport.Proxy and performs REMOTE DNS for socks5 (the egress
// host resolves the tracker name, not this process) — critical when the local
// DNS is part of the block. No golang.org/x/net/proxy dependency is required.
package httpx

import (
	"fmt"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
)

// proxyResolver matches the signature of http.Transport.Proxy.
type proxyResolver = func(*http.Request) (*url.URL, error)

// defaultBypassHosts are always kept off the upstream proxy in the explicit
// (BOBA_UPSTREAM_PROXY) path: loopback aliases plus the in-stack sidecar
// service names. localhost / loopback IPs are also matched by isLoopbackHost,
// but listing them keeps the bypass set self-documenting.
var defaultBypassHosts = []string{"localhost", "127.0.0.1", "::1", "qbittorrent", "jackett"}

var (
	mu sync.RWMutex
	// resolver is the process-wide outbound-proxy resolver. It defaults to
	// http.ProxyFromEnvironment so the standard *_PROXY env vars (and NO_PROXY)
	// are honored even if Configure is never called.
	resolver proxyResolver = http.ProxyFromEnvironment
)

// ProxyFunc builds an http.Transport.Proxy resolver from a proxy URL string
// (the BOBA_UPSTREAM_PROXY value).
//
//   - empty string  → http.ProxyFromEnvironment (standard *_PROXY + NO_PROXY).
//   - non-empty     → route every non-bypassed request through the parsed URL.
//     net/http honors http://, https:// and socks5:// schemes here.
//
// A non-empty value that does not parse, or that lacks a scheme or host, is a
// hard error — a misconfigured operator env must be loud, never silently
// ignored.
func ProxyFunc(proxyURL string) (proxyResolver, error) {
	trimmed := strings.TrimSpace(proxyURL)
	if trimmed == "" {
		return http.ProxyFromEnvironment, nil
	}
	u, err := url.Parse(trimmed)
	if err != nil {
		return nil, fmt.Errorf("httpx: invalid BOBA_UPSTREAM_PROXY %q: %w", proxyURL, err)
	}
	if u.Scheme == "" || u.Host == "" {
		return nil, fmt.Errorf(
			"httpx: BOBA_UPSTREAM_PROXY %q must include a scheme and host "+
				"(e.g. http://host:8080, https://host:8080, or socks5://host:1080)",
			proxyURL,
		)
	}
	bypass := bypassMatcher()
	return func(req *http.Request) (*url.URL, error) {
		if bypass(req.URL.Hostname()) {
			return nil, nil
		}
		return u, nil
	}, nil
}

// bypassMatcher returns a predicate reporting whether host must stay DIRECT
// (not routed through the upstream proxy). It combines loopback detection, the
// sidecar service-name defaults, and the operator's NO_PROXY entries (exact
// host match plus ".suffix" domain match).
func bypassMatcher() func(string) bool {
	set := make(map[string]struct{})
	add := func(entries string) {
		for _, e := range strings.Split(entries, ",") {
			e = strings.ToLower(strings.TrimSpace(e))
			if e != "" {
				set[e] = struct{}{}
			}
		}
	}
	for _, h := range defaultBypassHosts {
		set[h] = struct{}{}
	}
	add(os.Getenv("NO_PROXY"))
	add(os.Getenv("no_proxy"))

	return func(host string) bool {
		host = strings.ToLower(strings.TrimSpace(host))
		if host == "" {
			return true
		}
		if isLoopbackHost(host) {
			return true
		}
		if _, ok := set[host]; ok {
			return true
		}
		for e := range set {
			if strings.HasPrefix(e, ".") && strings.HasSuffix(host, e) {
				return true
			}
		}
		return false
	}
}

// isLoopbackHost reports whether host is "localhost" or a loopback IP literal
// (127.0.0.0/8, ::1).
func isLoopbackHost(host string) bool {
	if strings.EqualFold(host, "localhost") {
		return true
	}
	if ip := net.ParseIP(host); ip != nil {
		return ip.IsLoopback()
	}
	return false
}

// Configure sets the process-wide outbound proxy from a proxy URL string.
// Call it ONCE at startup (after config load, before serving). Returns the
// ProxyFunc error verbatim so the caller can fail-fast on a bad value.
func Configure(proxyURL string) error {
	fn, err := ProxyFunc(proxyURL)
	if err != nil {
		return err
	}
	mu.Lock()
	resolver = fn
	mu.Unlock()
	return nil
}

// Proxy is the http.Transport.Proxy function every tracker-bound transport
// installs. It defers to the process-wide resolver at REQUEST time, so a client
// constructed before Configure runs still picks up the configured proxy.
func Proxy(req *http.Request) (*url.URL, error) {
	mu.RLock()
	fn := resolver
	mu.RUnlock()
	return fn(req)
}

// NewTransport returns a clone of http.DefaultTransport with Proxy wired to
// Proxy. Tracker-bound clients install this so their egress honors the
// configured outbound proxy. Cloning preserves every default timeout / pool
// setting and only overrides Proxy.
func NewTransport() *http.Transport {
	t := http.DefaultTransport.(*http.Transport).Clone()
	t.Proxy = Proxy
	return t
}
