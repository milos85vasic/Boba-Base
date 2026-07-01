package api

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/httpx"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
	"github.com/stretchr/testify/assert"
)

// recProxy records absolute-form requests and serves a sentinel .torrent body,
// standing in for the operator's upstream egress proxy.
type recProxy struct {
	mu   sync.Mutex
	urls []string
	srv  *httptest.Server
	body []byte
}

func newRecProxy(body []byte) *recProxy {
	p := &recProxy{body: body}
	p.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p.mu.Lock()
		p.urls = append(p.urls, r.RequestURI)
		p.mu.Unlock()
		w.Header().Set("Content-Type", "application/x-bittorrent")
		_, _ = w.Write(p.body)
	}))
	return p
}
func (p *recProxy) seen() []string {
	p.mu.Lock()
	defer p.mu.Unlock()
	out := make([]string, len(p.urls))
	copy(out, p.urls)
	return out
}

func restoreProxy(t *testing.T) {
	t.Helper()
	t.Cleanup(func() { _ = httpx.Configure("") })
}

// TestDownloadFileHandler_RoutesTrackerFetchThroughProxy drives the REAL
// production handler the dashboard hits when a user clicks "Torrent". With
// BOBA_UPSTREAM_PROXY configured, the handler's tracker-bound fetch of an
// upstream .torrent URL MUST traverse the proxy, and the bytes returned to the
// user MUST be the .torrent the proxy served (user-observable outcome).
//
// Falsifiability (CONST-XII §2/§10): reverting the `Transport: httpx.NewTransport()`
// wiring in DownloadFileHandler makes the fetch go direct to tracker.invalid,
// which does not resolve → handler returns 404 and px.seen() is empty → this
// test fails. Verified in-session (see report).
func TestDownloadFileHandler_RoutesTrackerFetchThroughProxy(t *testing.T) {
	gin.SetMode(gin.TestMode)
	restoreProxy(t)

	torrent := []byte("d8:announce30:http://tracker.invalid/announce4:infod") // bencode-ish sentinel
	px := newRecProxy(torrent)
	defer px.srv.Close()
	if err := httpx.Configure(px.srv.URL); err != nil {
		t.Fatalf("Configure: %v", err)
	}

	r := gin.New()
	r.POST("/api/v1/download/file", DownloadFileHandler(service.NewMergeSearchService(nil, 5)))

	payload, _ := json.Marshal(map[string]any{
		"result_id":     "ubuntu-iso",
		"download_urls": []string{"http://tracker.invalid/forum/dl.php?t=42"},
	})
	req, _ := http.NewRequest("POST", "/api/v1/download/file", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code, "handler should serve the torrent fetched via the proxy")
	assert.Equal(t, "application/x-bittorrent", w.Header().Get("Content-Type"))
	body, _ := io.ReadAll(w.Body)
	assert.Equal(t, torrent, body, "user must receive the .torrent bytes the proxy served")

	seen := px.seen()
	assert.Len(t, seen, 1, "tracker fetch must have traversed the proxy exactly once")
	if len(seen) == 1 {
		assert.Equal(t, "http://tracker.invalid/forum/dl.php?t=42", seen[0])
	}
}

// TestDownloadFileHandler_NoProxyMeansDirect proves the falsifiable negative:
// with NO proxy configured (and no *_PROXY env), the same request goes direct
// to the unresolvable tracker host, so NOTHING reaches the recording proxy and
// the handler reports the user-visible 404. This is the exact failure shape the
// positive test would degrade to if the proxy wiring were removed.
func TestDownloadFileHandler_NoProxyMeansDirect(t *testing.T) {
	gin.SetMode(gin.TestMode)
	restoreProxy(t)
	t.Setenv("HTTP_PROXY", "")
	t.Setenv("HTTPS_PROXY", "")
	t.Setenv("ALL_PROXY", "")

	px := newRecProxy([]byte("should-not-be-served"))
	defer px.srv.Close()
	if err := httpx.Configure(""); err != nil {
		t.Fatalf("Configure(empty): %v", err)
	}

	r := gin.New()
	r.POST("/api/v1/download/file", DownloadFileHandler(service.NewMergeSearchService(nil, 5)))

	payload, _ := json.Marshal(map[string]any{
		"result_id":     "x",
		"download_urls": []string{"http://tracker.invalid/forum/dl.php?t=42"},
	})
	req, _ := http.NewRequest("POST", "/api/v1/download/file", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusNotFound, w.Code, "direct fetch of an unresolvable host yields the 404 user-error")
	assert.Empty(t, px.seen(), "no request may reach the proxy when none is configured")
}
