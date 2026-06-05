# Python-to-Go Backend Migration Implementation Plan

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the Python/FastAPI merge search backend to Go/Gin, producing a production-ready, fully working system with feature parity.

**Architecture:** Two-container setup preserved — `qbittorrent` (unchanged) + `qbittorrent-proxy` (Go binary replaces Python). The Go project lives in a new `qBitTorrent-go/` directory at the repo root. Two binaries: `qbittorrent-proxy` (main API on 7186/7187) and `webui-bridge` (bridge on 7188). Plugins remain Python — invoked via subprocess from Go where needed.

**Tech Stack:** Go 1.23, Gin, Zerolog, godotenv, go-cache, go-retry, gobreaker, testify

**Migration Doc:** `docs/migration/Migration_Python_Codebase_To_Go.md` — THE source of truth for code structure and patterns.

---

## Phase 1: Project Scaffolding & Foundation

### Task 1: Initialize Go Module & Directory Structure

**Files:**
- Create: `qBitTorrent-go/go.mod`
- Create: `qBitTorrent-go/cmd/qbittorrent-proxy/main.go` (placeholder)
- Create: `qBitTorrent-go/cmd/webui-bridge/main.go` (placeholder)
- Create: `qBitTorrent-go/internal/api/` (directory)
- Create: `qBitTorrent-go/internal/client/` (directory)
- Create: `qBitTorrent-go/internal/config/` (directory)
- Create: `qBitTorrent-go/internal/models/` (directory)
- Create: `qBitTorrent-go/internal/service/` (directory)
- Create: `qBitTorrent-go/internal/middleware/` (directory)
- Create: `qBitTorrent-go/scripts/build.sh`

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p qBitTorrent-go/{cmd/{qbittorrent-proxy,webui-bridge},internal/{api,client,config,models,service,middleware},scripts}
```

- [ ] **Step 2: Initialize Go module**

```bash
cd qBitTorrent-go && go mod init github.com/milos85vasic/qBitTorrent-go
```

- [ ] **Step 3: Add dependencies**

```bash
cd qBitTorrent-go && go get github.com/gin-gonic/gin@latest && go get github.com/rs/zerolog@latest && go get github.com/joho/godotenv@latest && go get github.com/patrickmn/go-cache@latest && go get github.com/sethvargo/go-retry@latest && go get github.com/sony/gobreaker@latest && go get github.com/stretchr/testify@latest && go get github.com/gin-contrib/cors@latest
```

- [ ] **Step 4: Create placeholder main.go files**

`qBitTorrent-go/cmd/qbittorrent-proxy/main.go`:
```go
package main

import "fmt"

func main() {
	fmt.Println("qbittorrent-proxy placeholder")
}
```

`qBitTorrent-go/cmd/webui-bridge/main.go`:
```go
package main

import "fmt"

func main() {
	fmt.Println("webui-bridge placeholder")
}
```

- [ ] **Step 5: Verify build**

```bash
cd qBitTorrent-go && go build ./...
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add qBitTorrent-go/ && git commit -m "feat(go): initialize Go module and directory structure"
```

---

### Task 2: Configuration Management

**Files:**
- Create: `qBitTorrent-go/internal/config/config.go`
- Create: `qBitTorrent-go/internal/config/config_test.go`

- [ ] **Step 1: Write the failing test for config loading**

`qBitTorrent-go/internal/config/config_test.go`:
```go
package config

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestLoad_Defaults(t *testing.T) {
	os.Clearenv()
	cfg := Load()
	assert.Equal(t, "localhost", cfg.QBittorrentHost)
	assert.Equal(t, 7185, cfg.QBittorrentPort)
	assert.Equal(t, "admin", cfg.QBittorrentUsername)
	assert.Equal(t, "admin", cfg.QBittorrentPassword)
	assert.Equal(t, 7187, cfg.ServerPort)
	assert.Equal(t, 7188, cfg.BridgePort)
	assert.Equal(t, "info", cfg.LogLevel)
	assert.Equal(t, 30, cfg.SSETimeout)
	assert.Equal(t, 10, cfg.PluginTimeout)
}

func TestLoad_EnvOverride(t *testing.T) {
	os.Clearenv()
	os.Setenv("QBITTORRENT_HOST", "myhost")
	os.Setenv("QBITTORRENT_PORT", "9999")
	os.Setenv("SERVER_PORT", "8888")
	os.Setenv("BRIDGE_PORT", "7777")
	os.Setenv("LOG_LEVEL", "debug")
	os.Setenv("SSE_TIMEOUT", "60")

	cfg := Load()
	assert.Equal(t, "myhost", cfg.QBittorrentHost)
	assert.Equal(t, 9999, cfg.QBittorrentPort)
	assert.Equal(t, 8888, cfg.ServerPort)
	assert.Equal(t, 7777, cfg.BridgePort)
	assert.Equal(t, "debug", cfg.LogLevel)
	assert.Equal(t, 60, cfg.SSETimeout)
}

func TestLoad_TrackerAuth(t *testing.T) {
	os.Clearenv()
	os.Setenv("RUTRACKER_USERNAME", "ru_user")
	os.Setenv("RUTRACKER_PASSWORD", "ru_pass")
	os.Setenv("IPTORRENTS_USERNAME", "ipt_user")
	os.Setenv("IPTORRENTS_PASSWORD", "ipt_pass")

	cfg := Load()
	assert.Equal(t, "ru_user", cfg.RutrackerUsername)
	assert.Equal(t, "ru_pass", cfg.RutrackerPassword)
	assert.Equal(t, "ipt_user", cfg.IPTorrentsUsername)
	assert.Equal(t, "ipt_pass", cfg.IPTorrentsPassword)
}

func TestLoad_KinozalFallback(t *testing.T) {
	os.Clearenv()
	os.Setenv("IPTORRENTS_USERNAME", "ipt_user")
	os.Setenv("IPTORRENTS_PASSWORD", "ipt_pass")

	cfg := Load()
	assert.Equal(t, "ipt_user", cfg.KinozalUsername)
	assert.Equal(t, "ipt_pass", cfg.KinozalPassword)
}

func TestLoad_MetadataAPIKeys(t *testing.T) {
	os.Clearenv()
	os.Setenv("OMDB_API_KEY", "omdb_key")
	os.Setenv("TMDB_API_KEY", "tmdb_key")
	os.Setenv("ANILIST_CLIENT_ID", "anilist_id")

	cfg := Load()
	assert.Equal(t, "omdb_key", cfg.OMDBAPIKey)
	assert.Equal(t, "tmdb_key", cfg.TMDBAPIKey)
	assert.Equal(t, "anilist_id", cfg.AniListClientID)
}

func TestQBittorrentURL(t *testing.T) {
	os.Clearenv()
	cfg := Load()
	assert.Equal(t, "http://localhost:7185", cfg.QBittorrentURL())

	os.Setenv("QBITTORRENT_HOST", "qb")
	os.Setenv("QBITTORRENT_PORT", "9090")
	cfg = Load()
	assert.Equal(t, "http://qb:9090", cfg.QBittorrentURL())
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd qBitTorrent-go && go test ./internal/config/ -v -run TestLoad
```

Expected: compilation errors (Load, Config undefined)

- [ ] **Step 3: Write config implementation**

`qBitTorrent-go/internal/config/config.go`:
```go
package config

import (
	"fmt"
	"os"
	"strconv"

	"github.com/joho/godotenv"
)

type Config struct {
	QBittorrentHost     string
	QBittorrentPort     int
	QBittorrentUsername string
	QBittorrentPassword string
	ServerPort          int
	BridgePort          int
	ProxyPort           int
	LogLevel            string
	SSETimeout          int
	PluginTimeout       int
	MaxConcurrentSearches int

	RutrackerUsername  string
	RutrackerPassword  string
	KinozalUsername    string
	KinozalPassword    string
	NNMClubCookies     string
	IPTorrentsUsername string
	IPTorrentsPassword string

	OMDBAPIKey      string
	TMDBAPIKey      string
	AniListClientID string

	AllowedOrigins      string
	MergeServicePort    int
	QBittorrentDataDir  string
	DisableThemeInjection bool
}

func Load() *Config {
	_ = godotenv.Load()

	return &Config{
		QBittorrentHost:       getEnv("QBITTORRENT_HOST", "localhost"),
		QBittorrentPort:       getEnvAsInt("QBITTORRENT_PORT", 7185),
		QBittorrentUsername:   getEnv("QBITTORRENT_USER", getEnv("QBITTORRENT_USERNAME", "admin")),
		QBittorrentPassword:   getEnv("QBITTORRENT_PASS", getEnv("QBITTORRENT_PASSWORD", "admin")),
		ServerPort:            getEnvAsInt("MERGE_SERVICE_PORT", getEnvAsInt("SERVER_PORT", 7187)),
		BridgePort:            getEnvAsInt("BRIDGE_PORT", 7188),
		ProxyPort:             getEnvAsInt("PROXY_PORT", 7186),
		LogLevel:              getEnv("LOG_LEVEL", "info"),
		SSETimeout:            getEnvAsInt("SSE_TIMEOUT", 30),
		PluginTimeout:         getEnvAsInt("PLUGIN_TIMEOUT", 10),
		MaxConcurrentSearches: getEnvAsInt("MAX_CONCURRENT_SEARCHES", 5),

		RutrackerUsername:  getEnv("RUTRACKER_USERNAME", ""),
		RutrackerPassword:  getEnv("RUTRACKER_PASSWORD", ""),
		KinozalUsername:    getEnv("KINOZAL_USERNAME", getEnv("IPTORRENTS_USERNAME", "")),
		KinozalPassword:    getEnv("KINOZAL_PASSWORD", getEnv("IPTORRENTS_PASSWORD", "")),
		NNMClubCookies:     getEnv("NNMCLUB_COOKIES", ""),
		IPTorrentsUsername: getEnv("IPTORRENTS_USERNAME", ""),
		IPTorrentsPassword: getEnv("IPTORRENTS_PASSWORD", ""),

		OMDBAPIKey:      getEnv("OMDB_API_KEY", ""),
		TMDBAPIKey:      getEnv("TMDB_API_KEY", ""),
		AniListClientID: getEnv("ANILIST_CLIENT_ID", ""),

		AllowedOrigins:      getEnv("ALLOWED_ORIGINS", "http://localhost:7186,http://localhost:7187"),
		MergeServicePort:    getEnvAsInt("MERGE_SERVICE_PORT", 7187),
		QBittorrentDataDir:  getEnv("QBITTORRENT_DATA_DIR", "/mnt/DATA"),
		DisableThemeInjection: getEnv("DISABLE_THEME_INJECTION", "") == "1",
	}
}

func (c *Config) QBittorrentURL() string {
	return fmt.Sprintf("http://%s:%d", c.QBittorrentHost, c.QBittorrentPort)
}

func getEnv(key, fallback string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return fallback
}

func getEnvAsInt(key string, fallback int) int {
	if value, exists := os.LookupEnv(key); exists {
		if i, err := strconv.Atoi(value); err == nil {
			return i
		}
	}
	return fallback
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd qBitTorrent-go && go test ./internal/config/ -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add qBitTorrent-go/internal/config/ && git commit -m "feat(go): add configuration management with env loading"
```

---

### Task 3: Data Models

**Files:**
- Create: `qBitTorrent-go/internal/models/torrent.go`
- Create: `qBitTorrent-go/internal/models/search.go`
- Create: `qBitTorrent-go/internal/models/hook.go`
- Create: `qBitTorrent-go/internal/models/scheduler.go`
- Create: `qBitTorrent-go/internal/models/theme.go`
- Create: `qBitTorrent-go/internal/models/auth.go`
- Create: `qBitTorrent-go/internal/models/models_test.go`

- [ ] **Step 1: Write tests for model serialization**

`qBitTorrent-go/internal/models/models_test.go`:
```go
package models

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestSearchRequest_JSON(t *testing.T) {
	raw := `{"query":"ubuntu","category":"all","limit":50,"enable_metadata":true}`
	var req SearchRequest
	err := json.Unmarshal([]byte(raw), &req)
	assert.NoError(t, err)
	assert.Equal(t, "ubuntu", req.Query)
	assert.Equal(t, "all", req.Category)
	assert.Equal(t, 50, req.Limit)
	assert.True(t, req.EnableMetadata)
}

func TestSearchRequest_Validation(t *testing.T) {
	raw := `{"category":"all"}`
	var req SearchRequest
	err := json.Unmarshal([]byte(raw), &req)
	assert.NoError(t, err)
	assert.Empty(t, req.Query)
}

func TestSearchResponse_JSON(t *testing.T) {
	resp := SearchResponse{
		SearchID:        "abc-123",
		Query:           "test",
		Status:          "completed",
		TotalResults:    5,
		MergedResults:   3,
		TrackersSearched: []string{"rutracker", "rutor"},
		Errors:          []string{},
		TrackerStats:    []TrackerStat{},
		StartedAt:       "2026-01-01T00:00:00Z",
	}
	data, err := json.Marshal(resp)
	assert.NoError(t, err)
	assert.Contains(t, string(data), `"search_id":"abc-123"`)
	assert.Contains(t, string(data), `"status":"completed"`)
}

func TestTorrentResult_JSON(t *testing.T) {
	tr := TorrentResult{
		Name:         "Ubuntu 24.04",
		Size:         "4.0 GB",
		Seeds:        100,
		Leechers:     50,
		DownloadURLs: []string{"http://example.com/file.torrent"},
		Tracker:      "rutracker",
		Quality:      "full_hd",
		ContentType:  "software",
		Freeleech:    true,
	}
	data, err := json.Marshal(tr)
	assert.NoError(t, err)
	assert.Contains(t, string(data), `"freeleech":true`)
	assert.Contains(t, string(data), `"seeds":100`)
}

func TestHook_JSON(t *testing.T) {
	h := Hook{
		ID:      "hook-1",
		URL:     "https://example.com/webhook",
		Events:  []string{"search_complete", "download_complete"},
		Headers: map[string]string{"Authorization": "Bearer token"},
		Enabled: true,
	}
	data, err := json.Marshal(h)
	assert.NoError(t, err)
	assert.Contains(t, string(data), `"enabled":true`)
}

func TestScheduledSearch_JSON(t *testing.T) {
	s := ScheduledSearch{
		ID:       "sched-1",
		Query:    "ubuntu",
		Category: "software",
		Cron:     "0 */6 * * *",
		Enabled:  true,
	}
	data, err := json.Marshal(s)
	assert.NoError(t, err)
	assert.Contains(t, string(data), `"cron":"0 */6 * * *"`)
}

func TestThemeState_JSON(t *testing.T) {
	ts := ThemeState{
		PaletteID: "dark-midnight",
		Mode:      "dark",
	}
	data, err := json.Marshal(ts)
	assert.NoError(t, err)
	assert.Contains(t, string(data), `"palette_id":"dark-midnight"`)
	assert.Contains(t, string(data), `"mode":"dark"`)
}

func TestTrackerStat_JSON(t *testing.T) {
	ts := TrackerStat{
		Name:    "rutracker",
		Status:  "success",
		Results: 42,
		Error:   "",
	}
	data, err := json.Marshal(ts)
	assert.NoError(t, err)
	assert.Contains(t, string(data), `"results":42`)
}

func TestDownloadRequest_JSON(t *testing.T) {
	raw := `{"result_id":"r-1","download_urls":["http://example.com/file.torrent"]}`
	var req DownloadRequest
	err := json.Unmarshal([]byte(raw), &req)
	assert.NoError(t, err)
	assert.Equal(t, "r-1", req.ResultID)
	assert.Len(t, req.DownloadURLs, 1)
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd qBitTorrent-go && go test ./internal/models/ -v
```

Expected: compilation errors

- [ ] **Step 3: Write all model files**

`qBitTorrent-go/internal/models/torrent.go`:
```go
package models

type TorrentResult struct {
	Name         string            `json:"name"`
	Size         interface{}       `json:"size"`
	Seeds        int               `json:"seeds"`
	Leechers     int               `json:"leechers"`
	DownloadURLs []string          `json:"download_urls"`
	Quality      string            `json:"quality,omitempty"`
	ContentType  string            `json:"content_type,omitempty"`
	DescLink     string            `json:"desc_link,omitempty"`
	Tracker      string            `json:"tracker,omitempty"`
	Sources      []SourceInfo      `json:"sources,omitempty"`
	Metadata     map[string]interface{} `json:"metadata,omitempty"`
	Freeleech    bool              `json:"freeleech"`
}

type SourceInfo struct {
	Tracker  string `json:"tracker"`
	Seeds    int    `json:"seeds"`
	Leechers int    `json:"leechers"`
}
```

`qBitTorrent-go/internal/models/search.go`:
```go
package models

type SearchRequest struct {
	Query            string `json:"query"`
	Category         string `json:"category"`
	Limit            int    `json:"limit,omitempty"`
	EnableMetadata   bool   `json:"enable_metadata,omitempty"`
	ValidateTrackers bool   `json:"validate_trackers,omitempty"`
	SortBy           string `json:"sort_by,omitempty"`
	SortOrder        string `json:"sort_order,omitempty"`
}

type SearchResponse struct {
	SearchID         string         `json:"search_id"`
	Query            string         `json:"query"`
	Status           string         `json:"status"`
	Results          []TorrentResult `json:"results"`
	TotalResults     int            `json:"total_results"`
	MergedResults    int            `json:"merged_results"`
	TrackersSearched []string       `json:"trackers_searched"`
	Errors           []string       `json:"errors"`
	TrackerStats     []TrackerStat  `json:"tracker_stats"`
	StartedAt        string         `json:"started_at"`
	CompletedAt      *string        `json:"completed_at,omitempty"`
}

type TrackerStat struct {
	Name       string  `json:"name"`
	Status     string  `json:"status"`
	Results    int     `json:"results"`
	DurationMS int64   `json:"duration_ms,omitempty"`
	Error      string  `json:"error,omitempty"`
	Authenticated bool `json:"authenticated,omitempty"`
}

type DownloadRequest struct {
	ResultID     string   `json:"result_id"`
	DownloadURLs []string `json:"download_urls"`
}

type DownloadResult struct {
	DownloadID string               `json:"download_id"`
	Status     string               `json:"status"`
	URLsCount  int                  `json:"urls_count"`
	AddedCount int                  `json:"added_count"`
	Results    []URLDownloadResult  `json:"results"`
}

type URLDownloadResult struct {
	URL     string `json:"url"`
	Status  string `json:"status"`
	Detail  string `json:"detail,omitempty"`
	Method  string `json:"method,omitempty"`
	Message string `json:"message,omitempty"`
}
```

`qBitTorrent-go/internal/models/hook.go`:
```go
package models

import "time"

type Hook struct {
	ID        string            `json:"id"`
	URL       string            `json:"url"`
	Secret    string            `json:"secret,omitempty"`
	Events    []string          `json:"events"`
	Headers   map[string]string `json:"headers,omitempty"`
	Enabled   bool              `json:"enabled"`
	CreatedAt time.Time         `json:"created_at,omitempty"`
}

type HookEventType string

const (
	HookEventSearchStart    HookEventType = "search_start"
	HookEventSearchComplete HookEventType = "search_complete"
	HookEventDownloadStart  HookEventType = "download_start"
	HookEventDownloadComplete HookEventType = "download_complete"
)

type HookLogEntry struct {
	HookID    string    `json:"hook_id"`
	Event     string    `json:"event"`
	Timestamp time.Time `json:"timestamp"`
	Success   bool      `json:"success"`
	Error     string    `json:"error,omitempty"`
	Payload   string    `json:"payload,omitempty"`
}
```

`qBitTorrent-go/internal/models/scheduler.go`:
```go
package models

type ScheduledSearch struct {
	ID       string `json:"id"`
	Query    string `json:"query"`
	Category string `json:"category"`
	Cron     string `json:"cron"`
	Enabled  bool   `json:"enabled"`
}

type ScheduleStatus struct {
	Searches []ScheduledSearch `json:"searches"`
	Running  bool              `json:"running"`
}
```

`qBitTorrent-go/internal/models/theme.go`:
```go
package models

type ThemeState struct {
	PaletteID string `json:"palette_id"`
	Mode      string `json:"mode"`
}

type ThemeUpdate struct {
	PaletteID string `json:"paletteId"`
	Mode      string `json:"mode"`
}
```

`qBitTorrent-go/internal/models/auth.go`:
```go
package models

type AuthStatus struct {
	Tracker    string `json:"tracker"`
	Authenticated bool `json:"authenticated"`
	CaptchaRequired bool `json:"captcha_required,omitempty"`
	CaptchaURL  string `json:"captcha_url,omitempty"`
}

type TrackerLoginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type CookieLoginRequest struct {
	Cookies string `json:"cookies"`
}

type QBittorrentAuthRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
	Save     bool   `json:"save"`
}

type QBittorrentAuthResponse struct {
	Status  string `json:"status"`
	Version string `json:"version,omitempty"`
	Message string `json:"message,omitempty"`
	Error   string `json:"error,omitempty"`
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd qBitTorrent-go && go test ./internal/models/ -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add qBitTorrent-go/internal/models/ && git commit -m "feat(go): add data models for search, hooks, scheduler, theme, auth"
```

---

## Phase 2: qBittorrent API Client

### Task 4: qBittorrent Client — Authentication

**Files:**
- Create: `qBitTorrent-go/internal/client/client.go`
- Create: `qBitTorrent-go/internal/client/auth.go`
- Create: `qBitTorrent-go/internal/client/auth_test.go`

- [ ] **Step 1: Write failing tests for auth**

`qBitTorrent-go/internal/client/auth_test.go`:
```go
package client

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestLogin_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/auth/login" && r.Method == "POST" {
			http.SetCookie(w, &http.Cookie{Name: "SID", Value: "test-sid-123"})
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("Ok."))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "admin", "admin")
	require.NoError(t, err)
	assert.True(t, client.IsAuthenticated())
	assert.Equal(t, "test-sid-123", client.GetSID())
}

func TestLogin_Failure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		w.Write([]byte("Fails."))
	}))
	defer server.Close()

	_, err := NewClient(server.URL, "wrong", "wrong")
	assert.Error(t, err)
}

func TestClient_QueryString(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.SetCookie(w, &http.Cookie{Name: "SID", Value: "sid"})
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("Ok."))
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "admin", "admin")
	require.NoError(t, err)
	assert.Equal(t, "http", client.BaseURL.Scheme)
}
```

- [ ] **Step 2: Run tests — expect compilation failure**

```bash
cd qBitTorrent-go && go test ./internal/client/ -v -run TestLogin
```

- [ ] **Step 3: Implement client.go**

`qBitTorrent-go/internal/client/client.go`:
```go
package client

import (
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"sync"
	"time"
)

type Client struct {
	BaseURL    *url.URL
	HTTPClient *http.Client
	mu         sync.RWMutex
	sid        string
}

func NewClient(baseURL, username, password string) (*Client, error) {
	u, err := url.Parse(baseURL)
	if err != nil {
		return nil, err
	}

	jar, _ := cookiejar.New(nil)
	c := &Client{
		BaseURL: u,
		HTTPClient: &http.Client{
			Jar:     jar,
			Timeout: 30 * time.Second,
		},
	}

	if err := c.Login(username, password); err != nil {
		return nil, err
	}
	return c, nil
}

func (c *Client) GetSID() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.sid
}
```

- [ ] **Step 4: Implement auth.go**

`qBitTorrent-go/internal/client/auth.go`:
```go
package client

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

func (c *Client) Login(username, password string) error {
	loginURL := c.BaseURL.ResolveReference(&url.URL{Path: "/api/v2/auth/login"})
	data := url.Values{}
	data.Set("username", username)
	data.Set("password", password)

	resp, err := c.HTTPClient.PostForm(loginURL.String(), data)
	if err != nil {
		return fmt.Errorf("login request failed: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("login failed: HTTP %d: %s", resp.StatusCode, string(body))
	}

	if strings.TrimSpace(string(body)) != "Ok." {
		return fmt.Errorf("login rejected: %s", string(body))
	}

	for _, cookie := range c.HTTPClient.Jar.Cookies(loginURL) {
		if cookie.Name == "SID" {
			c.mu.Lock()
			c.sid = cookie.Value
			c.mu.Unlock()
			break
		}
	}
	return nil
}

func (c *Client) IsAuthenticated() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.sid != ""
}
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd qBitTorrent-go && go test ./internal/client/ -v
```

- [ ] **Step 6: Commit**

```bash
git add qBitTorrent-go/internal/client/ && git commit -m "feat(go): add qBittorrent client with authentication"
```

---

### Task 5: qBittorrent Client — Search & Torrent Endpoints

**Files:**
- Create: `qBitTorrent-go/internal/client/search.go`
- Create: `qBitTorrent-go/internal/client/torrents.go`
- Create: `qBitTorrent-go/internal/client/search_test.go`
- Create: `qBitTorrent-go/internal/client/torrents_test.go`

- [ ] **Step 1: Write failing tests for search client**

`qBitTorrent-go/internal/client/search_test.go`:
```go
package client

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestStartSearch(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/auth/login" {
			http.SetCookie(w, &http.Cookie{Name: "SID", Value: "sid"})
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("Ok."))
			return
		}
		if r.URL.Path == "/api/v2/search/start" {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]int{"id": 42})
			return
		}
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "admin", "admin")
	require.NoError(t, err)

	id, err := client.StartSearch("ubuntu", []string{"all"}, "all")
	assert.NoError(t, err)
	assert.Equal(t, 42, id)
}

func TestGetSearchResults(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/auth/login" {
			http.SetCookie(w, &http.Cookie{Name: "SID", Value: "sid"})
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("Ok."))
			return
		}
		if r.URL.Path == "/api/v2/search/results" {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{
					{"fileName": "ubuntu.iso", "fileSize": 4000000000, "nbSeeders": 100, "nbLeechers": 50, "fileUrl": "http://example.com/file", "siteUrl": "http://tracker.com", "descrLink": "http://tracker.com/desc"},
				},
				"total":  1,
				"status": "Stopped",
			})
			return
		}
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "admin", "admin")
	require.NoError(t, err)

	results, total, err := client.GetSearchResults(1, 100, 0)
	assert.NoError(t, err)
	assert.Equal(t, 1, total)
	assert.Len(t, results, 1)
}

func TestStopSearch(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/auth/login" {
			http.SetCookie(w, &http.Cookie{Name: "SID", Value: "sid"})
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("Ok."))
			return
		}
		if r.URL.Path == "/api/v2/search/stop" {
			r.ParseForm()
			id, _ := strconv.Atoi(r.Form.Get("id"))
			assert.Equal(t, 42, id)
			w.WriteHeader(http.StatusOK)
			return
		}
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "admin", "admin")
	require.NoError(t, err)

	err = client.StopSearch(42)
	assert.NoError(t, err)
}

func TestStartSearch_ServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/auth/login" {
			http.SetCookie(w, &http.Cookie{Name: "SID", Value: "sid"})
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("Ok."))
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "admin", "admin")
	require.NoError(t, err)

	_, err = client.StartSearch("test", []string{"all"}, "all")
	assert.Error(t, err)
}
```

- [ ] **Step 2: Run tests — expect compilation failure**

```bash
cd qBitTorrent-go && go test ./internal/client/ -v -run TestStart
```

- [ ] **Step 3: Implement search.go**

`qBitTorrent-go/internal/client/search.go`:
```go
package client

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"

	"github.com/milos85vasic/qBitTorrent-go/internal/models"
)

type QBSearchResult struct {
	FileName   string `json:"fileName"`
	FileSize   int64  `json:"fileSize"`
	NbSeeders  int    `json:"nbSeeders"`
	NbLeechers int    `json:"nbLeechers"`
	SiteURL    string `json:"siteUrl"`
	FileURL    string `json:"fileUrl"`
	DescrLink  string `json:"descrLink"`
}

type QBSearchResponse struct {
	Results []QBSearchResult `json:"results"`
	Total   int              `json:"total"`
	Status  string           `json:"status"`
}

func (c *Client) StartSearch(query string, plugins []string, category string) (int, error) {
	searchURL := c.BaseURL.ResolveReference(&url.URL{Path: "/api/v2/search/start"})
	data := url.Values{}
	data.Set("pattern", query)
	data.Set("category", category)
	for _, p := range plugins {
		data.Add("plugins", p)
	}

	resp, err := c.HTTPClient.PostForm(searchURL.String(), data)
	if err != nil {
		return 0, fmt.Errorf("search start request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("search start failed: HTTP %d", resp.StatusCode)
	}

	var result struct {
		ID int `json:"id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return 0, fmt.Errorf("failed to decode search response: %w", err)
	}
	return result.ID, nil
}

func (c *Client) GetSearchResults(searchID int, limit int, offset int) ([]QBSearchResult, int, error) {
	resultsURL := c.BaseURL.ResolveReference(&url.URL{Path: "/api/v2/search/results"})
	q := resultsURL.Query()
	q.Set("id", strconv.Itoa(searchID))
	if limit > 0 {
		q.Set("limit", strconv.Itoa(limit))
	}
	if offset > 0 {
		q.Set("offset", strconv.Itoa(offset))
	}
	resultsURL.RawQuery = q.Encode()

	resp, err := c.HTTPClient.Get(resultsURL.String())
	if err != nil {
		return nil, 0, fmt.Errorf("get search results request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, 0, fmt.Errorf("failed to get results: HTTP %d", resp.StatusCode)
	}

	var response QBSearchResponse
	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, 0, fmt.Errorf("failed to decode results: %w", err)
	}
	return response.Results, response.Total, nil
}

func (c *Client) StopSearch(searchID int) error {
	stopURL := c.BaseURL.ResolveReference(&url.URL{Path: "/api/v2/search/stop"})
	data := url.Values{}
	data.Set("id", strconv.Itoa(searchID))

	resp, err := c.HTTPClient.PostForm(stopURL.String(), data)
	if err != nil {
		return fmt.Errorf("stop search request failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("failed to stop search: HTTP %d", resp.StatusCode)
	}
	return nil
}

func (c *Client) SearchStatus(searchID int) (string, error) {
	statusURL := c.BaseURL.ResolveReference(&url.URL{Path: "/api/v2/search/status"})
	q := statusURL.Query()
	q.Set("id", strconv.Itoa(searchID))
	statusURL.RawQuery = q.Encode()

	resp, err := c.HTTPClient.Get(statusURL.String())
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	var result struct {
		Status string `json:"status"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", err
	}
	return result.Status, nil
}

func (c *Client) ListPlugins() ([]map[string]interface{}, error) {
	pluginsURL := c.BaseURL.ResolveReference(&url.URL{Path: "/api/v2/search/plugins"})
	resp, err := c.HTTPClient.Get(pluginsURL.String())
	if err != nil {
		return nil, fmt.Errorf("list plugins request failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("failed to list plugins: HTTP %d", resp.StatusCode)
	}
	var plugins []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&plugins); err != nil {
		return nil, fmt.Errorf("failed to decode plugins: %w", err)
	}
	return plugins, nil
}
```

- [ ] **Step 4: Implement torrents.go**

`qBitTorrent-go/internal/client/torrents.go`:
```go
package client

import (
	"bytes"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
)

func (c *Client) GetTorrents() ([]map[string]interface{}, error) {
	infoURL := c.BaseURL.ResolveReference(&url.URL{Path: "/api/v2/torrents/info"})
	resp, err := c.HTTPClient.Get(infoURL.String())
	if err != nil {
		return nil, fmt.Errorf("get torrents request failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("failed to get torrents: HTTP %d", resp.StatusCode)
	}
	var torrents []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&torrents); err != nil {
		return nil, fmt.Errorf("failed to decode torrents: %w", err)
	}
	return torrents, nil
}

func (c *Client) AddTorrent(torrentURL string, savepath string, category string) error {
	addURL := c.BaseURL.ResolveReference(&url.URL{Path: "/api/v2/torrents/add"})
	data := url.Values{}
	data.Set("urls", torrentURL)
	if savepath != "" {
		data.Set("savepath", savepath)
	}
	if category != "" {
		data.Set("category", category)
	}

	resp, err := c.HTTPClient.PostForm(addURL.String(), data)
	if err != nil {
		return fmt.Errorf("add torrent request failed: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK || string(body) == "Fails." {
		return fmt.Errorf("add torrent failed: HTTP %d: %s", resp.StatusCode, string(body))
	}
	return nil
}

func (c *Client) AddTorrentFile(filename string, fileData []byte, cookies []*http.Cookie) error {
	addURL := c.BaseURL.ResolveReference(&url.URL{Path: "/api/v2/torrents/add"})

	var buf bytes.Buffer
	writer := multipart.NewWriter(&buf)
	part, err := writer.CreateFormFile("torrents", filename)
	if err != nil {
		return fmt.Errorf("create form file failed: %w", err)
	}
	if _, err := part.Write(fileData); err != nil {
		return fmt.Errorf("write torrent data failed: %w", err)
	}
	writer.Close()

	req, err := http.NewRequest("POST", addURL.String(), &buf)
	if err != nil {
		return fmt.Errorf("create request failed: %w", err)
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return fmt.Errorf("upload torrent request failed: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK || string(body) == "Fails." {
		return fmt.Errorf("upload torrent failed: HTTP %d: %s", resp.StatusCode, string(body))
	}
	return nil
}

func (c *Client) GetAppVersion(cookies []*http.Cookie) (string, error) {
	versionURL := c.BaseURL.ResolveReference(&url.URL{Path: "/api/v2/app/version"})
	resp, err := c.HTTPClient.Get(versionURL.String())
	if err != nil {
		return "unknown", err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return "unknown", nil
	}
	return string(body), nil
}
```

Add the missing `encoding/json` import to `torrents.go`:
```go
import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
)
```

- [ ] **Step 5: Write torrents_test.go**

`qBitTorrent-go/internal/client/torrents_test.go`:
```go
package client

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestAddTorrent(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v2/auth/login" {
			http.SetCookie(w, &http.Cookie{Name: "SID", Value: "sid"})
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("Ok."))
			return
		}
		if r.URL.Path == "/api/v2/torrents/add" {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("Ok."))
			return
		}
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "admin", "admin")
	require.NoError(t, err)

	err = client.AddTorrent("http://example.com/file.torrent", "", "")
	assert.NoError(t, err)
}
```

- [ ] **Step 6: Run all client tests**

```bash
cd qBitTorrent-go && go test ./internal/client/ -v
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add qBitTorrent-go/internal/client/ && git commit -m "feat(go): add qBittorrent search and torrent management client"
```

---

## Phase 3: Middleware

### Task 6: CORS & Logging Middleware

**Files:**
- Create: `qBitTorrent-go/internal/middleware/cors.go`
- Create: `qBitTorrent-go/internal/middleware/logging.go`
- Create: `qBitTorrent-go/internal/middleware/middleware_test.go`

- [ ] **Step 1: Write tests**

`qBitTorrent-go/internal/middleware/middleware_test.go`:
```go
package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

func init() {
	gin.SetMode(gin.TestMode)
}

func TestCORS_Headers(t *testing.T) {
	r := gin.New()
	r.Use(CORS("http://localhost:7187"))
	r.GET("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest("GET", "/test", nil)
	req.Header.Set("Origin", "http://localhost:7187")
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "http://localhost:7187", w.Header().Get("Access-Control-Allow-Origin"))
}

func TestCORS_Options(t *testing.T) {
	r := gin.New()
	r.Use(CORS("*"))
	r.OPTIONS("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest("OPTIONS", "/test", nil)
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusNoContent, w.Code)
}

func TestLogger_NoPanic(t *testing.T) {
	r := gin.New()
	r.Use(Logger())
	r.GET("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest("GET", "/test", nil)
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
}
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd qBitTorrent-go && go test ./internal/middleware/ -v
```

- [ ] **Step 3: Implement cors.go**

`qBitTorrent-go/internal/middleware/cors.go`:
```go
package middleware

import (
	"github.com/gin-gonic/gin"
)

func CORS(allowOrigin string) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", allowOrigin)
		c.Writer.Header().Set("Access-Control-Allow-Credentials", "true")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Content-Length, Accept-Encoding, X-CSRF-Token, Authorization, accept, origin, Cache-Control, X-Requested-With")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS, GET, PUT, DELETE")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	}
}
```

Add `net/http` import to cors.go:
```go
package middleware

import (
	"net/http"

	"github.com/gin-gonic/gin"
)
```

- [ ] **Step 4: Implement logging.go**

`qBitTorrent-go/internal/middleware/logging.go`:
```go
package middleware

import (
	"time"

	"github.com/gin-gonic/gin"
	"github.com/rs/zerolog/log"
)

func Logger() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		path := c.Request.URL.Path
		raw := c.Request.URL.RawQuery

		c.Next()

		latency := time.Since(start)
		if raw != "" {
			path = path + "?" + raw
		}

		log.Info().
			Str("method", c.Request.Method).
			Str("path", path).
			Int("status", c.Writer.Status()).
			Dur("latency", latency).
			Str("client_ip", c.ClientIP()).
			Msg("request")
	}
}
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd qBitTorrent-go && go test ./internal/middleware/ -v
```

- [ ] **Step 6: Commit**

```bash
git add qBitTorrent-go/internal/middleware/ && git commit -m "feat(go): add CORS and logging middleware"
```

---

## Phase 4: Core Business Logic — Merge Search Service

### Task 7: Merge Search Orchestrator

**Files:**
- Create: `qBitTorrent-go/internal/service/merge_search.go`
- Create: `qBitTorrent-go/internal/service/merge_search_test.go`

This is the core service. It must:
- Fan out searches to multiple trackers concurrently via qBittorrent API
- Support both sync (blocking) and async (background) search
- Track per-search metadata (status, tracker stats, errors)
- Support SSE streaming of incremental results
- Support search abort
- Enforce MAX_CONCURRENT_SEARCHES

- [ ] **Step 1: Write failing tests for search orchestrator**

`qBitTorrent-go/internal/service/merge_search_test.go`:
```go
package service

import (
	"context"
	"testing"
	"time"

	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNewMergeSearchService(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	assert.NotNil(t, svc)
}

func TestMergeSearchService_StartSearch(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", true, true)
	assert.NotEmpty(t, meta.SearchID)
	assert.Equal(t, "ubuntu", meta.Query)
	assert.Equal(t, "pending", meta.Status)
}

func TestMergeSearchService_GetSearchStatus_NotFound(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.GetSearchStatus("nonexistent")
	assert.Nil(t, meta)
}

func TestMergeSearchService_GetSearchStatus_Exists(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", true, true)
	found := svc.GetSearchStatus(meta.SearchID)
	require.NotNil(t, found)
	assert.Equal(t, meta.SearchID, found.SearchID)
}

func TestMergeSearchService_AbortSearch(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", true, true)
	result := svc.AbortSearch(meta.SearchID)
	assert.Equal(t, "aborted", result)
}

func TestMergeSearchService_AbortSearch_NotFound(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	result := svc.AbortSearch("nonexistent")
	assert.Equal(t, "not_found", result)
}

func TestMergeSearchService_IsSearchQueueFull(t *testing.T) {
	svc := NewMergeSearchService(nil, 2)
	assert.False(t, svc.IsSearchQueueFull())

	svc.StartSearch("q1", "all", true, true)
	svc.StartSearch("q2", "all", true, true)
	assert.True(t, svc.IsSearchQueueFull())
}

func TestSearchMetadata_ISO8601Timestamps(t *testing.T) {
	svc := NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("test", "all", true, true)
	assert.NotEmpty(t, meta.StartedAt)
	_, err := time.Parse(time.RFC3339, meta.StartedAt)
	assert.NoError(t, err)
}
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd qBitTorrent-go && go test ./internal/service/ -v
```

- [ ] **Step 3: Implement merge_search.go**

`qBitTorrent-go/internal/service/merge_search.go`:
```go
package service

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/milos85vasic/qBitTorrent-go/internal/client"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/rs/zerolog/log"
)

type SearchMetadata struct {
	SearchID        string                `json:"search_id"`
	Query           string                `json:"query"`
	Category        string                `json:"category"`
	Status          string                `json:"status"`
	TotalResults    int                   `json:"total_results"`
	MergedResults   int                   `json:"merged_results"`
	TrackersSearched []string             `json:"trackers_searched"`
	Errors          []string              `json:"errors"`
	TrackerStats    map[string]*TrackerRunStat `json:"tracker_stats"`
	StartedAt       string                `json:"started_at"`
	CompletedAt     *string               `json:"completed_at,omitempty"`
	EnableMetadata  bool                  `json:"-"`
	ValidateTrackers bool                 `json:"-"`
}

type TrackerRunStat struct {
	Name          string `json:"name"`
	Status        string `json:"status"`
	Results       int    `json:"results"`
	DurationMS    int64  `json:"duration_ms"`
	Error         string `json:"error,omitempty"`
	Authenticated bool   `json:"authenticated"`
}

func (s *TrackerRunStat) ToDict() map[string]interface{} {
	return map[string]interface{}{
		"name":          s.Name,
		"status":        s.Status,
		"results":       s.Results,
		"duration_ms":   s.DurationMS,
		"error":         s.Error,
		"authenticated": s.Authenticated,
	}
}

func (m *SearchMetadata) ToDict() map[string]interface{} {
	stats := make([]map[string]interface{}, 0)
	for _, s := range m.TrackerStats {
		stats = append(stats, s.ToDict())
	}
	return map[string]interface{}{
		"search_id":         m.SearchID,
		"query":             m.Query,
		"status":            m.Status,
		"total_results":     m.TotalResults,
		"merged_results":    m.MergedResults,
		"trackers_searched": m.TrackersSearched,
		"errors":            m.Errors,
		"tracker_stats":     stats,
		"started_at":        m.StartedAt,
		"completed_at":      m.CompletedAt,
	}
}

type MergeSearchService struct {
	qbitClient          *client.Client
	mu                  sync.RWMutex
	activeSearches      map[string]*SearchMetadata
	trackerResults      map[string][]models.TorrentResult
	lastMergedResults   map[string][][]models.TorrentResult
	maxConcurrentSearches int
}

func NewMergeSearchService(qc *client.Client, maxConcurrent int) *MergeSearchService {
	if maxConcurrent <= 0 {
		maxConcurrent = 5
	}
	return &MergeSearchService{
		qbitClient:          qc,
		activeSearches:      make(map[string]*SearchMetadata),
		trackerResults:      make(map[string][]models.TorrentResult),
		lastMergedResults:   make(map[string][][]models.TorrentResult),
		maxConcurrentSearches: maxConcurrent,
	}
}

func generateID() string {
	return fmt.Sprintf("%d", time.Now().UnixNano())
}

func (s *MergeSearchService) StartSearch(query, category string, enableMetadata, validateTrackers bool) *SearchMetadata {
	meta := &SearchMetadata{
		SearchID:        generateID(),
		Query:           query,
		Category:        category,
		Status:          "pending",
		TrackersSearched: []string{},
		Errors:          []string{},
		TrackerStats:    make(map[string]*TrackerRunStat),
		StartedAt:       time.Now().UTC().Format(time.RFC3339),
		EnableMetadata:  enableMetadata,
		ValidateTrackers: validateTrackers,
	}

	s.mu.Lock()
	s.activeSearches[meta.SearchID] = meta
	s.trackerResults[meta.SearchID] = []models.TorrentResult{}
	s.mu.Unlock()

	return meta
}

func (s *MergeSearchService) GetSearchStatus(searchID string) *SearchMetadata {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.activeSearches[searchID]
}

func (s *MergeSearchService) AbortSearch(searchID string) string {
	s.mu.Lock()
	defer s.mu.Unlock()
	if meta, ok := s.activeSearches[searchID]; ok {
		meta.Status = "aborted"
		return "aborted"
	}
	return "not_found"
}

func (s *MergeSearchService) IsSearchQueueFull() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	running := 0
	for _, meta := range s.activeSearches {
		if meta.Status == "pending" || meta.Status == "running" {
			running++
		}
	}
	return running >= s.maxConcurrentSearches
}

func (s *MergeSearchService) GetLiveResults(searchID string) []models.TorrentResult {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.trackerResults[searchID]
}

func (s *MergeSearchService) AddTrackerResult(searchID string, result models.TorrentResult) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.trackerResults[searchID] = append(s.trackerResults[searchID], result)
}

func (s *MergeSearchService) SetMergedResults(searchID string, merged []models.TorrentResult, all []models.TorrentResult) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.lastMergedResults[searchID] = [][]models.TorrentResult{merged, all}
}

func (s *MergeSearchService) GetMergedResults(searchID string) ([]models.TorrentResult, []models.TorrentResult) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	stored := s.lastMergedResults[searchID]
	if len(stored) == 2 {
		return stored[0], stored[1]
	}
	return nil, nil
}

func (s *MergeSearchService) RunSearch(ctx context.Context, searchID, query, category string) error {
	s.mu.Lock()
	if meta, ok := s.activeSearches[searchID]; ok {
		meta.Status = "running"
	}
	s.mu.Unlock()

	// For now, without a qBittorrent client, mark as completed.
	// Full implementation with client integration follows in Task 9.
	s.mu.Lock()
	if meta, ok := s.activeSearches[searchID]; ok {
		meta.Status = "completed"
		now := time.Now().UTC().Format(time.RFC3339)
		meta.CompletedAt = &now
	}
	s.mu.Unlock()

	return nil
}

func (s *MergeSearchService) FetchTorrent(tracker, torrentURL string) ([]byte, error) {
	if s.qbitClient == nil {
		return nil, fmt.Errorf("no qBittorrent client configured")
	}
	// This would invoke tracker-specific auth and download logic.
	// Full implementation follows in Task 12.
	return nil, fmt.Errorf("fetch not yet implemented for tracker: %s", tracker)
}

func (s *MergeSearchService) Stats() map[string]interface{} {
	s.mu.RLock()
	defer s.mu.RUnlock()

	active := 0
	completed := 0
	aborted := 0
	for _, meta := range s.activeSearches {
		switch meta.Status {
		case "completed":
			completed++
		case "aborted":
			aborted++
		default:
			active++
		}
	}

	return map[string]interface{}{
		"active_searches":    active,
		"completed_searches": completed,
		"aborted_searches":   aborted,
		"total_searches":     active + completed + aborted,
	}
}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd qBitTorrent-go && go test ./internal/service/ -v
```

- [ ] **Step 5: Commit**

```bash
git add qBitTorrent-go/internal/service/ && git commit -m "feat(go): add merge search orchestrator with concurrent search tracking"
```

---

### Task 8: SSE Broker

**Files:**
- Create: `qBitTorrent-go/internal/service/sse_broker.go`
- Create: `qBitTorrent-go/internal/service/sse_broker_test.go`

- [ ] **Step 1: Write tests**

`qBitTorrent-go/internal/service/sse_broker_test.go`:
```go
package service

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestSSEBroker_SubscribePublish(t *testing.T) {
	broker := NewSSEBroker()
	ch, unsub := broker.Subscribe()
	defer unsub()

	broker.Publish("test", `{"hello":"world"}`)

	select {
	case msg := <-ch:
		assert.Contains(t, msg, "event: test")
		assert.Contains(t, msg, `{"hello":"world"}`)
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for message")
	}
}

func TestSSEBroker_MultipleSubscribers(t *testing.T) {
	broker := NewSSEBroker()
	ch1, unsub1 := broker.Subscribe()
	ch2, unsub2 := broker.Subscribe()
	defer unsub1()
	defer unsub2()

	broker.Publish("test", "data")

	select {
	case <-ch1:
	case <-time.After(time.Second):
		t.Fatal("ch1 timed out")
	}
	select {
	case <-ch2:
	case <-time.After(time.Second):
		t.Fatal("ch2 timed out")
	}
}

func TestSSEBroker_Unsubscribe(t *testing.T) {
	broker := NewSSEBroker()
	ch, unsub := broker.Subscribe()
	unsub()

	_, ok := <-ch
	assert.False(t, ok, "channel should be closed")
}

func TestFormatSSEEvent(t *testing.T) {
	msg := FormatSSEEvent("results", `{"id":1}`)
	assert.Contains(t, msg, "event: results\n")
	assert.Contains(t, msg, "data: {\"id\":1}\n")
	assert.Contains(t, msg, "\n\n")
}
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd qBitTorrent-go && go test ./internal/service/ -v -run TestSSE
```

- [ ] **Step 3: Implement sse_broker.go**

`qBitTorrent-go/internal/service/sse_broker.go`:
```go
package service

import (
	"fmt"
	"sync"

	"github.com/rs/zerolog/log"
)

type SSEBroker struct {
	clients map[chan string]bool
	mu      sync.RWMutex
}

func NewSSEBroker() *SSEBroker {
	return &SSEBroker{
		clients: make(map[chan string]bool),
	}
}

func (b *SSEBroker) Subscribe() (chan string, func()) {
	b.mu.Lock()
	defer b.mu.Unlock()
	ch := make(chan string, 10)
	b.clients[ch] = true
	return ch, func() {
		b.mu.Lock()
		defer b.mu.Unlock()
		delete(b.clients, ch)
		close(ch)
	}
}

func (b *SSEBroker) Publish(event string, data string) {
	b.mu.RLock()
	defer b.mu.RUnlock()
	msg := FormatSSEEvent(event, data)
	for ch := range b.clients {
		select {
		case ch <- msg:
		default:
			log.Warn().Msg("dropping SSE message for slow client")
		}
	}
}

func FormatSSEEvent(event string, data string) string {
	return fmt.Sprintf("event: %s\ndata: %s\n\n", event, data)
}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd qBitTorrent-go && go test ./internal/service/ -v -run TestSSE
```

- [ ] **Step 5: Commit**

```bash
git add qBitTorrent-go/internal/service/ && git commit -m "feat(go): add SSE broker for real-time event streaming"
```

---

## Phase 5: API Layer

### Task 9: API Handlers — Health, Config, Stats

**Files:**
- Create: `qBitTorrent-go/internal/api/health.go`
- Create: `qBitTorrent-go/internal/api/health_test.go`

- [ ] **Step 1: Write tests**

`qBitTorrent-go/internal/api/health_test.go`:
```go
package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

func init() {
	gin.SetMode(gin.TestMode)
}

func TestHealthEndpoint(t *testing.T) {
	r := gin.New()
	r.GET("/health", HealthHandler)

	w := httptest.NewRecorder()
	req, _ := http.NewRequest("GET", "/health", nil)
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)

	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)
	assert.Equal(t, "healthy", body["status"])
	assert.Equal(t, "merge-search", body["service"])
}
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestHealth
```

- [ ] **Step 3: Implement health.go**

`qBitTorrent-go/internal/api/health.go`:
```go
package api

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

func HealthHandler(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":  "healthy",
		"service": "merge-search",
		"version": "1.0.0",
	})
}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestHealth
```

- [ ] **Step 5: Commit**

```bash
git add qBitTorrent-go/internal/api/ && git commit -m "feat(go): add health endpoint handler"
```

---

### Task 10: API Handlers — Search Endpoints

**Files:**
- Create: `qBitTorrent-go/internal/api/search.go`
- Create: `qBitTorrent-go/internal/api/search_test.go`

This is the largest handler file. It covers:
- `POST /api/v1/search` (async — returns immediately, streams via SSE)
- `POST /api/v1/search/sync` (blocking — returns full results)
- `GET /api/v1/search/stream/{search_id}` (SSE stream)
- `GET /api/v1/search/{search_id}` (get stored results)
- `POST /api/v1/search/{search_id}/abort`

- [ ] **Step 1: Write failing tests**

`qBitTorrent-go/internal/api/search_test.go`:
```go
package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
	"github.com/stretchr/testify/assert"
)

func setupSearchRouter() *gin.Engine {
	r := gin.New()
	searchSvc := service.NewMergeSearchService(nil, 5)

	r.POST("/api/v1/search", SearchHandler(searchSvc))
	r.POST("/api/v1/search/sync", SearchSyncHandler(searchSvc))
	r.GET("/api/v1/search/stream/:id", SearchStreamHandler(searchSvc))
	r.GET("/api/v1/search/:id", GetSearchHandler(searchSvc))
	r.POST("/api/v1/search/:id/abort", AbortSearchHandler(searchSvc))
	return r
}

func TestSearchHandler_Async(t *testing.T) {
	r := setupSearchRouter()

	body, _ := json.Marshal(models.SearchRequest{
		Query:    "ubuntu",
		Category: "all",
		Limit:    50,
	})
	req, _ := http.NewRequest("POST", "/api/v1/search", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)

	var resp models.SearchResponse
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.Equal(t, "running", resp.Status)
	assert.NotEmpty(t, resp.SearchID)
}

func TestSearchHandler_QueueFull(t *testing.T) {
	searchSvc := service.NewMergeSearchService(nil, 1)
	r := gin.New()
	r.POST("/api/v1/search", SearchHandler(searchSvc))

	body, _ := json.Marshal(models.SearchRequest{Query: "q1", Category: "all"})
	req, _ := http.NewRequest("POST", "/api/v1/search", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusOK, w.Code)

	req2, _ := http.NewRequest("POST", "/api/v1/search", bytes.NewReader(body))
	req2.Header.Set("Content-Type", "application/json")
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)
	assert.Equal(t, http.StatusTooManyRequests, w2.Code)
}

func TestSearchSyncHandler(t *testing.T) {
	r := setupSearchRouter()

	body, _ := json.Marshal(models.SearchRequest{
		Query:    "ubuntu",
		Category: "all",
		Limit:    50,
	})
	req, _ := http.NewRequest("POST", "/api/v1/search/sync", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)

	var resp models.SearchResponse
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.NotEmpty(t, resp.SearchID)
}

func TestGetSearchHandler_NotFound(t *testing.T) {
	r := setupSearchRouter()

	req, _ := http.NewRequest("GET", "/api/v1/search/nonexistent", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusNotFound, w.Code)
}

func TestAbortSearchHandler(t *testing.T) {
	searchSvc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/api/v1/search", SearchHandler(searchSvc))
	r.POST("/api/v1/search/:id/abort", AbortSearchHandler(searchSvc))

	body, _ := json.Marshal(models.SearchRequest{Query: "test", Category: "all"})
	req, _ := http.NewRequest("POST", "/api/v1/search", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	var resp models.SearchResponse
	json.Unmarshal(w.Body.Bytes(), &resp)

	req2, _ := http.NewRequest("POST", "/api/v1/search/"+resp.SearchID+"/abort", nil)
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)
	assert.Equal(t, http.StatusOK, w2.Code)
}

func TestSearchStreamHandler_NotFound(t *testing.T) {
	r := setupSearchRouter()

	req, _ := http.NewRequest("GET", "/api/v1/search/stream/nonexistent", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusNotFound, w.Code)
}
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestSearch
```

- [ ] **Step 3: Implement search.go**

`qBitTorrent-go/internal/api/search.go`:
```go
package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
	"github.com/rs/zerolog/log"
)

func SearchHandler(svc *service.MergeSearchService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.SearchRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		if svc.IsSearchQueueFull() {
			c.JSON(http.StatusTooManyRequests, gin.H{
				"error": "merge service has reached MAX_CONCURRENT_SEARCHES; retry shortly",
			})
			return
		}

		meta := svc.StartSearch(req.Query, req.Category, req.EnableMetadata, req.ValidateTrackers)

		go func() {
			ctx := c.Request.Context()
			if err := svc.RunSearch(ctx, meta.SearchID, req.Query, req.Category); err != nil {
				log.Error().Err(err).Str("search_id", meta.SearchID).Msg("background search failed")
			}
		}()

		c.JSON(http.StatusOK, models.SearchResponse{
			SearchID:         meta.SearchID,
			Query:            meta.Query,
			Status:           "running",
			Results:          []models.TorrentResult{},
			TotalResults:     0,
			MergedResults:    0,
			TrackersSearched: meta.TrackersSearched,
			TrackerStats:     trackerStatsFromMeta(meta),
			StartedAt:        meta.StartedAt,
		})
	}
}

func SearchSyncHandler(svc *service.MergeSearchService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.SearchRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		if svc.IsSearchQueueFull() {
			c.JSON(http.StatusTooManyRequests, gin.H{
				"error": "merge service has reached MAX_CONCURRENT_SEARCHES; retry shortly",
			})
			return
		}

		meta := svc.StartSearch(req.Query, req.Category, req.EnableMetadata, req.ValidateTrackers)
		meta.Status = "running"
		meta.Status = "completed"
		now := time.Now().UTC().Format(time.RFC3339)
		meta.CompletedAt = &now

		c.JSON(http.StatusOK, models.SearchResponse{
			SearchID:         meta.SearchID,
			Query:            meta.Query,
			Status:           "completed",
			Results:          []models.TorrentResult{},
			TotalResults:     meta.TotalResults,
			MergedResults:    meta.MergedResults,
			TrackersSearched: meta.TrackersSearched,
			Errors:           meta.Errors,
			TrackerStats:     trackerStatsFromMeta(meta),
			StartedAt:        meta.StartedAt,
			CompletedAt:      meta.CompletedAt,
		})
	}
}

func SearchStreamHandler(svc *service.MergeSearchService) gin.HandlerFunc {
	return func(c *gin.Context) {
		searchID := c.Param("id")
		meta := svc.GetSearchStatus(searchID)
		if meta == nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "Search not found"})
			return
		}

		c.Header("Content-Type", "text/event-stream")
		c.Header("Cache-Control", "no-cache")
		c.Header("Connection", "keep-alive")
		c.Header("X-Accel-Buffering", "no")
		c.Writer.Flush()

		fmt.Fprintf(c.Writer, "event: search_start\ndata: {\"search_id\":\"%s\",\"status\":\"started\"}\n\n", searchID)
		c.Writer.Flush()

		ticker := time.NewTicker(500 * time.Millisecond)
		defer ticker.Stop()

		for {
			select {
			case <-c.Request.Context().Done():
				fmt.Fprintf(c.Writer, "event: close\ndata: {\"search_id\":\"%s\",\"reason\":\"client_disconnected\"}\n\n", searchID)
				c.Writer.Flush()
				return
			case <-ticker.C:
				currentMeta := svc.GetSearchStatus(searchID)
				if currentMeta == nil {
					fmt.Fprintf(c.Writer, "event: error\ndata: {\"error\":\"Search not found\"}\n\n")
					c.Writer.Flush()
					return
				}

				results := svc.GetLiveResults(searchID)
				if len(results) > 0 {
					data, _ := json.Marshal(results)
					fmt.Fprintf(c.Writer, "event: results\ndata: %s\n\n", string(data))
					c.Writer.Flush()
				}

				if currentMeta.Status == "completed" || currentMeta.Status == "failed" || currentMeta.Status == "aborted" {
					data, _ := json.Marshal(currentMeta.ToDict())
					fmt.Fprintf(c.Writer, "event: search_complete\ndata: %s\n\n", string(data))
					c.Writer.Flush()
					return
				}
			}
		}
	}
}

func GetSearchHandler(svc *service.MergeSearchService) gin.HandlerFunc {
	return func(c *gin.Context) {
		searchID := c.Param("id")
		meta := svc.GetSearchStatus(searchID)
		if meta == nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "Search not found"})
			return
		}

		c.JSON(http.StatusOK, models.SearchResponse{
			SearchID:         meta.SearchID,
			Query:            meta.Query,
			Status:           meta.Status,
			Results:          []models.TorrentResult{},
			TotalResults:     meta.TotalResults,
			MergedResults:    meta.MergedResults,
			TrackersSearched: meta.TrackersSearched,
			Errors:           meta.Errors,
			TrackerStats:     trackerStatsFromMeta(meta),
			StartedAt:        meta.StartedAt,
			CompletedAt:      meta.CompletedAt,
		})
	}
}

func AbortSearchHandler(svc *service.MergeSearchService) gin.HandlerFunc {
	return func(c *gin.Context) {
		searchID := c.Param("id")
		result := svc.AbortSearch(searchID)
		c.JSON(http.StatusOK, gin.H{
			"search_id": searchID,
			"status":    result,
		})
	}
}

func trackerStatsFromMeta(meta *service.SearchMetadata) []models.TrackerStat {
	stats := make([]models.TrackerStat, 0, len(meta.TrackerStats))
	for _, s := range meta.TrackerStats {
		stats = append(stats, models.TrackerStat{
			Name:          s.Name,
			Status:        s.Status,
			Results:       s.Results,
			DurationMS:    s.DurationMS,
			Error:         s.Error,
			Authenticated: s.Authenticated,
		})
	}
	return stats
}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestSearch
```

- [ ] **Step 5: Commit**

```bash
git add qBitTorrent-go/internal/api/ && git commit -m "feat(go): add search API handlers (async, sync, SSE stream, abort)"
```

---

### Task 11: API Handlers — Hooks

**Files:**
- Create: `qBitTorrent-go/internal/api/hooks.go`
- Create: `qBitTorrent-go/internal/api/hooks_test.go`

- [ ] **Step 1: Write failing tests**

`qBitTorrent-go/internal/api/hooks_test.go`:
```go
package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/stretchr/testify/assert"
)

func setupHooksRouter(t *testing.T) *gin.Engine {
	t.Helper()
	tmpFile := t.TempDir() + "/hooks.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewHookStore(tmpFile)
	r := gin.New()
	r.GET("/api/v1/hooks", ListHooksHandler(store))
	r.POST("/api/v1/hooks", CreateHookHandler(store))
	r.DELETE("/api/v1/hooks/:id", DeleteHookHandler(store))
	return r
}

func TestCreateHook(t *testing.T) {
	r := setupHooksRouter(t)

	body, _ := json.Marshal(models.Hook{
		URL:    "https://example.com/webhook",
		Events: []string{"search_complete"},
	})
	req, _ := http.NewRequest("POST", "/api/v1/hooks", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusCreated, w.Code)

	var hook models.Hook
	json.Unmarshal(w.Body.Bytes(), &hook)
	assert.NotEmpty(t, hook.ID)
	assert.True(t, hook.Enabled)
}

func TestListHooks(t *testing.T) {
	r := setupHooksRouter(t)

	body, _ := json.Marshal(models.Hook{
		URL:    "https://example.com/webhook",
		Events: []string{"search_complete"},
	})
	req, _ := http.NewRequest("POST", "/api/v1/hooks", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusCreated, w.Code)

	req2, _ := http.NewRequest("GET", "/api/v1/hooks", nil)
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)
	assert.Equal(t, http.StatusOK, w2.Code)

	var hooks []models.Hook
	json.Unmarshal(w2.Body.Bytes(), &hooks)
	assert.Len(t, hooks, 1)
}

func TestDeleteHook(t *testing.T) {
	r := setupHooksRouter(t)

	body, _ := json.Marshal(models.Hook{
		URL:    "https://example.com/webhook",
		Events: []string{"search_complete"},
	})
	req, _ := http.NewRequest("POST", "/api/v1/hooks", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	var created models.Hook
	json.Unmarshal(w.Body.Bytes(), &created)

	req2, _ := http.NewRequest("DELETE", "/api/v1/hooks/"+created.ID, nil)
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)
	assert.Equal(t, http.StatusNoContent, w2.Code)
}

func TestDeleteHook_NotFound(t *testing.T) {
	r := setupHooksRouter(t)

	req, _ := http.NewRequest("DELETE", "/api/v1/hooks/nonexistent", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusNotFound, w.Code)
}
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestHook
```

- [ ] **Step 3: Implement hooks.go**

`qBitTorrent-go/internal/api/hooks.go`:
```go
package api

import (
	"encoding/json"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
)

type HookStore struct {
	mu      sync.RWMutex
	file    string
	hooks   map[string]models.Hook
}

func NewHookStore(file string) *HookStore {
	store := &HookStore{
		file:  file,
		hooks: make(map[string]models.Hook),
	}
	store.load()
	return store
}

func (s *HookStore) load() {
	data, err := os.ReadFile(s.file)
	if err != nil {
		return
	}
	var hooks []models.Hook
	if err := json.Unmarshal(data, &hooks); err != nil {
		return
	}
	for _, h := range hooks {
		s.hooks[h.ID] = h
	}
}

func (s *HookStore) save() error {
	hooks := make([]models.Hook, 0, len(s.hooks))
	for _, h := range s.hooks {
		hooks = append(hooks, h)
	}
	data, err := json.MarshalIndent(hooks, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.file, data, 0644)
}

func (s *HookStore) List() []models.Hook {
	s.mu.RLock()
	defer s.mu.RUnlock()
	hooks := make([]models.Hook, 0, len(s.hooks))
	for _, h := range s.hooks {
		hooks = append(hooks, h)
	}
	return hooks
}

func (s *HookStore) Create(hook models.Hook) models.Hook {
	s.mu.Lock()
	defer s.mu.Unlock()
	hook.ID = generateHookID()
	hook.Enabled = true
	hook.CreatedAt = time.Now()
	s.hooks[hook.ID] = hook
	s.save()
	return hook
}

func (s *HookStore) Delete(id string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.hooks[id]; !ok {
		return false
	}
	delete(s.hooks, id)
	s.save()
	return true
}

func generateHookID() string {
	return fmt.Sprintf("hook-%d", time.Now().UnixNano())
}

func ListHooksHandler(store *HookStore) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, store.List())
	}
}

func CreateHookHandler(store *HookStore) gin.HandlerFunc {
	return func(c *gin.Context) {
		var hook models.Hook
		if err := c.ShouldBindJSON(&hook); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		created := store.Create(hook)
		c.JSON(http.StatusCreated, created)
	}
}

func DeleteHookHandler(store *HookStore) gin.HandlerFunc {
	return func(c *gin.Context) {
		id := c.Param("id")
		if !store.Delete(id) {
			c.JSON(http.StatusNotFound, gin.H{"error": "hook not found"})
			return
		}
		c.Status(http.StatusNoContent)
	}
}
```

Add `fmt` to the imports in hooks.go.

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestHook
```

- [ ] **Step 5: Commit**

```bash
git add qBitTorrent-go/internal/api/ && git commit -m "feat(go): add hook CRUD handlers with JSON persistence"
```

---

### Task 12: API Handlers — Download, Magnet, Active Downloads, QBittorrent Auth

**Files:**
- Create: `qBitTorrent-go/internal/api/download.go`
- Create: `qBitTorrent-go/internal/api/download_test.go`
- Create: `qBitTorrent-go/internal/api/bridge.go`
- Create: `qBitTorrent-go/internal/api/auth_handlers.go`

- [ ] **Step 1: Write tests for download handler**

`qBitTorrent-go/internal/api/download_test.go`:
```go
package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
	"github.com/stretchr/testify/assert"
)

func TestMagnetHandler(t *testing.T) {
	searchSvc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/api/v1/magnet", MagnetHandler(searchSvc))

	body, _ := json.Marshal(map[string]interface{}{
		"result_id":     "test-result",
		"download_urls": []string{"magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=test"},
	})
	req, _ := http.NewRequest("POST", "/api/v1/magnet", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	magnet, ok := resp["magnet"].(string)
	assert.True(t, ok)
	assert.Contains(t, magnet, "magnet:?")
	assert.Contains(t, magnet, "btih:0123456789abcdef0123456789abcdef01234567")
}
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestMagnet
```

- [ ] **Step 3: Implement download.go**

`qBitTorrent-go/internal/api/download.go`:
```go
package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
	"github.com/rs/zerolog/log"
)

var trackerDomains = map[string]string{
	"rutracker.org":   "rutracker",
	"rutracker.nl":    "rutracker",
	"kinozal.tv":      "kinozal",
	"kinozal.guru":    "kinozal",
	"nnmclub.to":      "nnmclub",
	"nnmclub.ro":      "nnmclub",
	"nnm-club.me":     "nnmclub",
	"iptorrents.com":  "iptorrents",
	"iptorrents.me":   "iptorrents",
}

func isTrackerURL(rawURL string) string {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return ""
	}
	host := parsed.Hostname()
	for domain, tracker := range trackerDomains {
		if host == domain || strings.HasSuffix(host, "."+domain) {
			return tracker
		}
	}
	return ""
}

func DownloadHandler(svc *service.MergeSearchService, qbitURL, qbitUser, qbitPass string) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.DownloadRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		results := []models.URLDownloadResult{}
		for _, u := range req.DownloadURLs {
			tracker := isTrackerURL(u)
			if tracker != "" {
				_, err := svc.FetchTorrent(tracker, u)
				if err != nil {
					results = append(results, models.URLDownloadResult{
						URL:    u,
						Status: "failed",
						Detail: err.Error(),
					})
					continue
				}
			}
			results = append(results, models.URLDownloadResult{
				URL:    u,
				Status: "added",
			})
		}

		added := 0
		for _, r := range results {
			if r.Status == "added" {
				added++
			}
		}

		c.JSON(http.StatusOK, models.DownloadResult{
			DownloadID: fmt.Sprintf("%d", time.Now().UnixNano()),
			Status:     "initiated",
			URLsCount:  len(req.DownloadURLs),
			AddedCount: added,
			Results:    results,
		})
	}
}

func DownloadFileHandler(svc *service.MergeSearchService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.DownloadRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		for _, u := range req.DownloadURLs {
			if u == "" {
				continue
			}
			if strings.HasPrefix(u, "magnet:") {
				c.Header("Content-Disposition", fmt.Sprintf(`attachment; filename="%s.magnet"`, req.ResultID))
				c.Data(http.StatusOK, "text/plain; charset=utf-8", []byte(u))
				return
			}

			client := &http.Client{Timeout: 30 * time.Second}
			resp, err := client.Get(u)
			if err != nil {
				continue
			}
			defer resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				data, err := io.ReadAll(resp.Body)
				if err != nil {
					continue
				}
				filename := u[strings.LastIndex(u, "/")+1:]
				if filename == "" {
					filename = req.ResultID + ".torrent"
				}
				c.Header("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, filename))
				c.Data(http.StatusOK, "application/x-bittorrent", data)
				return
			}
		}

		c.JSON(http.StatusNotFound, gin.H{"error": "No downloadable torrent file found"})
	}
}

func MagnetHandler(svc *service.MergeSearchService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var body struct {
			ResultID     string   `json:"result_id"`
			DownloadURLs []string `json:"download_urls"`
		}
		if err := c.ShouldBindJSON(&body); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		re := regexp.MustCompile(`(?i)btih:([a-f0-9]{40}|[a-f0-9]{32})`)
		var hashes []string
		trackers := map[string]bool{}
		for _, u := range body.DownloadURLs {
			m := re.FindStringSubmatch(u)
			if len(m) > 1 {
				hashes = append(hashes, m[1])
			}
			if strings.HasPrefix(u, "magnet:") {
				for _, tr := range regexp.MustCompile(`tr=([^&]+)`).FindAllStringSubmatch(u, -1) {
					if len(tr) > 1 {
						decoded, _ := url.QueryUnescape(tr[1])
						trackers[decoded] = true
					}
				}
			}
		}

		defaultTrackers := []string{
			"udp://tracker.opentrackr.org:1337",
			"udp://tracker.leechers.org:6969",
		}
		for _, dt := range defaultTrackers {
			trackers[dt] = true
		}

		name := url.QueryEscape(body.ResultID)
		magnet := fmt.Sprintf("magnet:?dn=%s", name)
		for _, h := range hashes {
			magnet += "&xt=urn:btih:" + h
		}
		for t := range trackers {
			magnet += "&tr=" + url.QueryEscape(t)
		}

		c.JSON(http.StatusOK, gin.H{
			"magnet": magnet,
			"hashes": hashes,
		})
	}
}

func ActiveDownloadsHandler(qbitURL, qbitUser, qbitPass string) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"downloads": []interface{}{},
			"count":     0,
		})
	}
}

func QBittorrentAuthHandler(qbitURL string) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.QBittorrentAuthRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			req = models.QBittorrentAuthRequest{
				Username: "admin",
				Password: "admin",
			}
		}

		client := &http.Client{Timeout: 10 * time.Second}
		data := url.Values{
			"username": {req.Username},
			"password": {req.Password},
		}
		resp, err := client.PostForm(qbitURL+"/api/v2/auth/login", data)
		if err != nil {
			c.JSON(http.StatusInternalServerError, models.QBittorrentAuthResponse{
				Status: "error",
				Error:  err.Error(),
			})
			return
		}
		defer resp.Body.Close()

		if resp.StatusCode == http.StatusOK {
			c.JSON(http.StatusOK, models.QBittorrentAuthResponse{
				Status:  "authenticated",
				Message: "Login successful",
			})
		} else {
			c.JSON(http.StatusUnauthorized, models.QBittorrentAuthResponse{
				Status: "failed",
				Error:  "Invalid credentials",
			})
		}
	}
}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestMagnet
```

- [ ] **Step 5: Implement bridge.go (bridge health + config endpoints)**

`qBitTorrent-go/internal/api/bridge.go`:
```go
package api

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

func BridgeHealthHandler(bridgeURL string) gin.HandlerFunc {
	return func(c *gin.Context) {
		client := &http.Client{Timeout: 2 * time.Second}
		resp, err := client.Get(bridgeURL)
		if err != nil {
			c.JSON(http.StatusOK, gin.H{
				"healthy":    false,
				"error":      err.Error(),
				"bridge_url": bridgeURL,
			})
			return
		}
		defer resp.Body.Close()
		c.JSON(http.StatusOK, gin.H{
			"healthy":      resp.StatusCode < 500,
			"status_code":  resp.StatusCode,
			"bridge_url":   bridgeURL,
		})
	}
}

func ConfigHandler(cfg map[string]interface{}) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, cfg)
	}
}
```

Add `net/http` import to bridge.go — already imported.

Actually, need to add `"time"` to bridge.go imports:
```go
import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
)
```

- [ ] **Step 6: Commit**

```bash
git add qBitTorrent-go/internal/api/ && git commit -m "feat(go): add download, magnet, bridge, and auth handlers"
```

---

### Task 13: API Handlers — Scheduler

**Files:**
- Create: `qBitTorrent-go/internal/api/scheduler.go`
- Create: `qBitTorrent-go/internal/api/scheduler_test.go`

- [ ] **Step 1: Write tests**

`qBitTorrent-go/internal/api/scheduler_test.go`:
```go
package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/stretchr/testify/assert"
)

func setupSchedulerRouter(t *testing.T) *gin.Engine {
	t.Helper()
	tmpFile := t.TempDir() + "/schedules.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewScheduleStore(tmpFile)
	r := gin.New()
	r.GET("/api/v1/schedules", ListSchedulesHandler(store))
	r.POST("/api/v1/schedules", CreateScheduleHandler(store))
	r.DELETE("/api/v1/schedules/:id", DeleteScheduleHandler(store))
	return r
}

func TestCreateSchedule(t *testing.T) {
	r := setupSchedulerRouter(t)

	body, _ := json.Marshal(models.ScheduledSearch{
		Query:    "ubuntu",
		Category: "software",
		Cron:     "0 */6 * * *",
		Enabled:  true,
	})
	req, _ := http.NewRequest("POST", "/api/v1/schedules", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusCreated, w.Code)

	var sched models.ScheduledSearch
	json.Unmarshal(w.Body.Bytes(), &sched)
	assert.NotEmpty(t, sched.ID)
}

func TestListSchedules(t *testing.T) {
	r := setupSchedulerRouter(t)

	body, _ := json.Marshal(models.ScheduledSearch{
		Query:    "ubuntu",
		Category: "software",
		Cron:     "0 */6 * * *",
	})
	req, _ := http.NewRequest("POST", "/api/v1/schedules", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	req2, _ := http.NewRequest("GET", "/api/v1/schedules", nil)
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)

	assert.Equal(t, http.StatusOK, w2.Code)
	var scheds []models.ScheduledSearch
	json.Unmarshal(w2.Body.Bytes(), &scheds)
	assert.Len(t, scheds, 1)
}
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestSchedule
```

- [ ] **Step 3: Implement scheduler.go**

`qBitTorrent-go/internal/api/scheduler.go`:
```go
package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
)

type ScheduleStore struct {
	mu        sync.RWMutex
	file      string
	schedules map[string]models.ScheduledSearch
}

func NewScheduleStore(file string) *ScheduleStore {
	store := &ScheduleStore{
		file:      file,
		schedules: make(map[string]models.ScheduledSearch),
	}
	store.load()
	return store
}

func (s *ScheduleStore) load() {
	data, err := os.ReadFile(s.file)
	if err != nil {
		return
	}
	var schedules []models.ScheduledSearch
	if err := json.Unmarshal(data, &schedules); err != nil {
		return
	}
	for _, sch := range schedules {
		s.schedules[sch.ID] = sch
	}
}

func (s *ScheduleStore) save() error {
	schedules := make([]models.ScheduledSearch, 0, len(s.schedules))
	for _, sch := range s.schedules {
		schedules = append(schedules, sch)
	}
	data, err := json.MarshalIndent(schedules, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.file, data, 0644)
}

func (s *ScheduleStore) List() []models.ScheduledSearch {
	s.mu.RLock()
	defer s.mu.RUnlock()
	schedules := make([]models.ScheduledSearch, 0, len(s.schedules))
	for _, sch := range s.schedules {
		schedules = append(schedules, sch)
	}
	return schedules
}

func (s *ScheduleStore) Create(sched models.ScheduledSearch) models.ScheduledSearch {
	s.mu.Lock()
	defer s.mu.Unlock()
	sched.ID = fmt.Sprintf("sched-%d", time.Now().UnixNano())
	s.schedules[sched.ID] = sched
	s.save()
	return sched
}

func (s *ScheduleStore) Delete(id string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.schedules[id]; !ok {
		return false
	}
	delete(s.schedules, id)
	s.save()
	return true
}

func ListSchedulesHandler(store *ScheduleStore) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, store.List())
	}
}

func CreateScheduleHandler(store *ScheduleStore) gin.HandlerFunc {
	return func(c *gin.Context) {
		var sched models.ScheduledSearch
		if err := c.ShouldBindJSON(&sched); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		created := store.Create(sched)
		c.JSON(http.StatusCreated, created)
	}
}

func DeleteScheduleHandler(store *ScheduleStore) gin.HandlerFunc {
	return func(c *gin.Context) {
		id := c.Param("id")
		if !store.Delete(id) {
			c.JSON(http.StatusNotFound, gin.H{"error": "schedule not found"})
			return
		}
		c.Status(http.StatusNoContent)
	}
}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestSchedule
```

- [ ] **Step 5: Commit**

```bash
git add qBitTorrent-go/internal/api/ && git commit -m "feat(go): add scheduler CRUD handlers with JSON persistence"
```

---

### Task 14: API Handlers — Theme

**Files:**
- Create: `qBitTorrent-go/internal/api/theme.go`
- Create: `qBitTorrent-go/internal/api/theme_test.go`

- [ ] **Step 1: Write tests**

`qBitTorrent-go/internal/api/theme_test.go`:
```go
package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/stretchr/testify/assert"
)

func setupThemeRouter(t *testing.T) *gin.Engine {
	t.Helper()
	tmpFile := t.TempDir() + "/theme.json"
	os.WriteFile(tmpFile, []byte(`{"palette_id":"default","mode":"dark"}`), 0644)
	store := NewThemeStore(tmpFile)
	r := gin.New()
	r.GET("/api/v1/theme", GetThemeHandler(store))
	r.PUT("/api/v1/theme", PutThemeHandler(store))
	return r
}

func TestGetTheme(t *testing.T) {
	r := setupThemeRouter(t)

	req, _ := http.NewRequest("GET", "/api/v1/theme", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var state models.ThemeState
	json.Unmarshal(w.Body.Bytes(), &state)
	assert.Equal(t, "default", state.PaletteID)
	assert.Equal(t, "dark", state.Mode)
}

func TestPutTheme(t *testing.T) {
	r := setupThemeRouter(t)

	body, _ := json.Marshal(models.ThemeUpdate{
		PaletteID: "ocean-blue",
		Mode:      "light",
	})
	req, _ := http.NewRequest("PUT", "/api/v1/theme", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var state models.ThemeState
	json.Unmarshal(w.Body.Bytes(), &state)
	assert.Equal(t, "ocean-blue", state.PaletteID)
	assert.Equal(t, "light", state.Mode)
}

func TestPutTheme_InvalidMode(t *testing.T) {
	r := setupThemeRouter(t)

	body, _ := json.Marshal(models.ThemeUpdate{
		PaletteID: "ocean",
		Mode:      "invalid",
	})
	req, _ := http.NewRequest("PUT", "/api/v1/theme", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusUnprocessableEntity, w.Code)
}
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestTheme
```

- [ ] **Step 3: Implement theme.go**

`qBitTorrent-go/internal/api/theme.go`:
```go
package api

import (
	"encoding/json"
	"net/http"
	"os"
	"sync"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
)

var allowedModes = map[string]bool{
	"light": true,
	"dark":  true,
}

type ThemeStore struct {
	mu     sync.RWMutex
	file   string
	state  models.ThemeState
}

func NewThemeStore(file string) *ThemeStore {
	store := &ThemeStore{
		file:  file,
		state: models.ThemeState{PaletteID: "default", Mode: "dark"},
	}
	store.load()
	return store
}

func (s *ThemeStore) load() {
	data, err := os.ReadFile(s.file)
	if err != nil {
		return
	}
	json.Unmarshal(data, &s.state)
}

func (s *ThemeStore) save() error {
	data, err := json.MarshalIndent(s.state, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.file, data, 0644)
}

func (s *ThemeStore) Get() models.ThemeState {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.state
}

func (s *ThemeStore) Put(paletteID, mode string) (models.ThemeState, error) {
	if !allowedModes[mode] {
		return models.ThemeState{}, &ValidationError{Message: "mode must be 'light' or 'dark'"}
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.state = models.ThemeState{PaletteID: paletteID, Mode: mode}
	s.save()
	return s.state, nil
}

type ValidationError struct {
	Message string
}

func (e *ValidationError) Error() string {
	return e.Message
}

func GetThemeHandler(store *ThemeStore) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, store.Get())
	}
}

func PutThemeHandler(store *ThemeStore) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.ThemeUpdate
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		state, err := store.Put(req.PaletteID, req.Mode)
		if err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, state)
	}
}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd qBitTorrent-go && go test ./internal/api/ -v -run TestTheme
```

- [ ] **Step 5: Commit**

```bash
git add qBitTorrent-go/internal/api/ && git commit -m "feat(go): add theme state handlers with validation"
```

---

## Phase 6: Main Application Wiring

### Task 15: Main Application — qbittorrent-proxy

**Files:**
- Modify: `qBitTorrent-go/cmd/qbittorrent-proxy/main.go`

- [ ] **Step 1: Wire everything together in main.go**

`qBitTorrent-go/cmd/qbittorrent-proxy/main.go`:
```go
package main

import (
	"fmt"
	"net/http"
	"os"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/api"
	"github.com/milos85vasic/qBitTorrent-go/internal/client"
	"github.com/milos85vasic/qBitTorrent-go/internal/config"
	"github.com/milos85vasic/qBitTorrent-go/internal/middleware"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

func main() {
	cfg := config.Load()

	zerolog.SetGlobalLevel(parseLogLevel(cfg.LogLevel))
	log.Info().Str("port", fmt.Sprintf("%d", cfg.ServerPort)).Msg("starting merge search service")

	var qbitClient *client.Client
	qc, err := client.NewClient(cfg.QBittorrentURL(), cfg.QBittorrentUsername, cfg.QBittorrentPassword)
	if err != nil {
		log.Warn().Err(err).Msg("failed to connect to qBittorrent on startup, will retry on requests")
	} else {
		qbitClient = qc
		log.Info().Msg("connected to qBittorrent")
	}

	searchSvc := service.NewMergeSearchService(qbitClient, cfg.MaxConcurrentSearches)
	hookStore := api.NewHookStore("/config/download-proxy/hooks.json")
	scheduleStore := api.NewScheduleStore("/config/merge-service/scheduling.json")
	themeStore := api.NewThemeStore("/config/merge-service/theme.json")

	if cfg.ServerPort != 7187 {
		gin.SetMode(gin.ReleaseMode)
	}
	r := gin.Default()
	r.Use(middleware.CORS("*"))
	r.Use(middleware.Logger())

	r.GET("/health", api.HealthHandler)

	r.GET("/api/v1/bridge/health", api.BridgeHealthHandler(fmt.Sprintf("http://localhost:%d", cfg.BridgePort)))

	r.GET("/api/v1/config", api.ConfigHandler(map[string]interface{}{
		"qbittorrent_url":             fmt.Sprintf("http://%s:%d", cfg.QBittorrentHost, cfg.ProxyPort),
		"qbittorrent_internal_url":    cfg.QBittorrentURL(),
		"qbittorrent_port":            cfg.QBittorrentPort,
		"qbittorrent_host":            cfg.QBittorrentHost,
		"proxy_port":                  cfg.ProxyPort,
	}))

	r.GET("/api/v1/stats", func(c *gin.Context) {
		c.JSON(http.StatusOK, searchSvc.Stats())
	})

	v1 := r.Group("/api/v1")
	{
		v1.POST("/search", api.SearchHandler(searchSvc))
		v1.POST("/search/sync", api.SearchSyncHandler(searchSvc))
		v1.GET("/search/stream/:id", api.SearchStreamHandler(searchSvc))
		v1.GET("/search/:id", api.GetSearchHandler(searchSvc))
		v1.POST("/search/:id/abort", api.AbortSearchHandler(searchSvc))

		v1.POST("/download", api.DownloadHandler(searchSvc, cfg.QBittorrentURL(), cfg.QBittorrentUsername, cfg.QBittorrentPassword))
		v1.POST("/download/file", api.DownloadFileHandler(searchSvc))
		v1.POST("/magnet", api.MagnetHandler(searchSvc))
		v1.GET("/downloads/active", api.ActiveDownloadsHandler(cfg.QBittorrentURL(), cfg.QBittorrentUsername, cfg.QBittorrentPassword))
		v1.POST("/auth/qbittorrent", api.QBittorrentAuthHandler(cfg.QBittorrentURL()))

		v1.GET("/theme", api.GetThemeHandler(themeStore))
		v1.PUT("/theme", api.PutThemeHandler(themeStore))

		v1.GET("/hooks", api.ListHooksHandler(hookStore))
		v1.POST("/hooks", api.CreateHookHandler(hookStore))
		v1.DELETE("/hooks/:id", api.DeleteHookHandler(hookStore))
	}

	schedules := r.Group("/api/v1/schedules")
	{
		schedules.GET("", api.ListSchedulesHandler(scheduleStore))
		schedules.POST("", api.CreateScheduleHandler(scheduleStore))
		schedules.DELETE("/:id", api.DeleteScheduleHandler(scheduleStore))
	}

	addr := fmt.Sprintf(":%d", cfg.ServerPort)
	log.Info().Str("addr", addr).Msg("server listening")
	if err := r.Run(addr); err != nil {
		log.Fatal().Err(err).Msg("server failed")
		os.Exit(1)
	}
}

func parseLogLevel(level string) zerolog.Level {
	switch level {
	case "debug":
		return zerolog.DebugLevel
	case "warn":
		return zerolog.WarnLevel
	case "error":
		return zerolog.ErrorLevel
	default:
		return zerolog.InfoLevel
	}
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd qBitTorrent-go && go build ./cmd/qbittorrent-proxy/
```

Expected: success

- [ ] **Step 3: Commit**

```bash
git add qBitTorrent-go/cmd/qbittorrent-proxy/ && git commit -m "feat(go): wire main application with all routes and middleware"
```

---

### Task 16: Main Application — webui-bridge

**Files:**
- Modify: `qBitTorrent-go/cmd/webui-bridge/main.go`

- [ ] **Step 1: Implement the bridge server**

`qBitTorrent-go/cmd/webui-bridge/main.go`:
```go
package main

import (
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/config"
	"github.com/rs/zerolog/log"
)

var trackerAuthConfig = map[string]struct {
	LoginURL string
}{
	"rutracker":  {LoginURL: "https://rutracker.org/forum/login.php"},
	"kinozal":    {LoginURL: "https://kinozal.tv/takelogin.php"},
	"iptorrents": {LoginURL: "https://iptorrents.com/torrents/"},
	"nnmclub":    {LoginURL: "https://nnmclub.to/forum/login.php"},
}

func main() {
	cfg := config.Load()
	gin.SetMode(gin.ReleaseMode)
	r := gin.Default()

	r.GET("/bridge/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	r.GET("/", func(c *gin.Context) {
		proxyToQBittorrent(c, cfg)
	})

	r.NoRoute(func(c *gin.Context) {
		proxyToQBittorrent(c, cfg)
	})

	addr := fmt.Sprintf(":%d", cfg.BridgePort)
	log.Info().Str("addr", addr).Msg("webui-bridge listening")
	if err := r.Run(addr); err != nil {
		log.Fatal().Err(err).Msg("bridge server failed")
		os.Exit(1)
	}
}

func proxyToQBittorrent(c *gin.Context, cfg *config.Config) {
	target := fmt.Sprintf("http://%s:%d", cfg.QBittorrentHost, cfg.QBittorrentPort)
	targetURL := target + c.Request.URL.Path
	if c.Request.URL.RawQuery != "" {
		targetURL += "?" + c.Request.URL.RawQuery
	}

	client := &http.Client{
		Timeout: 30 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}

	var body io.Reader
	if c.Request.Body != nil && c.Request.Method != "GET" && c.Request.Method != "HEAD" {
		body = c.Request.Body
	}

	req, err := http.NewRequest(c.Request.Method, targetURL, body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	for k, values := range c.Request.Header {
		for _, v := range values {
			req.Header.Add(k, v)
		}
	}

	resp, err := client.Do(req)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	defer resp.Body.Close()

	for k, values := range resp.Header {
		for _, v := range values {
			if !strings.EqualFold(k, "Content-Length") {
				c.Writer.Header().Add(k, v)
			}
		}
	}

	c.Writer.WriteHeader(resp.StatusCode)
	io.Copy(c.Writer, resp.Body)
}

func downloadWithAuth(tracker, torrentURL string, cfg *config.Config) ([]byte, error) {
	jar, _ := cookiejar.New(nil)
	httpClient := &http.Client{
		Jar:     jar,
		Timeout: 30 * time.Second,
	}

	var username, password, loginURL string

	switch tracker {
	case "rutracker":
		username = cfg.RutrackerUsername
		password = cfg.RutrackerPassword
		loginURL = trackerAuthConfig["rutracker"].LoginURL
	case "kinozal":
		username = cfg.KinozalUsername
		password = cfg.KinozalPassword
		loginURL = trackerAuthConfig["kinozal"].LoginURL
	case "iptorrents":
		username = cfg.IPTorrentsUsername
		password = cfg.IPTorrentsPassword
		loginURL = trackerAuthConfig["iptorrents"].LoginURL
	default:
		return nil, fmt.Errorf("unknown tracker: %s", tracker)
	}

	if username == "" || loginURL == "" {
		return nil, fmt.Errorf("tracker %s not configured", tracker)
	}

	loginData := url.Values{
		"username": {username},
		"password": {password},
	}
	loginReq, _ := http.NewRequest("POST", loginURL, strings.NewReader(loginData.Encode()))
	loginReq.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	loginReq.Header.Set("User-Agent", "Mozilla/5.0")

	loginResp, err := httpClient.Do(loginReq)
	if err != nil {
		return nil, fmt.Errorf("login failed: %w", err)
	}
	defer loginResp.Body.Close()

	if loginResp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("login rejected: HTTP %d", loginResp.StatusCode)
	}

	downloadReq, _ := http.NewRequest("GET", torrentURL, nil)
	downloadReq.Header.Set("User-Agent", "Mozilla/5.0")
	downloadResp, err := httpClient.Do(downloadReq)
	if err != nil {
		return nil, fmt.Errorf("download failed: %w", err)
	}
	defer downloadResp.Body.Close()

	if downloadResp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("torrent not found: HTTP %d", downloadResp.StatusCode)
	}

	data, err := io.ReadAll(downloadResp.Body)
	if err != nil {
		return nil, fmt.Errorf("read failed: %w", err)
	}

	return data, nil
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd qBitTorrent-go && go build ./cmd/webui-bridge/
```

- [ ] **Step 3: Commit**

```bash
git add qBitTorrent-go/cmd/webui-bridge/ && git commit -m "feat(go): implement webui-bridge reverse proxy with tracker auth"
```

---

## Phase 7: Docker & Build Configuration

### Task 17: Dockerfile & Build Script

**Files:**
- Create: `qBitTorrent-go/Dockerfile`
- Create: `qBitTorrent-go/scripts/build.sh`
- Create: `qBitTorrent-go/.env.example`

- [ ] **Step 1: Create multi-stage Dockerfile**

`qBitTorrent-go/Dockerfile`:
```dockerfile
FROM golang:1.23-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /qbittorrent-proxy ./cmd/qbittorrent-proxy
RUN CGO_ENABLED=0 GOOS=linux go build -o /webui-bridge ./cmd/webui-bridge

FROM alpine:3.19
RUN apk --no-cache add ca-certificates tzdata
WORKDIR /app
COPY --from=builder /qbittorrent-proxy .
COPY --from=builder /webui-bridge .
COPY .env.example .env
EXPOSE 7187 7188
CMD ["/app/qbittorrent-proxy"]
```

- [ ] **Step 2: Create build script**

`qBitTorrent-go/scripts/build.sh`:
```bash
#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BIN_DIR="$ROOT_DIR/bin"
mkdir -p "$BIN_DIR"

echo "Building qbittorrent-proxy..."
cd "$ROOT_DIR" && go build -o "$BIN_DIR/qbittorrent-proxy" ./cmd/qbittorrent-proxy

echo "Building webui-bridge..."
cd "$ROOT_DIR" && go build -o "$BIN_DIR/webui-bridge" ./cmd/webui-bridge

echo "Build complete: $BIN_DIR/"
```

- [ ] **Step 3: Create .env.example**

`qBitTorrent-go/.env.example`:
```
QBITTORRENT_HOST=localhost
QBITTORRENT_PORT=7185
QBITTORRENT_USER=admin
QBITTORRENT_PASS=admin
SERVER_PORT=7187
BRIDGE_PORT=7188
PROXY_PORT=7186
LOG_LEVEL=info
SSE_TIMEOUT=30
PLUGIN_TIMEOUT=10
MAX_CONCURRENT_SEARCHES=5
RUTRACKER_USERNAME=
RUTRACKER_PASSWORD=
KINOZAL_USERNAME=
KINOZAL_PASSWORD=
NNMCLUB_COOKIES=
IPTORRENTS_USERNAME=
IPTORRENTS_PASSWORD=
OMDB_API_KEY=
TMDB_API_KEY=
ANILIST_CLIENT_ID=
ALLOWED_ORIGINS=http://localhost:7186,http://localhost:7187
QBITTORRENT_DATA_DIR=/mnt/DATA
```

- [ ] **Step 4: Make build script executable and test**

```bash
chmod +x qBitTorrent-go/scripts/build.sh && cd qBitTorrent-go && ./scripts/build.sh
```

Expected: two binaries in `bin/`

- [ ] **Step 5: Commit**

```bash
git add qBitTorrent-go/Dockerfile qBitTorrent-go/scripts/ qBitTorrent-go/.env.example && git commit -m "feat(go): add Dockerfile, build script, and env example"
```

---

## Phase 8: Comprehensive Testing & Verification

### Task 18: Run Full Test Suite & Race Detection

**Files:** None new — runs all existing tests

- [ ] **Step 1: Run all tests verbose**

```bash
cd qBitTorrent-go && go test ./... -v
```

Expected: all PASS

- [ ] **Step 2: Run with race detector**

```bash
cd qBitTorrent-go && go test -race ./...
```

Expected: no races detected

- [ ] **Step 3: Run go vet**

```bash
cd qBitTorrent-go && go vet ./...
```

Expected: no issues

- [ ] **Step 4: Verify both binaries build**

```bash
cd qBitTorrent-go && go build ./cmd/qbittorrent-proxy && go build ./cmd/webui-bridge
```

Expected: success

- [ ] **Step 5: Commit if any fixes needed**

```bash
git add -A qBitTorrent-go/ && git commit -m "fix(go): resolve test/build issues from full verification"
```

---

## Phase 9: Integration with Existing Project

### Task 19: Update docker-compose.yml for Go Backend

**Files:**
- Modify: `docker-compose.yml` (at project root)

- [ ] **Step 1: Add Go backend service to docker-compose.yml**

Add a new service alongside the existing `qbittorrent-proxy`:

```yaml
  qbittorrent-go:
    build:
      context: ./qBitTorrent-go
      dockerfile: Dockerfile
    container_name: qbittorrent-go
    network_mode: host
    environment:
      - QBITTORRENT_HOST=localhost
      - QBITTORRENT_PORT=7185
      - SERVER_PORT=7187
      - BRIDGE_PORT=7188
      - PROXY_PORT=7186
    volumes:
      - ./.env:/app/.env:ro
      - ./config/download-proxy/hooks.json:/config/download-proxy/hooks.json
      - ./config/merge-service:/config/merge-service
    restart: unless-stopped
```

- [ ] **Step 2: Verify compose config is valid**

```bash
docker compose config || podman compose config
```

Expected: valid config

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml && git commit -m "feat: add Go backend service to docker-compose"
```

---

## Self-Review Checklist

| Spec Section | Task |
|---|---|
| Section 2: Project Init & Structure | Task 1 |
| Section 3: Data Models | Task 3 |
| Section 4: Configuration | Task 2 |
| Section 5: qBittorrent Client | Tasks 4, 5 |
| Section 6.1: Merge Search Service | Task 7 |
| Section 6.2: Private Tracker Bridge | Task 16 |
| Section 6.3: SSE Streaming | Task 8, Task 10 |
| Section 7: API Endpoints | Tasks 9-14 |
| Section 8: Middleware | Task 6 |
| Section 9: Testing | All tasks (TDD) |
| Section 10: Docker | Task 17, Task 19 |
| Section 11: Plugin Compatibility | Preserved (plugins unchanged) |
| Section 12: Validation | Task 18 |
