package bridge

import (
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type fakeQBittorrentBridge struct {
	server      *httptest.Server
	requests    []http.Request
	addCalls    int
	loginCookie string
}

func newFakeQBittorrentBridge() *fakeQBittorrentBridge {
	fq := &fakeQBittorrentBridge{loginCookie: "QBT_SID_7186=bridge123"}
	fq.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fq.requests = append(fq.requests, *r.Clone(r.Context()))
		switch r.URL.Path {
		case "/api/v2/auth/login":
			w.Header().Set("Set-Cookie", fq.loginCookie)
			w.WriteHeader(http.StatusNoContent)
		case "/api/v2/torrents/add":
			fq.addCalls++
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"success_count":1}`))
		case "/api/v2/app/version":
			_, _ = w.Write([]byte("v5.2.3"))
		default:
			_, _ = io.Copy(io.Discard, r.Body)
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("qbit-root"))
		}
	}))
	return fq
}

func (f *fakeQBittorrentBridge) URL() string {
	return f.server.URL
}

func (f *fakeQBittorrentBridge) Close() {
	f.server.Close()
}

func TestBridgeHealth(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrentBridge()
	defer qbit.Close()

	cfg := &Config{QBittorrentURL: qbit.URL(), Port: 7188}
	r := NewRouter(cfg)
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Body.String(), "webui-bridge")
	assert.Contains(t, w.Body.String(), `"backend":"ok"`)
}

func TestBridgeRootProxy(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrentBridge()
	defer qbit.Close()

	cfg := &Config{QBittorrentURL: qbit.URL(), Port: 7188}
	r := NewRouter(cfg)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Accept", "text/html")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "qbit-root", w.Body.String())
	require.Len(t, qbit.requests, 1)
	assert.Equal(t, "/", qbit.requests[0].URL.Path)
	assert.Equal(t, "text/html", qbit.requests[0].Header.Get("Accept"))
}

func TestBridgeRefererOriginRewrite(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrentBridge()
	defer qbit.Close()

	cfg := &Config{QBittorrentURL: qbit.URL(), Port: 7188}
	r := NewRouter(cfg)
	req := httptest.NewRequest(http.MethodPost, "/api/v2/auth/login", nil)
	req.Header.Set("Referer", "http://localhost:7188/")
	req.Header.Set("Origin", "http://localhost:7188")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	require.Len(t, qbit.requests, 1)
	assert.Equal(t, qbit.URL(), qbit.requests[0].Header.Get("Referer"))
	assert.Equal(t, qbit.URL(), qbit.requests[0].Header.Get("Origin"))
}

func TestBridgeIdentifiesPrivateTracker(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrentBridge()
	defer qbit.Close()

	tmpDir := t.TempDir()
	torrentPath := filepath.Join(tmpDir, "rutracker.torrent")
	require.NoError(t, os.WriteFile(torrentPath, []byte("d8:announce"), 0o600))

	nova2dl := filepath.Join(tmpDir, "nova2dl.py")
	// Fake nova2dl echoes "<torrent_path> ok" just like the real one does.
	script := fmt.Sprintf(`#!/usr/bin/env python3
print("%s ok")
`, torrentPath)
	require.NoError(t, os.WriteFile(nova2dl, []byte(script), 0o700))

	cfg := &Config{
		QBittorrentURL:      qbit.URL(),
		QBittorrentUsername: "admin",
		QBittorrentPassword: "admin",
		Port:                7188,
		Nova2DLPath:         nova2dl,
	}
	r := NewRouter(cfg)

	req := httptest.NewRequest(http.MethodGet, "/?urls="+url.QueryEscape("https://rutracker.org/forum/dl.php?t=123"), nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "OK", w.Body.String())
	assert.Equal(t, 1, qbit.addCalls)
}

func TestBridgeFallbackToProxyForPublicURL(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrentBridge()
	defer qbit.Close()

	cfg := &Config{QBittorrentURL: qbit.URL(), Port: 7188}
	r := NewRouter(cfg)
	req := httptest.NewRequest(http.MethodGet, "/?urls="+url.QueryEscape("https://example.com/file.torrent"), nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "qbit-root", w.Body.String())
	assert.Equal(t, 0, qbit.addCalls)
}

func TestIdentifyTrackerInText(t *testing.T) {
	assert.Equal(t, "rutracker", identifyTrackerInText("https://rutracker.org/forum/dl.php?t=1"))
	assert.Equal(t, "kinozal", identifyTrackerInText("https://kinozal.guru/details.php?id=1"))
	assert.Equal(t, "nnmclub", identifyTrackerInText("https://nnmclub.to/forum/viewtopic.php?t=1"))
	assert.Equal(t, "iptorrents", identifyTrackerInText("https://iptorrents.com/t/1"))
	assert.Equal(t, "", identifyTrackerInText("https://example.com/file.torrent"))
}

func TestQbitAddSucceededBridge(t *testing.T) {
	assert.True(t, qbitAddSucceeded(http.StatusOK, `{"success_count":1}`))
	assert.True(t, qbitAddSucceeded(http.StatusAccepted, `{"pending_count":1}`))
	assert.True(t, qbitAddSucceeded(http.StatusConflict, ""))
	assert.False(t, qbitAddSucceeded(http.StatusBadRequest, "Fails."))
}

func TestDefaultConfig(t *testing.T) {
	t.Setenv("QBITTORRENT_URL", "http://qbit:8080")
	t.Setenv("BRIDGE_PORT", "9000")
	t.Setenv("NOVA2DL_PATH", "/tmp/nova2dl.py")

	cfg := DefaultConfig()
	assert.Equal(t, "http://qbit:8080", cfg.QBittorrentURL)
	assert.Equal(t, 9000, cfg.Port)
	assert.Equal(t, "/tmp/nova2dl.py", cfg.Nova2DLPath)
	assert.Equal(t, "admin", cfg.QBittorrentUsername)
}

func TestResolveQBittorrentURLFallback(t *testing.T) {
	t.Setenv("QBITTORRENT_URL", "")
	t.Setenv("BRIDGE_QBIT_URL", "")
	t.Setenv("QBITTORRENT_HOST", "127.0.0.1")
	t.Setenv("QBITTORRENT_PORT", "7185")

	cfg := DefaultConfig()
	assert.True(t, strings.HasSuffix(cfg.QBittorrentURL, ":7185"))
}
