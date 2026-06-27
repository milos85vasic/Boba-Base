package service

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"github.com/milos85vasic/qBitTorrent-go/internal/client"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
)

// idCounter guarantees unique search IDs even when StartSearch is called
// multiple times within the same nanosecond (time.Now().UnixNano() is NOT
// unique under burst — two searches could collide on the same activeSearches
// key, silently dropping one and undercounting MAX_CONCURRENT_SEARCHES).
var idCounter atomic.Uint64

type SearchMetadata struct {
	SearchID         string                     `json:"search_id"`
	Query            string                     `json:"query"`
	Category         string                     `json:"category"`
	Status           string                     `json:"status"`
	TotalResults     int                        `json:"total_results"`
	MergedResults    int                        `json:"merged_results"`
	TrackersSearched []string                   `json:"trackers_searched"`
	Errors           []string                   `json:"errors"`
	TrackerStats     map[string]*TrackerRunStat `json:"tracker_stats"`
	StartedAt        string                     `json:"started_at"`
	CompletedAt      *string                    `json:"completed_at,omitempty"`
	EnableMetadata   bool                       `json:"-"`
	ValidateTrackers bool                       `json:"-"`
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
	stats := make([]map[string]interface{}, 0, len(m.TrackerStats))
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
	qbitClient            *client.Client
	mu                    sync.RWMutex
	activeSearches        map[string]*SearchMetadata
	trackerResults        map[string][]models.TorrentResult
	lastMergedResults     map[string][][]models.TorrentResult
	maxConcurrentSearches int
}

func NewMergeSearchService(qc *client.Client, maxConcurrent int) *MergeSearchService {
	if maxConcurrent <= 0 {
		maxConcurrent = 5
	}
	return &MergeSearchService{
		qbitClient:            qc,
		activeSearches:        make(map[string]*SearchMetadata),
		trackerResults:        make(map[string][]models.TorrentResult),
		lastMergedResults:     make(map[string][][]models.TorrentResult),
		maxConcurrentSearches: maxConcurrent,
	}
}

func generateID() string {
	return fmt.Sprintf("%d-%d", time.Now().UnixNano(), idCounter.Add(1))
}

func (s *MergeSearchService) StartSearch(query, category string, enableMetadata, validateTrackers bool) *SearchMetadata {
	meta, _ := s.TryStartSearch(query, category, enableMetadata, validateTrackers)
	return meta
}

func (s *MergeSearchService) TryStartSearch(query, category string, enableMetadata, validateTrackers bool) (*SearchMetadata, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	running := 0
	for _, meta := range s.activeSearches {
		if meta.Status == "pending" || meta.Status == "running" {
			running++
		}
	}
	if running >= s.maxConcurrentSearches {
		return nil, false
	}

	meta := &SearchMetadata{
		SearchID:         generateID(),
		Query:            query,
		Category:         category,
		Status:           "pending",
		TrackersSearched: []string{},
		Errors:           []string{},
		TrackerStats:     make(map[string]*TrackerRunStat),
		StartedAt:        time.Now().UTC().Format(time.RFC3339),
		EnableMetadata:   enableMetadata,
		ValidateTrackers: validateTrackers,
	}

	s.activeSearches[meta.SearchID] = meta
	s.trackerResults[meta.SearchID] = []models.TorrentResult{}
	return meta, true
}

// GetSearchStatus returns the metadata for searchID. The comma-ok return makes
// the missing-vs-present contract explicit: a missing id yields (nil, false),
// a present id yields (meta, true). Callers MUST check ok before dereferencing.
func (s *MergeSearchService) GetSearchStatus(searchID string) (*SearchMetadata, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	meta, ok := s.activeSearches[searchID]
	return meta, ok
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

	// seen tracks the dedup key (FileURL, falling back to name+size when the
	// URL is empty) of every result already accumulated for this search.
	// Without it the fixed offset-0 poll re-appended the same rows on every
	// tick (BUG-3): the live set grew unbounded with duplicates and the merged
	// count was never computed.
	seen := make(map[string]struct{})

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
					tr := models.TorrentResult{
						Name:         r.FileName,
						Size:         r.FileSize,
						Seeds:        r.NbSeeders,
						Leechers:     r.NbLeechers,
						DownloadURLs: []string{r.FileURL},
						Tracker:      "qBittorrent",
						DescLink:     r.DescrLink,
					}
					key := dedupKey(tr)
					if _, dup := seen[key]; dup {
						continue
					}
					seen[key] = struct{}{}
					s.trackerResults[searchID] = append(s.trackerResults[searchID], tr)
				}
				if status == "Stopped" {
					// Snapshot the deduplicated accumulation as the merged
					// set and record the merged count so GetMergedResults and
					// SearchResponse.MergedResults reflect reality (BUG-3 /
					// BUG-4).
					merged := append([]models.TorrentResult(nil), s.trackerResults[searchID]...)
					s.lastMergedResults[searchID] = [][]models.TorrentResult{merged, merged}
					meta.MergedResults = len(merged)
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

// dedupKey derives a stable identity for a result. FileURL (magnet/infohash
// or download link) is the strongest signal; when absent we fall back to
// name+size so identical rows still collapse.
func dedupKey(r models.TorrentResult) string {
	if len(r.DownloadURLs) > 0 && r.DownloadURLs[0] != "" {
		return r.DownloadURLs[0]
	}
	return fmt.Sprintf("%s|%v", r.Name, r.Size)
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
