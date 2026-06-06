package service

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/milos85vasic/qBitTorrent-go/internal/client"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
)

type SearchMetadata struct {
	SearchID         string            `json:"search_id"`
	Query            string            `json:"query"`
	Category        string            `json:"category"`
	Status          string            `json:"status"`
	TotalResults    int               `json:"total_results"`
	MergedResults   int              `json:"merged_results"`
	TrackersSearched []string        `json:"trackers_searched"`
	Errors          []string         `json:"errors"`
	TrackerStats    map[string]*TrackerRunStat `json:"tracker_stats"`
	StartedAt       string          `json:"started_at"`
	CompletedAt     *string         `json:"completed_at,omitempty"`
	EnableMetadata  bool            `json:"-"`
	ValidateTrackers bool          `json:"-"`
}

type TrackerRunStat struct {
	Name           string `json:"name"`
	Status        string `json:"status"`
	Results       int    `json:"results"`
	DurationMS    int64  `json:"duration_ms"`
	Error         string `json:"error,omitempty"`
	Authenticated bool   `json:"authenticated"`
}

func (s *TrackerRunStat) ToDict() map[string]interface{} {
	return map[string]interface{}{
		"name":           s.Name,
		"status":         s.Status,
		"results":        s.Results,
		"duration_ms":    s.DurationMS,
		"error":          s.Error,
		"authenticated": s.Authenticated,
	}
}

func (m *SearchMetadata) ToDict() map[string]interface{} {
	stats := make([]map[string]interface{}, 0, len(m.TrackerStats))
	for _, s := range m.TrackerStats {
		stats = append(stats, s.ToDict())
	}
	return map[string]interface{}{
		"search_id":         m.SearchID,
		"query":             m.Query,
		"status":            m.Status,
		"total_results":     m.TotalResults,
		"merged_results":  m.MergedResults,
		"trackers_searched": m.TrackersSearched,
		"errors":           m.Errors,
		"tracker_stats":    stats,
		"started_at":       m.StartedAt,
		"completed_at":     m.CompletedAt,
	}
}

type MergeSearchService struct {
	qbitClient           *client.Client
	mu                   sync.RWMutex
	activeSearches       map[string]*SearchMetadata
	trackerResults       map[string][]models.TorrentResult
	lastMergedResults    map[string][][]models.TorrentResult
	maxConcurrentSearches int
}

func NewMergeSearchService(qc *client.Client, maxConcurrent int) *MergeSearchService {
	if maxConcurrent <= 0 {
		maxConcurrent = 5
	}
	return &MergeSearchService{
		qbitClient:           qc,
		activeSearches:      make(map[string]*SearchMetadata),
		trackerResults:       make(map[string][]models.TorrentResult),
		lastMergedResults:    make(map[string][][]models.TorrentResult),
		maxConcurrentSearches: maxConcurrent,
	}
}

func generateID() string {
	return fmt.Sprintf("%d", time.Now().UnixNano())
}

func (s *MergeSearchService) StartSearch(query, category string, enableMetadata, validateTrackers bool) *SearchMetadata {
	meta := &SearchMetadata{
		SearchID:         generateID(),
		Query:            query,
		Category:        category,
		Status:          "pending",
		TrackersSearched: []string{},
		Errors:           []string{},
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

func (s *MergeSearchService) SetMergedResults(searchID string, merged, all []models.TorrentResult) {
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

	if s.qbitClient == nil {
		return nil
	}

	searchIDInt, err := s.qbitClient.StartSearch(query, []string{"all"}, category)
	if err != nil {
		s.mu.Lock()
		if meta, ok := s.activeSearches[searchID]; ok {
			meta.Status = "failed"
			meta.Errors = append(meta.Errors, err.Error())
			now := time.Now().UTC().Format(time.RFC3339)
			meta.CompletedAt = &now
		}
		s.mu.Unlock()
		return err
	}

	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			_ = s.qbitClient.StopSearch(searchIDInt)
			return ctx.Err()
		case <-ticker.C:
			status, _ := s.qbitClient.SearchStatus(searchIDInt)
			results, total, _ := s.qbitClient.GetSearchResults(searchIDInt, 100, 0)

			s.mu.Lock()
			if meta, ok := s.activeSearches[searchID]; ok {
				meta.TotalResults = total
				for _, r := range results {
					s.trackerResults[searchID] = append(s.trackerResults[searchID], models.TorrentResult{
						Name:         r.FileName,
						Size:         r.FileSize,
						Seeds:        r.NbSeeders,
						Leechers:     r.NbLeechers,
						DownloadURLs: []string{r.FileURL},
						Tracker:      "qBittorrent",
						DescLink:     r.DescrLink,
					})
				}
				if status == "Stopped" {
					meta.Status = "completed"
					now := time.Now().UTC().Format(time.RFC3339)
					meta.CompletedAt = &now
					s.mu.Unlock()
					return nil
				}
			}
			s.mu.Unlock()
		}
	}
}

func (s *MergeSearchService) FetchTorrent(tracker, torrentURL string) ([]byte, error) {
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