package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
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
}

func TestSearchHandler_Async(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/api/v1/search", SearchHandler(svc))

	body, _ := json.Marshal(models.SearchRequest{Query: "ubuntu", Category: "all"})
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
	svc := service.NewMergeSearchService(nil, 1)
	r := gin.New()
	r.POST("/api/v1/search", SearchHandler(svc))

	body, _ := json.Marshal(models.SearchRequest{Query: "q1", Category: "all"})
	req, _ := http.NewRequest("POST", "/api/v1/search", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusOK, w.Code)

	w2 := httptest.NewRecorder()
	req2, _ := http.NewRequest("POST", "/api/v1/search", bytes.NewReader(body))
	req2.Header.Set("Content-Type", "application/json")
	r.ServeHTTP(w2, req2)
	assert.Equal(t, http.StatusTooManyRequests, w2.Code)
}

func TestGetSearchHandler_NotFound(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.GET("/api/v1/search/:id", GetSearchHandler(svc))
	req, _ := http.NewRequest("GET", "/api/v1/search/nonexistent", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusNotFound, w.Code)
}

func TestSearchStreamHandler_NotFound(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.GET("/api/v1/search/stream/:id", SearchStreamHandler(svc))
	req, _ := http.NewRequest("GET", "/api/v1/search/stream/nonexistent", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusNotFound, w.Code)
}

func TestAbortSearchHandler(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/api/v1/search", SearchHandler(svc))
	r.POST("/api/v1/search/:id/abort", AbortSearchHandler(svc))

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

func TestCreateHook(t *testing.T) {
	tmpFile := t.TempDir() + "/hooks.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewHookStore(tmpFile)
	r := gin.New()
	r.POST("/hooks", CreateHookHandler(store))

	body, _ := json.Marshal(models.Hook{URL: "https://example.com/webhook", Events: []string{"search_complete"}})
	req, _ := http.NewRequest("POST", "/hooks", bytes.NewReader(body))
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
	tmpFile := t.TempDir() + "/hooks.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewHookStore(tmpFile)
	store.Create(models.Hook{URL: "https://example.com", Events: []string{"search_complete"}})

	r := gin.New()
	r.GET("/hooks", ListHooksHandler(store))
	req, _ := http.NewRequest("GET", "/hooks", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusOK, w.Code)
	var hooks []models.Hook
	json.Unmarshal(w.Body.Bytes(), &hooks)
	assert.Len(t, hooks, 1)
}

func TestDeleteHook(t *testing.T) {
	tmpFile := t.TempDir() + "/hooks.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewHookStore(tmpFile)
	created := store.Create(models.Hook{URL: "https://example.com", Events: []string{"search_complete"}})

	r := gin.New()
	r.DELETE("/hooks/:id", DeleteHookHandler(store))
	req, _ := http.NewRequest("DELETE", "/hooks/"+created.ID, nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusNoContent, w.Code)
}

func TestDeleteHook_NotFound(t *testing.T) {
	tmpFile := t.TempDir() + "/hooks.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewHookStore(tmpFile)
	r := gin.New()
	r.DELETE("/hooks/:id", DeleteHookHandler(store))
	req, _ := http.NewRequest("DELETE", "/hooks/nonexistent", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusNotFound, w.Code)
}

func TestMagnetHandler(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/magnet", MagnetHandler(svc))

	body, _ := json.Marshal(map[string]interface{}{
		"result_id":     "test-result",
		"download_urls": []string{"magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=test"},
	})
	req, _ := http.NewRequest("POST", "/magnet", bytes.NewReader(body))
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

// TestMagnetHandler_SingleXtFromMergedSources is the RED-first regression guard
// (constitution §11.4.115). A merged search-results row aggregates many DISTINCT
// tracker-copies of the same content, each carrying a DIFFERENT infohash. A magnet
// identifies exactly ONE torrent, so it MUST carry exactly ONE xt=urn:btih: — the
// PRIMARY source (download_urls[0]'s hash, the best/highest-seeded copy). Joining
// every infohash produces a malformed multi-xt magnet qBittorrent rejects (confirmed
// live 2026-06-14: an Ubuntu merged row produced a 21-xt magnet). Trackers from ALL
// sources MUST still aggregate into that single torrent's magnet.
func TestMagnetHandler_SingleXtFromMergedSources(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/magnet", MagnetHandler(svc))

	const primaryHash = "1111111111111111111111111111111111111111"
	const secondaryHash = "2222222222222222222222222222222222222222"

	// Two distinct tracker-copies of the same content: different infohashes,
	// each with its own tracker.
	src1 := "magnet:?xt=urn:btih:" + primaryHash + "&tr=udp%3A%2F%2Ftracker.one%3A1111"
	src2 := "magnet:?xt=urn:btih:" + secondaryHash + "&tr=udp%3A%2F%2Ftracker.two%3A2222"

	body, _ := json.Marshal(map[string]interface{}{
		"result_id":     "merged-row",
		"download_urls": []string{src1, src2},
	})
	req, _ := http.NewRequest("POST", "/magnet", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	magnet, ok := resp["magnet"].(string)
	assert.True(t, ok)

	// EXACTLY ONE xt=urn:btih: in the magnet.
	assert.Equal(t, 1, strings.Count(magnet, "xt=urn:btih:"),
		"merged row must yield exactly one xt=urn:btih:, got magnet: %s", magnet)
	// The single xt is the PRIMARY (first) source's hash.
	assert.Contains(t, magnet, "xt=urn:btih:"+primaryHash)
	// The secondary source's hash must be ABSENT.
	assert.NotContains(t, magnet, secondaryHash,
		"secondary infohash must not appear in the magnet: %s", magnet)
	// Trackers from BOTH sources still aggregate into the single torrent's magnet.
	assert.Contains(t, magnet, "tracker.one")
	assert.Contains(t, magnet, "tracker.two")
}

func TestCreateSchedule(t *testing.T) {
	tmpFile := t.TempDir() + "/schedules.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewScheduleStore(tmpFile)
	r := gin.New()
	r.POST("/schedules", CreateScheduleHandler(store))

	body, _ := json.Marshal(models.ScheduledSearch{Query: "ubuntu", Category: "software", Cron: "0 */6 * * *", Enabled: true})
	req, _ := http.NewRequest("POST", "/schedules", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusCreated, w.Code)
	var sched models.ScheduledSearch
	json.Unmarshal(w.Body.Bytes(), &sched)
	assert.NotEmpty(t, sched.ID)
}

func TestGetTheme(t *testing.T) {
	tmpFile := t.TempDir() + "/theme.json"
	os.WriteFile(tmpFile, []byte(`{"palette_id":"default","mode":"dark"}`), 0644)
	store := NewThemeStore(tmpFile)
	r := gin.New()
	r.GET("/theme", GetThemeHandler(store))

	req, _ := http.NewRequest("GET", "/theme", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusOK, w.Code)
	var state models.ThemeState
	json.Unmarshal(w.Body.Bytes(), &state)
	assert.Equal(t, "default", state.PaletteID)
	assert.Equal(t, "dark", state.Mode)
}

func TestPutTheme(t *testing.T) {
	tmpFile := t.TempDir() + "/theme.json"
	os.WriteFile(tmpFile, []byte(`{"palette_id":"default","mode":"dark"}`), 0644)
	store := NewThemeStore(tmpFile)
	r := gin.New()
	r.PUT("/theme", PutThemeHandler(store))

	body, _ := json.Marshal(models.ThemeUpdate{PaletteID: "ocean-blue", Mode: "light"})
	req, _ := http.NewRequest("PUT", "/theme", bytes.NewReader(body))
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
	tmpFile := t.TempDir() + "/theme.json"
	os.WriteFile(tmpFile, []byte(`{"palette_id":"default","mode":"dark"}`), 0644)
	store := NewThemeStore(tmpFile)
	r := gin.New()
	r.PUT("/theme", PutThemeHandler(store))

	body, _ := json.Marshal(models.ThemeUpdate{PaletteID: "ocean", Mode: "invalid"})
	req, _ := http.NewRequest("PUT", "/theme", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusUnprocessableEntity, w.Code)
}
