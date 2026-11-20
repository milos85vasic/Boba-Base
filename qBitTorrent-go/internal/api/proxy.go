package api

import (
	"bytes"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/httpx"
)

// ProxyDownloadRequest is the body expected by the :7186 /download endpoint.
// It carries a tracker download URL plus optional authentication material.
type ProxyDownloadRequest struct {
	URL      string `json:"url" binding:"required"`
	Cookies  string `json:"cookies,omitempty"`
	Username string `json:"username,omitempty"`
	Password string `json:"password,omitempty"`
}

// ProxyDownloadResponse reports the result of a backend fetch-and-add.
type ProxyDownloadResponse struct {
	Success bool   `json:"success"`
	URL     string `json:"url"`
	Method  string `json:"method"`
	Detail  string `json:"detail,omitempty"`
}

// NewProxyRouter builds the :7186 download-proxy surface.
//
//   * Most paths are reverse-proxied to qBittorrent with admin/admin auth
//     passthrough and same-origin header hygiene.
//   * POST /download fetches a .torrent/magnet on the backend and adds it to
//     qBittorrent via the Web API.
//   * GET /health exposes a liveness probe.
func NewProxyRouter(qbitURL, qbitUser, qbitPass string) *gin.Engine {
	r := gin.New()
	r.Use(gin.Recovery())

	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status":  "healthy",
			"service": "download-proxy",
		})
	})

	r.POST("/download", proxyDownloadHandler(qbitURL, qbitUser, qbitPass))

	// Everything else is forwarded byte-for-byte to qBittorrent.
	r.NoRoute(reverseProxyHandler(qbitURL, qbitUser, qbitPass))

	return r
}

func reverseProxyHandler(qbitURL, qbitUser, qbitPass string) gin.HandlerFunc {
	u, err := url.Parse(qbitURL)
	if err != nil {
		u, _ = url.Parse("http://localhost:7185")
	}

	proxy := httputil.NewSingleHostReverseProxy(u)
	proxy.ModifyResponse = func(resp *http.Response) error {
		// Strip hop-by-hop headers that confuse chunked responses.
		resp.Header.Del("Transfer-Encoding")
		return nil
	}

	transport := httpx.NewTransport()
	proxy.Transport = transport

	return func(c *gin.Context) {
		// Pass through the request, rewriting Referer/Origin so qBittorrent's
		// same-origin check accepts browser traffic that arrived through :7186.
		for k, v := range c.Request.Header {
			kl := strings.ToLower(k)
			if kl == "host" || kl == "content-length" {
				continue
			}
			if kl == "referer" || kl == "origin" {
				c.Request.Header.Set(k, u.String())
				continue
			}
			for _, val := range v {
				c.Request.Header.Add(k, val)
			}
		}

		// Authenticate to qBittorrent as the configured admin account if the
		// client did not already supply a session cookie.
		if _, hasCookie := c.Request.Header["Cookie"]; !hasCookie && qbitUser != "" {
			session, err := qbittorrentLogin(u.String(), qbitUser, qbitPass)
			if err == nil && session != "" {
				c.Request.Header.Set("Cookie", session)
			}
		}

		c.Request.Host = u.Host
		c.Request.URL.Scheme = u.Scheme
		c.Request.URL.Host = u.Host

		proxy.ServeHTTP(httpx.NewCloseNotifierWriter(c.Writer), c.Request)
	}
}

func proxyDownloadHandler(qbitURL, qbitUser, qbitPass string) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req ProxyDownloadRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		if strings.HasPrefix(strings.ToLower(req.URL), "magnet:") {
			err := addURLToQBittorrent(qbitURL, qbitUser, qbitPass, req.URL, "")
			if err != nil {
				c.JSON(http.StatusBadGateway, ProxyDownloadResponse{
					Success: false,
					URL:     req.URL,
					Method:  "magnet",
					Detail:  err.Error(),
				})
				return
			}
			c.JSON(http.StatusOK, ProxyDownloadResponse{
				Success: true,
				URL:     req.URL,
				Method:  "magnet",
			})
			return
		}

		data, contentType, err := fetchTorrentBytes(req.URL, req.Cookies, req.Username, req.Password)
		if err != nil {
			c.JSON(http.StatusBadGateway, ProxyDownloadResponse{
				Success: false,
				URL:     req.URL,
				Method:  "fetch",
				Detail:  err.Error(),
			})
			return
		}

		filename := "torrent.torrent"
		if lastSlash := strings.LastIndex(req.URL, "/"); lastSlash != -1 && lastSlash < len(req.URL)-1 {
			candidate := req.URL[lastSlash+1:]
			if candidate != "" && !strings.Contains(candidate, "?") {
				filename = candidate
			}
		}

		if err := uploadTorrentToQBittorrent(qbitURL, qbitUser, qbitPass, filename, data, contentType); err != nil {
			c.JSON(http.StatusBadGateway, ProxyDownloadResponse{
				Success: false,
				URL:     req.URL,
				Method:  "upload",
				Detail:  err.Error(),
			})
			return
		}

		c.JSON(http.StatusOK, ProxyDownloadResponse{
			Success: true,
			URL:     req.URL,
			Method:  "file",
		})
	}
}

func fetchTorrentBytes(rawURL, cookies, username, password string) ([]byte, string, error) {
	req, err := http.NewRequest(http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, "", err
	}
	if cookies != "" {
		req.Header.Set("Cookie", cookies)
	}
	if username != "" || password != "" {
		req.SetBasicAuth(username, password)
	}
	req.Header.Set("User-Agent", "qBittorrent/5.0")

	client := &http.Client{Timeout: 60 * time.Second, Transport: httpx.NewTransport()}
	resp, err := client.Do(req)
	if err != nil {
		return nil, "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, "", fmt.Errorf("upstream returned HTTP %d", resp.StatusCode)
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, "", err
	}
	return data, resp.Header.Get("Content-Type"), nil
}

func uploadTorrentToQBittorrent(qbitURL, qbitUser, qbitPass, filename string, data []byte, contentType string) error {
	session, err := qbittorrentLogin(qbitURL, qbitUser, qbitPass)
	if err != nil {
		return fmt.Errorf("qBittorrent login failed: %w", err)
	}

	var buf bytes.Buffer
	writer := multipart.NewWriter(&buf)
	part, err := writer.CreateFormFile("torrents", filename)
	if err != nil {
		return err
	}
	if _, err := part.Write(data); err != nil {
		return err
	}
	writer.Close()

	req, err := http.NewRequest(http.MethodPost, qbitURL+"/api/v2/torrents/add", &buf)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	req.Header.Set("Cookie", session)
	req.Header.Set("Referer", qbitURL)

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if !qbitAddSucceeded(resp.StatusCode, string(body)) {
		return fmt.Errorf("qBittorrent rejected add: HTTP %d: %s", resp.StatusCode, string(body))
	}
	return nil
}

func addURLToQBittorrent(qbitURL, qbitUser, qbitPass, rawURL, _ string) error {
	session, err := qbittorrentLogin(qbitURL, qbitUser, qbitPass)
	if err != nil {
		return fmt.Errorf("qBittorrent login failed: %w", err)
	}

	data := url.Values{}
	data.Set("urls", rawURL)

	req, err := http.NewRequest(http.MethodPost, qbitURL+"/api/v2/torrents/add", strings.NewReader(data.Encode()))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Cookie", session)
	req.Header.Set("Referer", qbitURL)

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if !qbitAddSucceeded(resp.StatusCode, string(body)) {
		return fmt.Errorf("qBittorrent rejected add: HTTP %d: %s", resp.StatusCode, string(body))
	}
	return nil
}

func qbittorrentLogin(qbitURL, username, password string) (string, error) {
	data := url.Values{}
	data.Set("username", username)
	data.Set("password", password)

	req, err := http.NewRequest(http.MethodPost, qbitURL+"/api/v2/auth/login", strings.NewReader(data.Encode()))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Referer", qbitURL)

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		return "", fmt.Errorf("login failed: HTTP %d", resp.StatusCode)
	}

	for _, cookie := range resp.Cookies() {
		if cookie.Name == "SID" || strings.HasPrefix(cookie.Name, "QBT_SID") {
			return fmt.Sprintf("%s=%s", cookie.Name, cookie.Value), nil
		}
	}
	return "", fmt.Errorf("login returned no session cookie")
}

// qbitAddSucceeded mirrors the measured qBittorrent add contract documented in
// download-proxy/src/merge_service/qbit_add.py. It is duplicated here in a
// minimal form so the :7186 proxy can decide whether a fetch-and-add really
// landed without importing Python code.
func qbitAddSucceeded(status int, body string) bool {
	if status == 409 {
		return true
	}
	if status != 200 && status != 201 && status != 202 {
		return false
	}
	text := strings.TrimSpace(body)
	if strings.HasPrefix(text, "Ok.") || strings.HasPrefix(text, "ok") {
		return true
	}
	if strings.EqualFold(text, "Fails.") {
		return false
	}
	return true
}
