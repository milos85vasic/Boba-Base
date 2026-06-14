package api

// Constitution §11.4.85 STRESS + CHAOS coverage for the Go backend magnet/download
// path — the Go parity of the single-xt MagnetHandler fix.
//
// These tests exercise the REAL MagnetHandler via httptest (no real qBittorrent).
// They prove USER-OBSERVABLE outcomes per §11.4 / §11.4.69:
//   - the produced magnet carries EXACTLY ONE xt=urn:btih: (strings.Count == 1),
//     and that single xt is the PRIMARY (first-source) infohash;
//   - httptest status codes (200 for well-formed, 400 for malformed JSON);
//   - the handler NEVER panics under adversarial / fault-injected input;
//   - a captured latency-distribution artefact is written to disk and is non-empty.
//
// Evidence (§11.4.5 / §11.4.69 captured-evidence): qa-results/go_magnet_stress/local/.
//
// HOST SAFETY (§12): run only via `GOMAXPROCS=2 nice -n 19 go test ...`.

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/service"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// xtCount returns how many xt=urn:btih: tokens appear in a magnet — the
// single load-bearing user-observable invariant of the fix.
func xtCount(magnet string) int { return strings.Count(magnet, "xt=urn:btih:") }

// newMagnetRouter wires the REAL MagnetHandler exactly as production routes it.
func newMagnetRouter() *gin.Engine {
	svc := service.NewMergeSearchService(nil, 256)
	r := gin.New()
	r.POST("/magnet", MagnetHandler(svc))
	return r
}

// callMagnet posts a body to the real handler and returns (status, magnet, ok).
// rawBody, when non-nil, is sent verbatim (for malformed-JSON chaos); otherwise
// the resultID + urls are marshalled into the standard request shape.
func callMagnet(r *gin.Engine, resultID string, urls []string, rawBody []byte) (int, string, bool) {
	var payload []byte
	if rawBody != nil {
		payload = rawBody
	} else {
		payload, _ = json.Marshal(map[string]interface{}{
			"result_id":     resultID,
			"download_urls": urls,
		})
	}
	req, _ := http.NewRequest("POST", "/magnet", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		return w.Code, "", false
	}
	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		return w.Code, "", false
	}
	magnet, ok := resp["magnet"].(string)
	return w.Code, magnet, ok
}

// magnetWithHash builds a single tracker-copy magnet for a 40-char btih.
func magnetWithHash(hash, tracker string) string {
	return "magnet:?xt=urn:btih:" + hash + "&tr=" + tracker
}

// hash40 produces a deterministic distinct 40-hex-char infohash from an int.
func hash40(n int) string {
	const hexd = "0123456789abcdef"
	b := make([]byte, 40)
	v := n + 1 // avoid all-zero so it's clearly distinct
	for i := 39; i >= 0; i-- {
		b[i] = hexd[v&0xf]
		v >>= 4
		if v == 0 {
			// pad the rest with a position-derived nibble to keep 40 distinct hexes
			for j := i - 1; j >= 0; j-- {
				b[j] = hexd[(n+j)&0xf]
			}
			break
		}
	}
	return string(b)
}

// latencyStats is the captured-evidence summary (§11.4.85 stress: p50/p95/p99).
type latencyStats struct {
	Category       string    `json:"category"`
	Iterations     int       `json:"iterations"`
	SingleXtPasses int       `json:"single_xt_passes"`
	PrimaryXtMatch int       `json:"primary_xt_match"`
	MinNanos       int64     `json:"min_nanos"`
	MaxNanos       int64     `json:"max_nanos"`
	MeanNanos      int64     `json:"mean_nanos"`
	P50Nanos       int64     `json:"p50_nanos"`
	P95Nanos       int64     `json:"p95_nanos"`
	P99Nanos       int64     `json:"p99_nanos"`
	GeneratedAt    time.Time `json:"generated_at"`
}

func evidenceDir(t *testing.T) string {
	// internal/api/  ->  module root is two levels up; qa-results lives at module root.
	dir := filepath.Join("..", "..", "qa-results", "go_magnet_stress", "local")
	require.NoError(t, os.MkdirAll(dir, 0o755))
	return dir
}

func writeLatencyEvidence(t *testing.T, name string, stats latencyStats) {
	dir := evidenceDir(t)
	path := filepath.Join(dir, name)
	data, err := json.MarshalIndent(stats, "", "  ")
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(path, data, 0o644))

	// Anti-bluff: the captured-evidence file MUST exist and be non-empty.
	info, err := os.Stat(path)
	require.NoError(t, err, "evidence file must exist: %s", path)
	require.Greater(t, info.Size(), int64(0), "evidence file must be non-empty: %s", path)
	t.Logf("§11.4.85 evidence written: %s (%d bytes)", path, info.Size())
}

func summarize(category string, durations []time.Duration, singleXt, primaryMatch int) latencyStats {
	sorted := append([]time.Duration(nil), durations...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i] < sorted[j] })
	pick := func(p float64) int64 {
		if len(sorted) == 0 {
			return 0
		}
		idx := int(p * float64(len(sorted)-1))
		return sorted[idx].Nanoseconds()
	}
	var sum int64
	for _, d := range durations {
		sum += d.Nanoseconds()
	}
	mean := int64(0)
	if len(durations) > 0 {
		mean = sum / int64(len(durations))
	}
	return latencyStats{
		Category:       category,
		Iterations:     len(durations),
		SingleXtPasses: singleXt,
		PrimaryXtMatch: primaryMatch,
		MinNanos:       pick(0),
		MaxNanos:       pick(1),
		MeanNanos:      mean,
		P50Nanos:       pick(0.50),
		P95Nanos:       pick(0.95),
		P99Nanos:       pick(0.99),
		GeneratedAt:    time.Now().UTC(),
	}
}

// ---------------------------------------------------------------------------
// STRESS — sustained load (§11.4.85 stress: N>=100 iterations + per-iter latency)
// ---------------------------------------------------------------------------

func TestMagnetHandler_Stress_SustainedLoad(t *testing.T) {
	r := newMagnetRouter()

	const iterations = 250
	durations := make([]time.Duration, 0, iterations)
	singleXt, primaryMatch := 0, 0

	for i := 0; i < iterations; i++ {
		// Vary 1..50 distinct tracker-copies (distinct infohashes) per row.
		n := (i % 50) + 1
		urls := make([]string, n)
		for j := 0; j < n; j++ {
			urls[j] = magnetWithHash(hash40(i*97+j), "udp%3A%2F%2Ftr"+hash40(j)[:4]+"%3A6969")
		}
		primary := hash40(i * 97) // download_urls[0]'s hash

		start := time.Now()
		status, magnet, ok := callMagnet(r, "row-"+hash40(i)[:8], urls, nil)
		durations = append(durations, time.Since(start))

		require.Equal(t, http.StatusOK, status, "iter %d", i)
		require.True(t, ok, "iter %d: magnet field present", i)

		// USER-OBSERVABLE: EXACTLY ONE xt=urn:btih:.
		if assert.Equal(t, 1, xtCount(magnet),
			"iter %d (n=%d): exactly one xt=urn:btih: required, got magnet=%s", i, n, magnet) {
			singleXt++
		}
		// The single xt MUST be the PRIMARY (first) source.
		if assert.Contains(t, magnet, "xt=urn:btih:"+primary,
			"iter %d: single xt must be the primary infohash", i) {
			primaryMatch++
		}
	}

	require.Equal(t, iterations, singleXt, "every iteration must yield exactly one xt")
	require.Equal(t, iterations, primaryMatch, "every iteration's xt must be the primary")

	stats := summarize("stress_sustained_load", durations, singleXt, primaryMatch)
	writeLatencyEvidence(t, "latency.json", stats)
	t.Logf("sustained-load: %d iters, p50=%dns p95=%dns p99=%dns max=%dns; single-xt=%d/%d",
		stats.Iterations, stats.P50Nanos, stats.P95Nanos, stats.P99Nanos, stats.MaxNanos, singleXt, iterations)
}

// ---------------------------------------------------------------------------
// STRESS — concurrent contention + race (run with -race)
// ---------------------------------------------------------------------------

func TestMagnetHandler_Stress_ConcurrentContention(t *testing.T) {
	r := newMagnetRouter()

	const workers = 32 // >= 20 concurrent calls
	var wg sync.WaitGroup
	var mu sync.Mutex
	failures := []string{}
	durations := make([]time.Duration, 0, workers)
	singleXt := 0

	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			n := (id % 30) + 1
			urls := make([]string, n)
			for j := 0; j < n; j++ {
				urls[j] = magnetWithHash(hash40(id*131+j), "udp%3A%2F%2Fc"+hash40(j)[:4]+"%3A80")
			}
			primary := hash40(id * 131)

			start := time.Now()
			status, magnet, ok := callMagnet(r, "c-"+hash40(id)[:8], urls, nil)
			d := time.Since(start)

			mu.Lock()
			defer mu.Unlock()
			durations = append(durations, d)
			if status != http.StatusOK || !ok {
				failures = append(failures, "worker "+hash40(id)[:6]+": bad status/missing magnet")
				return
			}
			if xtCount(magnet) != 1 {
				failures = append(failures, "worker "+hash40(id)[:6]+": multi-xt magnet "+magnet)
				return
			}
			if !strings.Contains(magnet, "xt=urn:btih:"+primary) {
				failures = append(failures, "worker "+hash40(id)[:6]+": xt not primary")
				return
			}
			singleXt++
		}(w)
	}
	wg.Wait()

	require.Empty(t, failures, "concurrent contention produced failures: %v", failures)
	require.Equal(t, workers, singleXt, "every concurrent call must yield exactly one primary xt")

	stats := summarize("stress_concurrent_contention", durations, singleXt, singleXt)
	writeLatencyEvidence(t, "concurrent_latency.json", stats)
	t.Logf("concurrent: %d workers, all single-xt, p95=%dns max=%dns", workers, stats.P95Nanos, stats.MaxNanos)
}

// ---------------------------------------------------------------------------
// STRESS — boundary conditions
// ---------------------------------------------------------------------------

func TestMagnetHandler_Stress_Boundaries(t *testing.T) {
	r := newMagnetRouter()

	t.Run("empty_download_urls_yields_no_xt", func(t *testing.T) {
		status, magnet, ok := callMagnet(r, "empty", []string{}, nil)
		require.Equal(t, http.StatusOK, status)
		require.True(t, ok)
		assert.True(t, strings.HasPrefix(magnet, "magnet:?"),
			"must still be a well-formed magnet: %s", magnet)
		assert.Equal(t, 0, xtCount(magnet), "no sources => no xt: %s", magnet)
	})

	t.Run("single_magnet_yields_one_xt", func(t *testing.T) {
		h := hash40(7)
		status, magnet, ok := callMagnet(r, "single", []string{magnetWithHash(h, "udp%3A%2F%2Ft%3A1")}, nil)
		require.Equal(t, http.StatusOK, status)
		require.True(t, ok)
		assert.Equal(t, 1, xtCount(magnet), "single source => one xt: %s", magnet)
		assert.Contains(t, magnet, "xt=urn:btih:"+h)
	})

	t.Run("thousand_distinct_infohashes_yield_one_xt", func(t *testing.T) {
		const n = 1000
		urls := make([]string, n)
		for j := 0; j < n; j++ {
			urls[j] = magnetWithHash(hash40(j*3+1), "udp%3A%2F%2Fk%3A6969")
		}
		primary := hash40(1)
		status, magnet, ok := callMagnet(r, "thousand", urls, nil)
		require.Equal(t, http.StatusOK, status)
		require.True(t, ok)
		assert.Equal(t, 1, xtCount(magnet), "1000 sources must still yield exactly one xt")
		assert.Contains(t, magnet, "xt=urn:btih:"+primary, "xt must be the primary (first) source")
	})

	t.Run("malformed_no_btih_mixed_with_valid_uses_valid_primary", func(t *testing.T) {
		valid := hash40(42)
		urls := []string{
			"magnet:?dn=junk&tr=udp%3A%2F%2Fno-hash%3A1",   // no btih at all
			"https://example.test/file.torrent",            // non-magnet URL, no btih
			magnetWithHash(valid, "udp%3A%2F%2Fgood%3A80"), // the only valid source
		}
		status, magnet, ok := callMagnet(r, "mixed", urls, nil)
		require.Equal(t, http.StatusOK, status)
		require.True(t, ok)
		// btihRe scans ALL urls; only the valid one has a btih => it becomes hashes[0].
		assert.Equal(t, 1, xtCount(magnet), "exactly one xt from the only valid btih: %s", magnet)
		assert.Contains(t, magnet, "xt=urn:btih:"+valid)
	})

	t.Run("non_magnet_url_only_yields_no_xt", func(t *testing.T) {
		status, magnet, ok := callMagnet(r, "url-only", []string{"https://example.test/a.torrent"}, nil)
		require.Equal(t, http.StatusOK, status)
		require.True(t, ok)
		assert.Equal(t, 0, xtCount(magnet), "non-magnet URL with no btih => no xt: %s", magnet)
	})
}

// ---------------------------------------------------------------------------
// CHAOS — input-fault injection. Handler must NEVER panic; always a clean
// 2xx/4xx. A panic in the handler crashes the gin worker -> go test reports it.
// ---------------------------------------------------------------------------

func TestMagnetHandler_Chaos_MalformedAndAdversarialInput(t *testing.T) {
	r := newMagnetRouter()

	hugeURL := "magnet:?xt=urn:btih:" + hash40(5) + "&dn=" + strings.Repeat("A", 100_000)
	ctrlChars := "magnet:?xt=urn:btih:" + hash40(6) + "&dn=" +
		string([]byte{0x00, 0x01, 0x02, 0x07, 0x1b, 0x7f}) + "￿​"
	unicodeName := "magnet:?xt=urn:btih:" + hash40(8) + "&dn=" + "日本語テスト🎬mix"

	cases := []struct {
		name   string
		raw    []byte   // raw body (mutually exclusive with urls)
		urls   []string // normal-shape body
		expect int      // expected HTTP status
	}{
		{name: "malformed_json", raw: []byte("{not-json"), expect: http.StatusBadRequest},
		{name: "empty_body", raw: []byte(""), expect: http.StatusBadRequest},
		{name: "array_instead_of_object", raw: []byte("[1,2,3]"), expect: http.StatusBadRequest},
		{name: "json_null_body", raw: []byte("null"), expect: http.StatusOK}, // binds to zero-value struct
		{name: "missing_fields_empty_object", raw: []byte("{}"), expect: http.StatusOK},
		{name: "null_download_urls", raw: []byte(`{"result_id":"x","download_urls":null}`), expect: http.StatusOK},
		{name: "wrong_type_download_urls", raw: []byte(`{"download_urls":"not-an-array"}`), expect: http.StatusBadRequest},
		{name: "huge_download_url", urls: []string{hugeURL}, expect: http.StatusOK},
		{name: "control_chars", urls: []string{ctrlChars}, expect: http.StatusOK},
		{name: "unicode_name", urls: []string{unicodeName}, expect: http.StatusOK},
		{name: "empty_string_entries", urls: []string{"", "", ""}, expect: http.StatusOK},
		{name: "deeply_nested_garbage", raw: []byte(`{"download_urls":[{"x":1}]}`), expect: http.StatusBadRequest},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			// require.NotPanics asserts the user-observable no-panic outcome.
			require.NotPanics(t, func() {
				status, magnet, _ := callMagnet(r, "chaos", tc.urls, tc.raw)
				assert.Equal(t, tc.expect, status, "case %s: clean status, no panic-500", tc.name)
				if status == http.StatusOK && magnet != "" {
					// Any successful magnet must remain single-xt-bounded.
					assert.LessOrEqual(t, xtCount(magnet), 1,
						"case %s: at most one xt: %s", tc.name, magnet)
				}
			})
		})
	}
}

// ---------------------------------------------------------------------------
// CHAOS / STRESS — adversarial 10000-entry payload: bounded, single-xt, fast.
// ---------------------------------------------------------------------------

func TestMagnetHandler_Chaos_TenThousandEntries(t *testing.T) {
	r := newMagnetRouter()

	const n = 10_000
	urls := make([]string, n)
	for j := 0; j < n; j++ {
		urls[j] = magnetWithHash(hash40(j*7+3), "udp%3A%2F%2Fz%3A6969")
	}
	primary := hash40(3)

	start := time.Now()
	var status int
	var magnet string
	var ok bool
	require.NotPanics(t, func() {
		status, magnet, ok = callMagnet(r, "ten-k", urls, nil)
	})
	elapsed := time.Since(start)

	require.Equal(t, http.StatusOK, status)
	require.True(t, ok)
	assert.Equal(t, 1, xtCount(magnet), "10000 sources must still yield exactly one xt")
	assert.Contains(t, magnet, "xt=urn:btih:"+primary, "xt must be the primary (first) source")
	assert.Less(t, elapsed, 5*time.Second, "10000-entry magnet must complete under a sane bound, took %v", elapsed)
	t.Logf("ten-thousand-entry: bounded, single-xt, completed in %v", elapsed)
}
