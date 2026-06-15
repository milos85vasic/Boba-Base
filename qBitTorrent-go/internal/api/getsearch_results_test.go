package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
	"github.com/stretchr/testify/assert"
)

// TestGetSearch_ReturnsResults is the §11.4.115 RED-on-broken-artifact
// regression guard for BUG-4: GetSearchHandler (the final GET the dashboard
// hits on search_complete) omitted Results entirely, so the Go-profile grid
// rendered empty after every search. We seed a completed search with 2 merged
// results via SetMergedResults, then GET /api/v1/search/{id} and assert the
// handler returns those 2 results.
func TestGetSearch_ReturnsResults(t *testing.T) {
	svc := service.NewMergeSearchService(nil, 5)
	meta := svc.StartSearch("ubuntu", "all", true, true)

	merged := []models.TorrentResult{
		{Name: "Ubuntu 22.04 ISO", Size: 4096, Seeds: 10, DownloadURLs: []string{"magnet:?xt=urn:btih:A"}},
		{Name: "Ubuntu 24.04 ISO", Size: 8192, Seeds: 20, DownloadURLs: []string{"magnet:?xt=urn:btih:B"}},
	}
	svc.SetMergedResults(meta.SearchID, merged, merged)
	meta.Status = "completed"
	meta.MergedResults = len(merged)

	r := gin.New()
	r.GET("/api/v1/search/:id", GetSearchHandler(svc))

	req, _ := http.NewRequest("GET", "/api/v1/search/"+meta.SearchID, nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var resp models.SearchResponse
	assert.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
	assert.Lenf(t, resp.Results, 2,
		"BUG-4: final GET must return the merged results, got %d", len(resp.Results))
	assert.Equal(t, "Ubuntu 22.04 ISO", resp.Results[0].Name)
}
