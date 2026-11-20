package api

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// fakeQBittorrent stands in for the real qBittorrent WebUI/WebAPI.
type fakeQBittorrent struct {
	server      *httptest.Server
	requests    []http.Request
	addCalls    int
	addFails    bool
	loginCookie string
}

func newFakeQBittorrent() *fakeQBittorrent {
	fq := &fakeQBittorrent{loginCookie: "QBT_SID_7185=abc123"}
	fq.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fq.requests = append(fq.requests, *r.Clone(r.Context()))

		switch r.URL.Path {
		case "/api/v2/auth/login":
			w.Header().Set("Set-Cookie", fq.loginCookie)
			w.WriteHeader(http.StatusNoContent)
		case "/api/v2/torrents/add":
			fq.addCalls++
			if fq.addFails {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte("Fails."))
				return
			}
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"success_count":1}`))
		case "/api/v2/app/version":
			_, _ = w.Write([]byte("v5.2.3"))
		default:
			_, _ = io.Copy(io.Discard, r.Body)
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("proxied"))
		}
	}))
	return fq
}

func (f *fakeQBittorrent) URL() string {
	return f.server.URL
}

func (f *fakeQBittorrent) Close() {
	f.server.Close()
}

func TestProxyHealth(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrent()
	defer qbit.Close()

	r := NewProxyRouter(qbit.URL(), "admin", "admin")
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Body.String(), "download-proxy")
}

func TestProxyForwardRoot(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrent()
	defer qbit.Close()

	r := NewProxyRouter(qbit.URL(), "admin", "admin")
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	// Supply an existing session cookie so the proxy does not need to log in.
	req.Header.Set("Cookie", "SID=existing")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "proxied", w.Body.String())
	require.Len(t, qbit.requests, 1)
	assert.Equal(t, "/", qbit.requests[0].URL.Path)
}

func TestProxyForwardAuthPassthrough(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrent()
	defer qbit.Close()

	r := NewProxyRouter(qbit.URL(), "admin", "admin")
	req := httptest.NewRequest(http.MethodGet, "/api/v2/sync/maindata", nil)
	req.Header.Set("X-Requested-With", "XMLHttpRequest")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// Without a client cookie the proxy first logs in, then forwards the request.
	require.GreaterOrEqual(t, len(qbit.requests), 2)
	var forwarded *http.Request
	for i := range qbit.requests {
		if qbit.requests[i].URL.Path == "/api/v2/sync/maindata" {
			forwarded = &qbit.requests[i]
			break
		}
	}
	require.NotNil(t, forwarded, "forwarded request not found")
	// When the client supplies no Cookie header, the proxy should have logged
	// in and attached a QBT_SID cookie.
	assert.Contains(t, forwarded.Header.Get("Cookie"), "QBT_SID")
	assert.Equal(t, "XMLHttpRequest", forwarded.Header.Get("X-Requested-With"))
}

func TestProxyDownload_MagnetAccepts(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrent()
	defer qbit.Close()

	r := NewProxyRouter(qbit.URL(), "admin", "admin")
	payload, _ := json.Marshal(ProxyDownloadRequest{URL: "magnet:?xt=urn:btih:abc"})
	req := httptest.NewRequest(http.MethodPost, "/download", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Body.String(), `"success":true`)
	assert.Equal(t, 1, qbit.addCalls)
}

func TestProxyDownload_FetchAndUploadAccepts(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrent()
	defer qbit.Close()

	tracker := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/x-bittorrent")
		_, _ = w.Write([]byte("d8:announce"))
	}))
	defer tracker.Close()

	r := NewProxyRouter(qbit.URL(), "admin", "admin")
	payload, _ := json.Marshal(ProxyDownloadRequest{URL: tracker.URL + "/dl.php?t=1"})
	req := httptest.NewRequest(http.MethodPost, "/download", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Body.String(), `"success":true`)
	assert.Equal(t, 1, qbit.addCalls)
}

func TestProxyDownload_FetchFailure(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrent()
	defer qbit.Close()

	r := NewProxyRouter(qbit.URL(), "admin", "admin")
	payload, _ := json.Marshal(ProxyDownloadRequest{URL: "http://127.0.0.1:1/no"})
	req := httptest.NewRequest(http.MethodPost, "/download", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusBadGateway, w.Code)
	assert.Contains(t, w.Body.String(), `"success":false`)
	assert.Equal(t, 0, qbit.addCalls)
}

func TestProxyDownload_QBittorrentRejects(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrent()
	qbit.addFails = true
	defer qbit.Close()

	tracker := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("d8:announce"))
	}))
	defer tracker.Close()

	r := NewProxyRouter(qbit.URL(), "admin", "admin")
	payload, _ := json.Marshal(ProxyDownloadRequest{URL: tracker.URL + "/x.torrent"})
	req := httptest.NewRequest(http.MethodPost, "/download", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusBadGateway, w.Code)
	assert.Contains(t, w.Body.String(), `"success":false`)
	assert.Equal(t, 1, qbit.addCalls)
}

func TestProxyDownload_MissingURL(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrent()
	defer qbit.Close()

	r := NewProxyRouter(qbit.URL(), "admin", "admin")
	payload := []byte(`{"cookies":"x"}`)
	req := httptest.NewRequest(http.MethodPost, "/download", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusBadRequest, w.Code)
}

func TestProxyDownload_CookiesAndBasicAuthForwarded(t *testing.T) {
	gin.SetMode(gin.TestMode)
	qbit := newFakeQBittorrent()
	defer qbit.Close()

	var receivedCookie, receivedAuth string
	tracker := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedCookie = r.Header.Get("Cookie")
		receivedAuth = r.Header.Get("Authorization")
		_, _ = w.Write([]byte("d8:announce"))
	}))
	defer tracker.Close()

	r := NewProxyRouter(qbit.URL(), "admin", "admin")
	payload, _ := json.Marshal(ProxyDownloadRequest{
		URL:      tracker.URL + "/x.torrent",
		Cookies:  "session=secret",
		Username: "user",
		Password: "pass",
	})
	req := httptest.NewRequest(http.MethodPost, "/download", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "session=secret", receivedCookie)
	assert.True(t, strings.HasPrefix(receivedAuth, "Basic "), "basic auth should be forwarded")
}

func TestQbitAddSucceeded(t *testing.T) {
	assert.True(t, qbitAddSucceeded(http.StatusOK, `{"success_count":1}`))
	assert.True(t, qbitAddSucceeded(http.StatusAccepted, `{"pending_count":1}`))
	assert.True(t, qbitAddSucceeded(http.StatusConflict, ""))
	assert.True(t, qbitAddSucceeded(http.StatusOK, "Ok."))
	assert.False(t, qbitAddSucceeded(http.StatusBadRequest, ""))
	assert.False(t, qbitAddSucceeded(http.StatusOK, "Fails."))
}
