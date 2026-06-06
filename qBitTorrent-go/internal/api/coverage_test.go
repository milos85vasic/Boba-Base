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

// --- search handlers ---

func TestSearchHandler_BadJSON(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/api/v1/search", SearchHandler(svc))

	req, _ := http.NewRequest("POST", "/api/v1/search", strings.NewReader("{not-json"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusBadRequest, w.Code)
	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)
	assert.NotEmpty(t, body["error"])
}

func TestSearchSyncHandler_NilClientCompletes(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/api/v1/search/sync", SearchSyncHandler(svc))

	body, _ := json.Marshal(models.SearchRequest{Query: "ubuntu", Category: "all"})
	req, _ := http.NewRequest("POST", "/api/v1/search/sync", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var resp models.SearchResponse
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.Equal(t, "completed", resp.Status)
	assert.Equal(t, "ubuntu", resp.Query)
	assert.NotEmpty(t, resp.SearchID)
	assert.NotNil(t, resp.CompletedAt)
}

func TestSearchSyncHandler_BadJSON(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/api/v1/search/sync", SearchSyncHandler(svc))
	req, _ := http.NewRequest("POST", "/api/v1/search/sync", strings.NewReader("garbage"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusBadRequest, w.Code)
}

func TestSearchSyncHandler_QueueFull(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 1)
	svc.StartSearch("occupy", "all", false, false) // fills the single slot
	r := gin.New()
	r.POST("/api/v1/search/sync", SearchSyncHandler(svc))

	body, _ := json.Marshal(models.SearchRequest{Query: "q", Category: "all"})
	req, _ := http.NewRequest("POST", "/api/v1/search/sync", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusTooManyRequests, w.Code)
}

func TestGetSearchHandler_Found(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", false, false)
	r := gin.New()
	r.GET("/api/v1/search/:id", GetSearchHandler(svc))

	req, _ := http.NewRequest("GET", "/api/v1/search/"+meta.SearchID, nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusOK, w.Code)
	var resp models.SearchResponse
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.Equal(t, meta.SearchID, resp.SearchID)
	assert.Equal(t, "ubuntu", resp.Query)
	assert.Equal(t, "pending", resp.Status)
}

func TestAbortSearchHandler_NotFoundStatus(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/api/v1/search/:id/abort", AbortSearchHandler(svc))

	req, _ := http.NewRequest("POST", "/api/v1/search/nope/abort", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusOK, w.Code)
	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)
	assert.Equal(t, "nope", body["search_id"])
	assert.Equal(t, "not_found", body["status"])
}

func TestSearchStreamHandler_CompletesStream(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", false, false)
	// Pre-seed a live result and mark completed so the stream loop terminates.
	svc.AddTrackerResult(meta.SearchID, models.TorrentResult{Name: "Ubuntu", Seeds: 9})
	got := svc.GetSearchStatus(meta.SearchID)
	got.Status = "completed"

	r := gin.New()
	r.GET("/api/v1/search/stream/:id", SearchStreamHandler(svc))
	req, _ := http.NewRequest("GET", "/api/v1/search/stream/"+meta.SearchID, nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "text/event-stream", w.Header().Get("Content-Type"))
	out := w.Body.String()
	assert.Contains(t, out, "event: search_start")
	assert.Contains(t, out, "event: results")
	assert.Contains(t, out, `"Ubuntu"`)
	assert.Contains(t, out, "event: search_complete")
}

// --- download handlers ---

func TestDownloadHandler_AddsURLs(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/download", DownloadHandler(svc, "http://qbit", "admin", "admin"))

	body, _ := json.Marshal(models.DownloadRequest{
		ResultID:     "r1",
		DownloadURLs: []string{"magnet:?xt=1", "https://example.com/a.torrent"},
	})
	req, _ := http.NewRequest("POST", "/download", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var resp models.DownloadResult
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.Equal(t, "initiated", resp.Status)
	assert.Equal(t, 2, resp.URLsCount)
	assert.Equal(t, 2, resp.AddedCount)
	assert.Len(t, resp.Results, 2)
	assert.Equal(t, "added", resp.Results[0].Status)
}

func TestDownloadHandler_BadJSON(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/download", DownloadHandler(svc, "http://qbit", "u", "p"))
	req, _ := http.NewRequest("POST", "/download", strings.NewReader("nope"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusBadRequest, w.Code)
}

func TestDownloadFileHandler_Magnet(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/download-file", DownloadFileHandler(svc))

	magnet := "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"
	body, _ := json.Marshal(models.DownloadRequest{ResultID: "myres", DownloadURLs: []string{magnet}})
	req, _ := http.NewRequest("POST", "/download-file", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, magnet, w.Body.String())
	assert.Contains(t, w.Header().Get("Content-Disposition"), `myres.magnet`)
}

func TestDownloadFileHandler_FetchesTorrent(t *testing.T) {
	// Real local HTTP server serving torrent bytes (no external network).
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("d8:announce-torrent-bytes"))
	}))
	defer ts.Close()

	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/download-file", DownloadFileHandler(svc))

	body, _ := json.Marshal(models.DownloadRequest{ResultID: "res", DownloadURLs: []string{ts.URL + "/file.torrent"}})
	req, _ := http.NewRequest("POST", "/download-file", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "d8:announce-torrent-bytes", w.Body.String())
	assert.Equal(t, "application/x-bittorrent", w.Header().Get("Content-Type"))
	assert.Contains(t, w.Header().Get("Content-Disposition"), "file.torrent")
}

func TestDownloadFileHandler_NotFound(t *testing.T) {
	// Server returns 404 so the handler exhausts URLs and replies not-found.
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer ts.Close()

	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/download-file", DownloadFileHandler(svc))

	body, _ := json.Marshal(models.DownloadRequest{ResultID: "res", DownloadURLs: []string{"", ts.URL + "/x"}})
	req, _ := http.NewRequest("POST", "/download-file", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusNotFound, w.Code)
	var body2 map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body2)
	assert.Contains(t, body2["error"], "No downloadable")
}

func TestDownloadFileHandler_BadJSON(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/download-file", DownloadFileHandler(svc))
	req, _ := http.NewRequest("POST", "/download-file", strings.NewReader("x"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusBadRequest, w.Code)
}

func TestMagnetHandler_BadJSON(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/magnet", MagnetHandler(svc))
	req, _ := http.NewRequest("POST", "/magnet", strings.NewReader("x"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusBadRequest, w.Code)
}

func TestMagnetHandler_ParsesTrackersFromMagnet(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	r := gin.New()
	r.POST("/magnet", MagnetHandler(svc))

	// Input magnet carries an explicit tracker that must survive into output.
	in := "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&tr=" +
		"udp%3A%2F%2Fcustom.tracker%3A9999"
	body, _ := json.Marshal(map[string]interface{}{
		"result_id":     "my title",
		"download_urls": []string{in},
	})
	req, _ := http.NewRequest("POST", "/magnet", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	magnet := resp["magnet"].(string)
	assert.Contains(t, magnet, "btih:0123456789abcdef0123456789abcdef01234567")
	// dn is URL-escaped.
	assert.Contains(t, magnet, "dn=my+title")
	// custom tracker propagated (URL-escaped form of udp://custom.tracker:9999).
	assert.Contains(t, magnet, "custom.tracker")
	// default trackers also appended.
	assert.Contains(t, magnet, "opentrackr.org")
	hashes, ok := resp["hashes"].([]interface{})
	assert.True(t, ok)
	assert.Len(t, hashes, 1)
}

func TestActiveDownloadsHandler(t *testing.T) {
	r := gin.New()
	r.GET("/active", ActiveDownloadsHandler("http://qbit", "u", "p"))
	req, _ := http.NewRequest("GET", "/active", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusOK, w.Code)
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.Equal(t, float64(0), resp["count"])
}

func TestQBittorrentAuthHandler_Success(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		assert.Equal(t, "/api/v2/auth/login", req.URL.Path)
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("Ok."))
	}))
	defer ts.Close()

	r := gin.New()
	r.POST("/qbit-auth", QBittorrentAuthHandler(ts.URL))
	body, _ := json.Marshal(models.QBittorrentAuthRequest{Username: "admin", Password: "admin"})
	req, _ := http.NewRequest("POST", "/qbit-auth", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var resp models.QBittorrentAuthResponse
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.Equal(t, "authenticated", resp.Status)
}

func TestQBittorrentAuthHandler_InvalidCreds(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		w.Write([]byte("Fails."))
	}))
	defer ts.Close()

	r := gin.New()
	r.POST("/qbit-auth", QBittorrentAuthHandler(ts.URL))
	// Bad JSON triggers the default admin/admin fallback path too.
	req, _ := http.NewRequest("POST", "/qbit-auth", strings.NewReader("not-json"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusUnauthorized, w.Code)
	var resp models.QBittorrentAuthResponse
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.Equal(t, "failed", resp.Status)
}

func TestQBittorrentAuthHandler_Unreachable(t *testing.T) {
	r := gin.New()
	// Port 0 / closed endpoint -> client.PostForm returns an error.
	r.POST("/qbit-auth", QBittorrentAuthHandler("http://127.0.0.1:0"))
	body, _ := json.Marshal(models.QBittorrentAuthRequest{Username: "a", Password: "b"})
	req, _ := http.NewRequest("POST", "/qbit-auth", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusInternalServerError, w.Code)
	var resp models.QBittorrentAuthResponse
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.Equal(t, "error", resp.Status)
	assert.NotEmpty(t, resp.Error)
}

func TestBridgeHealthHandler_Healthy(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	r := gin.New()
	r.GET("/bridge", BridgeHealthHandler(ts.URL))
	req, _ := http.NewRequest("GET", "/bridge", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.Equal(t, true, resp["healthy"])
	assert.Equal(t, float64(200), resp["status_code"])
}

func TestBridgeHealthHandler_Unreachable(t *testing.T) {
	r := gin.New()
	r.GET("/bridge", BridgeHealthHandler("http://127.0.0.1:0"))
	req, _ := http.NewRequest("GET", "/bridge", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.Equal(t, false, resp["healthy"])
	assert.NotEmpty(t, resp["error"])
}

func TestConfigHandler(t *testing.T) {
	cfg := map[string]interface{}{"proxy_port": 7186, "merge_port": 7187}
	r := gin.New()
	r.GET("/config", ConfigHandler(cfg))
	req, _ := http.NewRequest("GET", "/config", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	assert.Equal(t, float64(7186), resp["proxy_port"])
	assert.Equal(t, float64(7187), resp["merge_port"])
}

// --- hooks / theme / schedule extra paths ---

func TestCreateHook_BadJSON(t *testing.T) {
	tmpFile := t.TempDir() + "/hooks.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewHookStore(tmpFile)
	r := gin.New()
	r.POST("/hooks", CreateHookHandler(store))
	req, _ := http.NewRequest("POST", "/hooks", strings.NewReader("x"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusBadRequest, w.Code)
}

func TestListHooks_Empty(t *testing.T) {
	tmpFile := t.TempDir() + "/hooks.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewHookStore(tmpFile)
	r := gin.New()
	r.GET("/hooks", ListHooksHandler(store))
	req, _ := http.NewRequest("GET", "/hooks", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusOK, w.Code)
	var hooks []models.Hook
	json.Unmarshal(w.Body.Bytes(), &hooks)
	assert.Len(t, hooks, 0)
}

func TestHookStore_PersistsAcrossReload(t *testing.T) {
	tmpFile := t.TempDir() + "/hooks.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewHookStore(tmpFile)
	created := store.Create(models.Hook{URL: "https://x", Events: []string{"e"}})

	// New store loads the saved file (covers load()).
	store2 := NewHookStore(tmpFile)
	list := store2.List()
	assert.Len(t, list, 1)
	assert.Equal(t, created.ID, list[0].ID)
}

func TestPutTheme_BadJSON(t *testing.T) {
	tmpFile := t.TempDir() + "/theme.json"
	os.WriteFile(tmpFile, []byte(`{"palette_id":"default","mode":"dark"}`), 0644)
	store := NewThemeStore(tmpFile)
	r := gin.New()
	r.PUT("/theme", PutThemeHandler(store))
	req, _ := http.NewRequest("PUT", "/theme", strings.NewReader("x"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusBadRequest, w.Code)
}

func TestThemeStore_PutPersistsAcrossReload(t *testing.T) {
	tmpFile := t.TempDir() + "/theme.json"
	os.WriteFile(tmpFile, []byte(`{"palette_id":"default","mode":"dark"}`), 0644)
	store := NewThemeStore(tmpFile)
	_, err := store.Put("ocean", "light")
	assert.NoError(t, err)

	// Reload from disk (covers load() reading saved state).
	store2 := NewThemeStore(tmpFile)
	got := store2.Get()
	assert.Equal(t, "ocean", got.PaletteID)
	assert.Equal(t, "light", got.Mode)
}

func TestValidationError_Error(t *testing.T) {
	e := &ValidationError{Message: "bad"}
	assert.Equal(t, "bad", e.Error())
}

func TestListSchedules(t *testing.T) {
	tmpFile := t.TempDir() + "/schedules.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewScheduleStore(tmpFile)
	store.Create(models.ScheduledSearch{Query: "ubuntu", Cron: "0 0 * * *", Enabled: true})

	r := gin.New()
	r.GET("/schedules", ListSchedulesHandler(store))
	req, _ := http.NewRequest("GET", "/schedules", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusOK, w.Code)
	var list []models.ScheduledSearch
	json.Unmarshal(w.Body.Bytes(), &list)
	assert.Len(t, list, 1)
	assert.Equal(t, "ubuntu", list[0].Query)
}

func TestCreateSchedule_BadJSON(t *testing.T) {
	tmpFile := t.TempDir() + "/schedules.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewScheduleStore(tmpFile)
	r := gin.New()
	r.POST("/schedules", CreateScheduleHandler(store))
	req, _ := http.NewRequest("POST", "/schedules", strings.NewReader("x"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusBadRequest, w.Code)
}

func TestDeleteSchedule(t *testing.T) {
	tmpFile := t.TempDir() + "/schedules.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewScheduleStore(tmpFile)
	created := store.Create(models.ScheduledSearch{Query: "q", Cron: "* * * * *", Enabled: true})

	r := gin.New()
	r.DELETE("/schedules/:id", DeleteScheduleHandler(store))
	req, _ := http.NewRequest("DELETE", "/schedules/"+created.ID, nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusNoContent, w.Code)

	// Reload to confirm it was actually removed from disk.
	store2 := NewScheduleStore(tmpFile)
	assert.Len(t, store2.List(), 0)
}

func TestDeleteSchedule_NotFound(t *testing.T) {
	tmpFile := t.TempDir() + "/schedules.json"
	os.WriteFile(tmpFile, []byte("[]"), 0644)
	store := NewScheduleStore(tmpFile)
	r := gin.New()
	r.DELETE("/schedules/:id", DeleteScheduleHandler(store))
	req, _ := http.NewRequest("DELETE", "/schedules/none", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	assert.Equal(t, http.StatusNotFound, w.Code)
}
