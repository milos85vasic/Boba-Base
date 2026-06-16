package jackett

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"github.com/milos85vasic/qBitTorrent-go/internal/db"
	"github.com/milos85vasic/qBitTorrent-go/internal/db/repos"
)

// harness wires a fresh on-disk SQLite DB, real repos, and a stub Jackett
// httptest.Server into AutoconfigDeps so each test exercises the orchestrator
// against real persistence — no mocks beyond the HTTP server fixture.
type harness struct {
	deps    AutoconfigDeps
	server  *httptest.Server
	cleanup func()
}

func newHarness(t *testing.T, handler http.Handler) *harness {
	t.Helper()
	dir := t.TempDir()
	conn, err := db.Open(filepath.Join(dir, "t.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	if err := db.Migrate(conn); err != nil {
		t.Fatalf("Migrate: %v", err)
	}
	// Zeroed key is fine for tests — encrypt/decrypt round-trip works
	// regardless of key entropy. Production callers source via Bootstrap.
	key := make([]byte, 32)
	srv := httptest.NewServer(handler)
	deps := AutoconfigDeps{
		Creds:     repos.NewCredentials(conn, key),
		Overrides: repos.NewOverrides(conn),
		Indexers:  repos.NewIndexers(conn),
		Runs:      repos.NewRuns(conn),
		Client:    NewClient(srv.URL, "test-api-key"),
	}
	return &harness{
		deps:   deps,
		server: srv,
		cleanup: func() {
			srv.Close()
			conn.Close()
		},
	}
}

func acStrPtr(s string) *string { return &s }

func TestAutoconfigureNoCredentials(t *testing.T) {
	h := newHarness(t, http.NotFoundHandler())
	defer h.cleanup()

	res := Autoconfigure(h.deps, nil)

	if len(res.DiscoveredCredentials) != 0 {
		t.Fatalf("expected no creds: %+v", res)
	}
	if len(res.Errors) != 0 {
		t.Fatalf("expected no errors: %+v", res.Errors)
	}
	// Run row is still inserted so the dashboard shows a "no creds" entry.
	runs, err := h.deps.Runs.List(10)
	if err != nil {
		t.Fatalf("list runs: %v", err)
	}
	if len(runs) != 1 {
		t.Fatalf("expected 1 run row, got %d", len(runs))
	}
	if runs[0].DiscoveredCount != 0 || runs[0].ConfiguredNowCount != 0 {
		t.Fatalf("expected zero counts: %+v", runs[0])
	}
}

func TestAutoconfigureMissingAPIKey(t *testing.T) {
	h := newHarness(t, http.NotFoundHandler())
	defer h.cleanup()
	// Replace client with empty api key.
	h.deps.Client = NewClient(h.server.URL, "")
	if err := h.deps.Creds.Upsert("RUTRACKER", "userpass", acStrPtr("u"), acStrPtr("p"), nil); err != nil {
		t.Fatalf("seed creds: %v", err)
	}

	res := Autoconfigure(h.deps, nil)

	if len(res.Errors) == 0 || res.Errors[0] != "jackett_auth_missing_key" {
		t.Fatalf("expected jackett_auth_missing_key, got %+v", res.Errors)
	}
	if len(res.DiscoveredCredentials) != 1 || res.DiscoveredCredentials[0] != "RUTRACKER" {
		t.Fatalf("discovered: %+v", res.DiscoveredCredentials)
	}
	// Run row recorded with the discovered count.
	runs, _ := h.deps.Runs.List(10)
	if len(runs) != 1 || runs[0].DiscoveredCount != 1 {
		t.Fatalf("run row: %+v", runs)
	}
}

func TestAutoconfigureNoCompatibleFields(t *testing.T) {
	// An indexer template that requires a "cookie" field, paired with a
	// userpass credential. FillFields fills nothing → skip with the
	// no_compatible_credential_fields_for_indexer error.
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == "POST" && r.URL.Path == "/UI/Dashboard":
			w.WriteHeader(302)
		case r.URL.Path == "/api/v2.0/indexers" && r.Method == "GET":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`[{"id":"iptorrents","name":"IPTorrents","type":"private","configured":false}]`))
		case strings.HasSuffix(r.URL.Path, "/iptorrents/config") && r.Method == "GET":
			// Template only declares cookie field.
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`[{"id":"cookie","type":"hidden","value":""}]`))
		default:
			t.Errorf("unexpected request: %s %s", r.Method, r.URL.Path)
			w.WriteHeader(500)
		}
	})
	h := newHarness(t, handler)
	defer h.cleanup()
	if err := h.deps.Creds.Upsert("IPTORRENTS", "userpass", acStrPtr("u"), acStrPtr("p"), nil); err != nil {
		t.Fatalf("seed creds: %v", err)
	}

	res := Autoconfigure(h.deps, nil)

	if len(res.Errors) == 0 {
		t.Fatalf("expected error, got %+v", res)
	}
	found := false
	for _, e := range res.Errors {
		if strings.Contains(e, "no_compatible_credential_fields_for_indexer") {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("expected no_compatible_credential_fields_for_indexer, got %+v", res.Errors)
	}
}

func TestAutoconfigureHappyPath(t *testing.T) {
	var gotConfig string
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == "POST" && r.URL.Path == "/UI/Dashboard":
			w.WriteHeader(302)
		case r.URL.Path == "/api/v2.0/indexers" && r.Method == "GET":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`[{"id":"rutracker","name":"RuTracker","type":"private","configured":false}]`))
		case strings.HasSuffix(r.URL.Path, "/rutracker/config") && r.Method == "GET":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`[{"id":"username","value":""},{"id":"password","value":""}]`))
		case strings.HasSuffix(r.URL.Path, "/rutracker/config") && r.Method == "POST":
			body, _ := io.ReadAll(r.Body)
			gotConfig = string(body)
			w.WriteHeader(200)
		default:
			t.Errorf("unexpected request: %s %s", r.Method, r.URL.Path)
			w.WriteHeader(500)
		}
	})
	h := newHarness(t, handler)
	defer h.cleanup()
	if err := h.deps.Creds.Upsert("RUTRACKER", "userpass", acStrPtr("uname"), acStrPtr("pwd"), nil); err != nil {
		t.Fatalf("seed creds: %v", err)
	}

	res := Autoconfigure(h.deps, nil)

	if len(res.Errors) != 0 {
		t.Fatalf("errors: %+v", res.Errors)
	}
	if len(res.ConfiguredNow) != 1 || res.ConfiguredNow[0] != "rutracker" {
		t.Fatalf("expected configured rutracker, got %+v", res.ConfiguredNow)
	}
	if !strings.Contains(gotConfig, "uname") || !strings.Contains(gotConfig, "pwd") {
		t.Fatalf("posted config missing creds: %s", gotConfig)
	}
	// Indexer row mirrored.
	rows, err := h.deps.Indexers.List()
	if err != nil {
		t.Fatalf("list indexers: %v", err)
	}
	if len(rows) != 1 || rows[0].ID != "rutracker" {
		t.Fatalf("indexer row: %+v", rows)
	}
	if !rows[0].ConfiguredAtJackett || !rows[0].EnabledForSearch {
		t.Fatalf("indexer flags: %+v", rows[0])
	}
	if rows[0].LinkedCredentialName == nil || *rows[0].LinkedCredentialName != "RUTRACKER" {
		t.Fatalf("indexer linked cred: %+v", rows[0].LinkedCredentialName)
	}
	// Run row recorded with 1 configured.
	runs, _ := h.deps.Runs.List(10)
	if len(runs) != 1 || runs[0].ConfiguredNowCount != 1 {
		t.Fatalf("run row: %+v", runs)
	}
	// Result summary parses back to AutoconfigResult.
	var parsed AutoconfigResult
	if err := json.Unmarshal([]byte(runs[0].ResultSummaryJSON), &parsed); err != nil {
		t.Fatalf("parse result_summary_json: %v", err)
	}
	if len(parsed.ConfiguredNow) != 1 || parsed.ConfiguredNow[0] != "rutracker" {
		t.Fatalf("parsed configured: %+v", parsed.ConfiguredNow)
	}
	// Credential MarkUsed updated last_used_at.
	cr, err := h.deps.Creds.Get("RUTRACKER")
	if err != nil {
		t.Fatalf("get cred: %v", err)
	}
	if cr.LastUsedAt == nil {
		t.Fatalf("expected last_used_at to be stamped")
	}
}

// TestAutoconfigureNNMClubServedByNativePlugin pins the Task 32
// behaviour: when a discovered credential is a known native-plugin
// tracker (NNMCLUB) and Jackett's catalog has no matching indexer, the
// orchestrator MUST list it in ServedByNativePlugin so the UI can render
// the "this is served by a native qBittorrent plugin" banner.
//
// Anti-bluff: a stub that just returned an empty AutoconfigResult would
// FAIL because we assert on the exact membership. A regression that
// dropped the classifier would also FAIL because ServedByNativePlugin
// would be the pre-allocated empty slice instead of containing
// NNMCLUB.
func TestAutoconfigureNNMClubServedByNativePlugin(t *testing.T) {
	// Catalog has only rutracker — NNMCLUB will land in unmatched.
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == "POST" && r.URL.Path == "/UI/Dashboard":
			w.WriteHeader(302)
		case r.URL.Path == "/api/v2.0/indexers" && r.Method == "GET":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`[{"id":"rutracker","name":"RuTracker","type":"private","configured":true}]`))
		default:
			t.Errorf("unexpected request: %s %s", r.Method, r.URL.Path)
			w.WriteHeader(500)
		}
	})
	h := newHarness(t, handler)
	defer h.cleanup()
	if err := h.deps.Creds.Upsert("NNMCLUB", "cookie", nil, nil, acStrPtr("sid=abc")); err != nil {
		t.Fatalf("seed nnmclub: %v", err)
	}

	res := Autoconfigure(h.deps, nil)

	// NNMCLUB must be in unmatched (no rutracker-like fuzzy match).
	foundUnmatched := false
	for _, u := range res.SkippedNoMatch {
		if u == "NNMCLUB" {
			foundUnmatched = true
		}
	}
	if !foundUnmatched {
		t.Fatalf("expected NNMCLUB in SkippedNoMatch: %+v", res.SkippedNoMatch)
	}

	// And critically: NNMCLUB must show up in ServedByNativePlugin.
	foundServed := false
	for _, n := range res.ServedByNativePlugin {
		if n == "NNMCLUB" {
			foundServed = true
		}
	}
	if !foundServed {
		t.Fatalf("expected NNMCLUB in ServedByNativePlugin, got %+v", res.ServedByNativePlugin)
	}

	// Round-trips through JSON the same way the runs row stores it.
	encoded, err := json.Marshal(res)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if !strings.Contains(string(encoded), `"served_by_native_plugin":["NNMCLUB"]`) {
		t.Fatalf("served_by_native_plugin missing or not array: %s", encoded)
	}
}

// TestAutoconfigureServedByNativePluginEmptyArray verifies the empty-slice
// initialization fix from Phase 6 still applies to the new field — when
// the discovered set has no native-plugin trackers, the JSON must
// serialize as `[]` not `null`.
func TestAutoconfigureServedByNativePluginEmptyArray(t *testing.T) {
	h := newHarness(t, http.NotFoundHandler())
	defer h.cleanup()

	res := Autoconfigure(h.deps, nil)
	encoded, err := json.Marshal(res)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if !strings.Contains(string(encoded), `"served_by_native_plugin":[]`) {
		t.Fatalf("served_by_native_plugin should serialize as []: %s", encoded)
	}
}

// TestParseIndexerMapCSV exercises the env-string parser used to merge
// JACKETT_INDEXER_MAP into the override map. Mirrors Python _parse_indexer_map.
func TestParseIndexerMapCSV(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want map[string]string
	}{
		{"empty", "", map[string]string{}},
		{"single", "RUTRACKER:rutracker", map[string]string{"RUTRACKER": "rutracker"}},
		{"multi", "rutracker:rutracker, KINOZAL :kinozalbiz",
			map[string]string{"RUTRACKER": "rutracker", "KINOZAL": "kinozalbiz"}},
		{"malformed pair skipped", "RUTRACKER:rutracker,brokenpair", map[string]string{"RUTRACKER": "rutracker"}},
		{"empty value skipped", "RUTRACKER:,KINOZAL:kinozalbiz", map[string]string{"KINOZAL": "kinozalbiz"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := ParseIndexerMapCSV(tc.in)
			if len(got) != len(tc.want) {
				t.Fatalf("len got=%d want=%d (%+v)", len(got), len(tc.want), got)
			}
			for k, v := range tc.want {
				if got[k] != v {
					t.Fatalf("key %q got %q want %q", k, got[k], v)
				}
			}
		})
	}
}

// TestIsServerError pins the 5xx-sniffing classifier that gates the
// configureOne retry. Only a "config POST HTTP 5xx" message must retry;
// 4xx and non-matching messages must NOT. RED-on-regression: if the
// prefix check were dropped a "template fetch HTTP 503" would falsely
// trigger a retry on the wrong call.
func TestIsServerError(t *testing.T) {
	cases := []struct {
		msg  string
		want bool
	}{
		{"config POST HTTP 500", true},
		{"config POST HTTP 503", true},
		{"config POST HTTP 404", false},
		{"config POST HTTP 401", false},
		{"template fetch HTTP 500", false}, // wrong prefix → not a config-POST 5xx
		{"unreachable", false},
		{"", false},
	}
	for _, tc := range cases {
		if got := isServerError(tc.msg); got != tc.want {
			t.Fatalf("isServerError(%q)=%v want %v", tc.msg, got, tc.want)
		}
	}
}

// TestConfigureOneRetriesOn5xx drives configureOne against a stateful
// stub whose POST /config returns 500 on the first attempt and 200 on the
// second. configureOne must retry (after its 2s backoff) and ultimately
// succeed (empty error string). RED-on-regression: if the retry branch is
// removed, the first 500 surfaces as "config POST HTTP 500" and this fails.
func TestConfigureOneRetriesOn5xx(t *testing.T) {
	if testing.Short() {
		t.Skip("retry path includes a 2s backoff; SKIP-OK in -short")
	}
	var posts int
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasSuffix(r.URL.Path, "/rutracker/config") && r.Method == "GET":
			_, _ = w.Write([]byte(`[{"id":"username","value":""},{"id":"password","value":""}]`))
		case strings.HasSuffix(r.URL.Path, "/rutracker/config") && r.Method == "POST":
			posts++
			if posts == 1 {
				w.WriteHeader(500) // first attempt: server error -> retry
				return
			}
			w.WriteHeader(200) // retry succeeds
		default:
			w.WriteHeader(404)
		}
	})
	srv := httptest.NewServer(handler)
	defer srv.Close()

	deps := AutoconfigDeps{Client: NewClient(srv.URL, "k")}
	cred := &repos.Credential{
		Name:        "RUTRACKER",
		HasUsername: true,
		HasPassword: true,
		Username:    "u",
		Password:    "p",
	}
	errStr := configureOne(deps, "RUTRACKER", "rutracker", cred)
	if errStr != "" {
		t.Fatalf("configureOne after retry: want success, got %q", errStr)
	}
	if posts != 2 {
		t.Fatalf("expected exactly 2 POST attempts (1 fail + 1 retry), got %d", posts)
	}
}

// TestConfigureOneNoRetryOn4xx confirms a 4xx is surfaced immediately with
// NO retry. RED-on-regression: retrying a 4xx would make posts == 2.
func TestConfigureOneNoRetryOn4xx(t *testing.T) {
	var posts int
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasSuffix(r.URL.Path, "/rutracker/config") && r.Method == "GET":
			_, _ = w.Write([]byte(`[{"id":"username","value":""},{"id":"password","value":""}]`))
		case strings.HasSuffix(r.URL.Path, "/rutracker/config") && r.Method == "POST":
			posts++
			w.WriteHeader(400)
		default:
			w.WriteHeader(404)
		}
	})
	srv := httptest.NewServer(handler)
	defer srv.Close()

	deps := AutoconfigDeps{Client: NewClient(srv.URL, "k")}
	cred := &repos.Credential{
		Name: "RUTRACKER", HasUsername: true, HasPassword: true,
		Username: "u", Password: "p",
	}
	errStr := configureOne(deps, "RUTRACKER", "rutracker", cred)
	if errStr != "config POST HTTP 400" {
		t.Fatalf("want immediate 4xx surfacing, got %q", errStr)
	}
	if posts != 1 {
		t.Fatalf("expected exactly 1 POST (no retry on 4xx), got %d", posts)
	}
}
