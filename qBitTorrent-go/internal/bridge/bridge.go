package bridge

import (
	"bytes"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/httpx"
)

// PrivateTrackerDomains mirrors download-proxy/src/merge_service/trackers.py
// so the bridge can identify which URLs need authenticated download without
// importing Python code. The list must be kept in sync with the Python roster.
var PrivateTrackerDomains = map[string][]string{
	"rutracker":  {"rutracker.org", "rutracker.net", "rutracker.nl"},
	"kinozal":    {"kinozal.tv", "kinozal.me", "kinozal.guru"},
	"nnmclub":    {"nnmclub.to", "nnmclub.ro", "nnm-club.me"},
	"iptorrents": {"iptorrents.com", "iptorrents.me", "iptorrents.org"},
}

// Config holds the runtime dependencies of the WebUI bridge.
type Config struct {
	QBittorrentURL      string
	QBittorrentUsername string
	QBittorrentPassword string
	Port                int
	Nova2DLPath         string
}

// DefaultConfig builds a Config from the same environment variables used by
// the Python bridge and the Go merge service.
func DefaultConfig() *Config {
	qbitURL := resolveQBittorrentURL()
	return &Config{
		QBittorrentURL:      qbitURL,
		QBittorrentUsername: getEnv("QBITTORRENT_USER", getEnv("QBITTORRENT_USERNAME", "admin")),
		QBittorrentPassword: getEnv("QBITTORRENT_PASS", getEnv("QBITTORRENT_PASSWORD", "admin")),
		Port:                getEnvInt("BRIDGE_PORT", 7188),
		Nova2DLPath:         getEnv("NOVA2DL_PATH", "/config/qBittorrent/nova3/nova2dl.py"),
	}
}

func resolveQBittorrentURL() string {
	if explicit := getEnv("BRIDGE_QBIT_URL", getEnv("QBITTORRENT_URL", "")); explicit != "" {
		return strings.TrimRight(explicit, "/")
	}
	host := getEnv("QBITTORRENT_HOST", "localhost")
	port := getEnvInt("QBITTORRENT_PORT", 7186)
	return fmt.Sprintf("http://%s:%d", host, port)
}

func getEnv(key, fallback string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	v, ok := os.LookupEnv(key)
	if !ok {
		return fallback
	}
	var out int
	if _, err := fmt.Sscanf(v, "%d", &out); err != nil {
		return fallback
	}
	return out
}

// NewRouter builds the WebUI bridge HTTP surface.
func NewRouter(cfg *Config) *gin.Engine {
	r := gin.New()
	r.Use(gin.Recovery())

	r.GET("/health", func(c *gin.Context) {
		backend := "unknown"
		if status, err := probeQBittorrent(cfg.QBittorrentURL); err == nil {
			backend = status
		} else {
			backend = fmt.Sprintf("unreachable:%s", err)
		}
		overall := "healthy"
		if backend != "ok" {
			overall = "degraded"
		}
		c.JSON(http.StatusOK, gin.H{
			"status":  overall,
			"service": "webui-bridge",
			"backend": backend,
		})
	})

	r.GET("/bridge/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	r.GET("/", bridgeHandler(cfg))
	r.POST("/", bridgeHandler(cfg))
	r.NoRoute(bridgeHandler(cfg))

	return r
}

func bridgeHandler(cfg *Config) gin.HandlerFunc {
	u, err := url.Parse(cfg.QBittorrentURL)
	if err != nil {
		u, _ = url.Parse("http://localhost:7186")
	}

	proxy := httputil.NewSingleHostReverseProxy(u)
	proxy.ModifyResponse = func(resp *http.Response) error {
		resp.Header.Del("Transfer-Encoding")
		return nil
	}

	return func(c *gin.Context) {
		// Intercept WebUI "add by URL" requests.
		if c.Request.Method == http.MethodGet || c.Request.Method == http.MethodPost {
			if urls := c.Query("urls"); urls != "" {
				if tracker := identifyTrackerInText(urls); tracker != "" {
					handlePrivateTorrentDownload(c, cfg, tracker, urls)
					return
				}
			}
		}

		// Not a private-tracker download: proxy to qBittorrent.
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

		c.Request.Host = u.Host
		c.Request.URL.Scheme = u.Scheme
		c.Request.URL.Host = u.Host

		proxy.ServeHTTP(httpx.NewCloseNotifierWriter(c.Writer), c.Request)
	}
}

func handlePrivateTorrentDownload(c *gin.Context, cfg *Config, tracker, rawURL string) {
	torrentFile, err := downloadViaNova2DL(cfg.Nova2DLPath, tracker, rawURL)
	if err != nil {
		// Fall back to transparent proxy so the WebUI can still try its own path.
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	defer os.Remove(torrentFile)

	data, err := os.ReadFile(torrentFile)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if err := uploadTorrentToQBittorrent(cfg, filepath.Base(torrentFile), data); err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}

	c.String(http.StatusOK, "OK")
}

func downloadViaNova2DL(nova2dlPath, tracker, rawURL string) (string, error) {
	if _, err := os.Stat(nova2dlPath); err != nil {
		return "", fmt.Errorf("nova2dl not found at %s", nova2dlPath)
	}

	cmd := exec.Command("python3", nova2dlPath, tracker, rawURL)
	cmd.Stderr = os.Stderr
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("nova2dl failed: %w", err)
	}

	parts := strings.Fields(strings.TrimSpace(string(out)))
	if len(parts) < 2 {
		return "", fmt.Errorf("nova2dl returned unexpected output: %q", string(out))
	}
	torrentPath := parts[0]
	if _, err := os.Stat(torrentPath); err != nil {
		return "", fmt.Errorf("torrent file not found after download: %s", torrentPath)
	}
	return torrentPath, nil
}

func uploadTorrentToQBittorrent(cfg *Config, filename string, data []byte) error {
	session, err := qbittorrentLogin(cfg.QBittorrentURL, cfg.QBittorrentUsername, cfg.QBittorrentPassword)
	if err != nil {
		return err
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

	req, err := http.NewRequest(http.MethodPost, cfg.QBittorrentURL+"/api/v2/torrents/add", &buf)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	req.Header.Set("Cookie", session)
	req.Header.Set("Referer", cfg.QBittorrentURL)

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

func probeQBittorrent(qbitURL string) (string, error) {
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get(qbitURL + "/api/v2/app/version")
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 500 {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return "ok", nil
}

// identifyTrackerInText uses substring matching, matching the Python bridge's
// historical behaviour for WebUI "add by URL" payloads.
func identifyTrackerInText(text string) string {
	lowered := strings.ToLower(text)
	for name, domains := range PrivateTrackerDomains {
		for _, domain := range domains {
			if strings.Contains(lowered, domain) {
				return name
			}
		}
	}
	return ""
}

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
	return true
}
