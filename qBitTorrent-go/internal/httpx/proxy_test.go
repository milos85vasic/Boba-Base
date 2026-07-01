package httpx

import (
	"io"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
)

// recordingProxy is an in-process forward proxy: when a client routes an
// http:// request through it, the request arrives in absolute form
// (GET http://host/path) and we record the absolute URL, then short-circuit
// with a sentinel body. A request that reaches it proves traversal; an empty
// log proves the request went direct.
type recordingProxy struct {
	mu      sync.Mutex
	urls    []string
	sentinel string
	srv     *httptest.Server
}

func newRecordingProxy() *recordingProxy {
	p := &recordingProxy{sentinel: "PROXY-SENTINEL-BODY"}
	p.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p.mu.Lock()
		p.urls = append(p.urls, r.RequestURI)
		p.mu.Unlock()
		w.Header().Set("Content-Type", "application/x-bittorrent")
		_, _ = io.WriteString(w, p.sentinel)
	}))
	return p
}

func (p *recordingProxy) URL() string { return p.srv.URL }
func (p *recordingProxy) close()      { p.srv.Close() }
func (p *recordingProxy) seen() []string {
	p.mu.Lock()
	defer p.mu.Unlock()
	out := make([]string, len(p.urls))
	copy(out, p.urls)
	return out
}

func reqTo(t *testing.T, rawurl string) *http.Request {
	t.Helper()
	r, err := http.NewRequest("GET", rawurl, nil)
	if err != nil {
		t.Fatalf("build request %q: %v", rawurl, err)
	}
	return r
}

// resetResolver restores the default env-based resolver so process-wide state
// from one test never leaks into the next.
func resetResolver(t *testing.T) {
	t.Helper()
	t.Cleanup(func() {
		mu.Lock()
		resolver = http.ProxyFromEnvironment
		mu.Unlock()
	})
}

func TestProxyFuncRoutesTrackerThroughExplicitProxy(t *testing.T) {
	resetResolver(t)
	const px = "socks5://10.9.8.7:1080"
	if err := Configure(px); err != nil {
		t.Fatalf("Configure: %v", err)
	}
	got, err := Proxy(reqTo(t, "https://rutracker.org/forum/index.php"))
	if err != nil {
		t.Fatalf("Proxy: %v", err)
	}
	if got == nil {
		t.Fatal("tracker request was NOT routed through the proxy (got nil)")
	}
	if got.String() != px {
		t.Fatalf("tracker routed through %q, want %q", got.String(), px)
	}
}

func TestProxyFuncBypassesLoopbackAndSidecars(t *testing.T) {
	resetResolver(t)
	if err := Configure("http://10.9.8.7:8080"); err != nil {
		t.Fatalf("Configure: %v", err)
	}
	// Each of these MUST stay direct (nil) even though a proxy is configured.
	for _, host := range []string{
		"http://127.0.0.1:7185/api/v2/auth/login", // qbittorrent loopback
		"http://localhost:9117/api/v2.0/indexers", // jackett loopback
		"http://qbittorrent:7185/api/v2/torrents/add",
		"http://jackett:9117/UI/Dashboard",
		"http://[::1]:8191/",
	} {
		got, err := Proxy(reqTo(t, host))
		if err != nil {
			t.Fatalf("Proxy(%q): %v", host, err)
		}
		if got != nil {
			t.Fatalf("loopback/sidecar %q was routed through proxy %q, want DIRECT (nil)", host, got)
		}
	}
}

func TestProxyFuncRespectsNoProxyEnv(t *testing.T) {
	resetResolver(t)
	t.Setenv("NO_PROXY", "internal.example,.corp.local")
	if err := Configure("http://10.9.8.7:8080"); err != nil {
		t.Fatalf("Configure: %v", err)
	}
	// NO_PROXY exact + suffix entries stay direct.
	for _, host := range []string{"http://internal.example/x", "http://api.corp.local/y"} {
		got, _ := Proxy(reqTo(t, host))
		if got != nil {
			t.Fatalf("NO_PROXY host %q routed through %q, want DIRECT", host, got)
		}
	}
	// A normal tracker host is still proxied.
	got, _ := Proxy(reqTo(t, "https://nnmclub.to/forum/tracker.php"))
	if got == nil {
		t.Fatal("tracker host should still be proxied when NO_PROXY does not match it")
	}
}

func TestProxyFuncEmptyFallsBackToEnv(t *testing.T) {
	resetResolver(t)
	t.Setenv("HTTP_PROXY", "http://env-proxy.example:3128")
	t.Setenv("NO_PROXY", "")
	if err := Configure(""); err != nil {
		t.Fatalf("Configure(empty): %v", err)
	}
	got, err := Proxy(reqTo(t, "http://rutor.info/search"))
	if err != nil {
		t.Fatalf("Proxy: %v", err)
	}
	if got == nil || got.Host != "env-proxy.example:3128" {
		t.Fatalf("empty BOBA_UPSTREAM_PROXY should fall back to HTTP_PROXY; got %v", got)
	}
}

func TestProxyFuncRejectsMalformedProxy(t *testing.T) {
	if _, err := ProxyFunc("://nope"); err == nil {
		t.Fatal("expected error for proxy URL without a scheme")
	}
	if _, err := ProxyFunc("just-a-host:8080"); err == nil {
		t.Fatal("expected error for proxy URL missing scheme//host shape")
	}
}

// TestNewTransportTrackerTraversesProxy is the end-to-end anti-bluff proof: a
// real *http.Client built from NewTransport() routes a tracker-host request
// through a real recording proxy, and the RESPONSE BODY is the one the proxy
// served (user-observable outcome, not a call count).
func TestNewTransportTrackerTraversesProxy(t *testing.T) {
	resetResolver(t)
	px := newRecordingProxy()
	defer px.close()
	if err := Configure(px.URL()); err != nil {
		t.Fatalf("Configure: %v", err)
	}

	client := &http.Client{Transport: NewTransport()}
	resp, err := client.Get("http://tracker.invalid/file.torrent")
	if err != nil {
		t.Fatalf("GET via proxy: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if string(body) != px.sentinel {
		t.Fatalf("body = %q, want proxy sentinel %q", string(body), px.sentinel)
	}
	seen := px.seen()
	if len(seen) != 1 || seen[0] != "http://tracker.invalid/file.torrent" {
		t.Fatalf("proxy did not record the tracker request; saw %v", seen)
	}
}

// TestNewTransportLoopbackStaysDirect proves the loopback/sidecar bypass on the
// real transport: with a proxy configured, a call to a loopback origin reaches
// the ORIGIN directly and the proxy log stays empty.
func TestNewTransportLoopbackStaysDirect(t *testing.T) {
	resetResolver(t)
	origin := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.WriteString(w, "ORIGIN-DIRECT")
	}))
	defer origin.Close()
	px := newRecordingProxy()
	defer px.close()
	if err := Configure(px.URL()); err != nil {
		t.Fatalf("Configure: %v", err)
	}

	// origin.URL is http://127.0.0.1:<port> — a loopback host, must bypass.
	client := &http.Client{Transport: NewTransport()}
	resp, err := client.Get(origin.URL + "/health")
	if err != nil {
		t.Fatalf("GET loopback: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if string(body) != "ORIGIN-DIRECT" {
		t.Fatalf("loopback body = %q, want ORIGIN-DIRECT", string(body))
	}
	if seen := px.seen(); len(seen) != 0 {
		t.Fatalf("loopback request leaked through the proxy: %v", seen)
	}
}
