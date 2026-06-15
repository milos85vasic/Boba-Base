package api

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
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

		searchID, query, category := meta.SearchID, meta.Query, req.Category
		go func() {
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			if err := svc.RunSearch(ctx, searchID, query, category); err != nil {
				return
			}
		}()

		c.JSON(http.StatusOK, models.SearchResponse{
			SearchID:         meta.SearchID,
			Query:            meta.Query,
			Status:           "running",
			TrackersSearched: meta.TrackersSearched,
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

		ctx := c.Request.Context()
		svc.RunSearch(ctx, meta.SearchID, req.Query, req.Category)

		results := svc.GetLiveResults(meta.SearchID)
		meta.Status = "completed"
		now := time.Now().UTC().Format(time.RFC3339)
		meta.CompletedAt = &now

		c.JSON(http.StatusOK, models.SearchResponse{
			SearchID:         meta.SearchID,
			Query:            meta.Query,
			Status:           "completed",
			Results:          results,
			TotalResults:     meta.TotalResults,
			MergedResults:    meta.MergedResults,
			TrackersSearched: meta.TrackersSearched,
			Errors:           meta.Errors,
			StartedAt:        meta.StartedAt,
			CompletedAt:      meta.CompletedAt,
		})
	}
}

func SearchStreamHandler(svc *service.MergeSearchService) gin.HandlerFunc {
	return func(c *gin.Context) {
		searchID := c.Param("id")
		meta, ok := svc.GetSearchStatus(searchID)
		if !ok || meta == nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "Search not found"})
			return
		}

		c.Header("Content-Type", "text/event-stream")
		c.Header("Cache-Control", "no-cache")
		c.Header("Connection", "keep-alive")
		c.Header("X-Accel-Buffering", "no")
		c.Writer.Flush()

	c.Writer.Write([]byte("event: search_start\ndata: {\"search_id\":\"" + searchID + "\",\"status\":\"started\"}\n\n"))
	c.Writer.Flush()

	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-c.Request.Context().Done():
			c.Writer.Write([]byte("event: close\ndata: {\"search_id\":\"" + searchID + "\",\"reason\":\"client_disconnected\"}\n\n"))
			c.Writer.Flush()
			return
		case <-ticker.C:
			currentMeta, ok := svc.GetSearchStatus(searchID)
			if !ok || currentMeta == nil {
				c.Writer.Write([]byte("event: error\ndata: {\"error\":\"Search not found\"}\n\n"))
				c.Writer.Flush()
				return
			}

			results := svc.GetLiveResults(searchID)
			if len(results) > 0 {
				data, _ := json.Marshal(results)
				c.Writer.Write([]byte("event: results\ndata: " + string(data) + "\n\n"))
				c.Writer.Flush()
			}

			if currentMeta.Status == "completed" || currentMeta.Status == "failed" || currentMeta.Status == "aborted" {
				data, _ := json.Marshal(currentMeta.ToDict())
				c.Writer.Write([]byte("event: search_complete\ndata: " + string(data) + "\n\n"))
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
		meta, ok := svc.GetSearchStatus(searchID)
		if !ok || meta == nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "Search not found"})
			return
		}

		// Return the merged result set the dashboard renders on completion.
		// Previously Results was omitted entirely, so the Go-profile grid was
		// always empty after a search (BUG-4). Fall back to the live set when
		// no merged snapshot has been stored yet (search still running).
		results, _ := svc.GetMergedResults(searchID)
		if results == nil {
			results = svc.GetLiveResults(searchID)
		}

		c.JSON(http.StatusOK, models.SearchResponse{
			SearchID:         meta.SearchID,
			Query:            meta.Query,
			Status:           meta.Status,
			Results:          results,
			TotalResults:     meta.TotalResults,
			MergedResults:    meta.MergedResults,
			TrackersSearched: meta.TrackersSearched,
			Errors:           meta.Errors,
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

