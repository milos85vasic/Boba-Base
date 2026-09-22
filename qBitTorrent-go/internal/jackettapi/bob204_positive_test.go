package jackettapi

// §11.4.201(1) false-positive guards for the BOB-204 fail-closed fix.
//
// The fix turns three silently-swallowed errors into refusals. A guard that
// refuses a HEALTHY operation is a FAIL-bluff of exactly the same severity
// as the PASS-bluff it replaced, so every newly-added refusal branch needs a
// positive counterpart proving the good path still completes.
//
// TestGOLDENFALSE_BOB204_HealthyPathsUnaffected (bob204_failclosed_test.go)
// already covers the healthy DELETE with Jackett == nil. The two branches
// below are the ones it cannot reach:
//
//   - the Jackett cascade actually SUCCEEDING (that test leaves Jackett nil,
//     so the new `jackett_cascade_failed` branch is never exercised against
//     a working server);
//   - rollbackCredential's mustClear == false path, where the failed request
//     OVERWROTE an existing field rather than introducing a new one, and the
//     `env_write_failed_db_rolled_back` claim must be TRUE.
//
// §11.4.10: fixture values are obviously-fake literals and no assertion or
// failure message prints a credential VALUE — only names, booleans and
// status codes.
//
// §11.4.27: no mocks — a real local HTTP server and a real SQLite DB.
// §11.4.263: no processes spawned, no signals sent.

import (
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"

	"github.com/milos85vasic/qBitTorrent-go/internal/db/repos"
	"github.com/milos85vasic/qBitTorrent-go/internal/jackett"
)

// TestPOSITIVE_BOB204_HealthyJackettCascadeStillDeletes proves the new
// fail-closed cascade does not refuse a working Jackett: the DELETE is
// really issued for the linked indexer, and the credential is fully
// removed from .env and the DB with a 204.
func TestPOSITIVE_BOB204_HealthyJackettCascadeStillDeletes(t *testing.T) {
	h := newCredsHarness(t)

	var mu sync.Mutex
	var deletedPaths []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "DELETE" {
			mu.Lock()
			deletedPaths = append(deletedPaths, r.URL.Path)
			mu.Unlock()
		}
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	h.deps.Jackett = jackett.NewClient(srv.URL, "fake-not-a-real-apikey")

	if err := h.deps.Repo.Upsert("RUTRACKER", "userpass",
		strPtr(fakeUser), strPtr(fakePass), nil); err != nil {
		t.Fatalf("seed db: %v", err)
	}
	if err := h.deps.Indexers.Upsert(&repos.Indexer{
		ID:                   "rutracker-idx",
		DisplayName:          "RuTracker",
		Type:                 "private",
		ConfiguredAtJackett:  true,
		LinkedCredentialName: strPtr("RUTRACKER"),
		EnabledForSearch:     true,
	}); err != nil {
		t.Fatalf("seed indexer: %v", err)
	}
	if err := os.WriteFile(h.envPath, []byte(
		"RUTRACKER_USERNAME="+fakeUser+"\n"+
			"RUTRACKER_PASSWORD="+fakePass+"\n"+
			"FOO=bar\n"), 0o600); err != nil {
		t.Fatalf("seed env: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest("DELETE", "/api/v1/jackett/credentials/RUTRACKER", nil)
	h.deps.HandleDeleteCredential(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("healthy cascade must still return 204, got %d body=%s", rec.Code, rec.Body.String())
	}
	mu.Lock()
	paths := append([]string(nil), deletedPaths...)
	mu.Unlock()
	var sawIndexerDelete bool
	for _, p := range paths {
		if strings.Contains(p, "rutracker-idx") {
			sawIndexerDelete = true
		}
	}
	if !sawIndexerDelete {
		t.Fatalf("cascade DELETE for rutracker-idx was never issued; paths=%v", paths)
	}
	if envHasKey(t, h.envPath, "RUTRACKER_USERNAME") || envHasKey(t, h.envPath, "RUTRACKER_PASSWORD") {
		t.Fatal("credential variables should be gone from .env")
	}
	if !envHasKey(t, h.envPath, "FOO") {
		t.Fatal("unrelated FOO must survive")
	}
	if _, err := h.deps.Repo.Get("RUTRACKER"); err == nil {
		t.Fatal("db row should be gone")
	}
}

// TestPOSITIVE_BOB204_RollbackRestoresOverwrittenValue proves the
// `env_write_failed_db_rolled_back` claim is TRUE on the overwrite path:
// the prior username is really back in the DB, not merely asserted to be.
//
// This is the mustClear == false branch — the failed request overwrote a
// field the prior row already had, so the plain compensating Upsert is
// sufficient and created_at / last_used_at are preserved.
func TestPOSITIVE_BOB204_RollbackRestoresOverwrittenValue(t *testing.T) {
	const priorUser = "fake-not-a-real-prior-username"
	const newUser = "fake-not-a-real-new-username"

	h := newCredsHarness(t)
	if err := h.deps.Repo.Upsert("KINOZAL", "userpass",
		strPtr(priorUser), strPtr(fakePass), nil); err != nil {
		t.Fatalf("seed db: %v", err)
	}

	breakEnvWrites(t, h.envPath)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest("POST", "/api/v1/jackett/credentials",
		strings.NewReader(`{"name":"KINOZAL","username":"`+newUser+`"}`))
	h.deps.HandleUpsertCredential(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 from the failed .env mirror, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "env_write_failed_db_rolled_back") {
		t.Fatalf("a verified rollback must report env_write_failed_db_rolled_back; "+
			"got a different code (status %d)", rec.Code)
	}

	after, err := h.deps.Repo.Get("KINOZAL")
	if err != nil {
		t.Fatalf("read post-rollback: %v", err)
	}
	// Values compared in memory, never printed (§11.4.10).
	if after.Username != priorUser {
		t.Fatal("rollback claimed but the prior username was NOT restored")
	}
	if !after.HasPassword || after.Password != fakePass {
		t.Fatal("rollback disturbed the untouched password field")
	}
	if after.Kind != "userpass" {
		t.Fatalf("rollback disturbed kind: %q", after.Kind)
	}
}
