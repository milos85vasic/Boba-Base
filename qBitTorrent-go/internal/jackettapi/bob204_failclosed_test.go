package jackettapi

// RED tests for BOB-204 — credential-DELETE / rollback fail-open in
// credentials.go. These are §11.4.115 RED-on-the-broken-artifact tests:
// they FAIL against the current source and are expected to flip GREEN once
// the handler stops reporting success for writes that did not happen.
//
// §11.4.252 framing: HandleDeleteCredential combines four dangerous
// capabilities on one path (credential access + filesystem mutation +
// external side effect + irreversible delete) where the fail-closed
// mandate requires only two. It currently fails OPEN.
//
// §11.4.10: every fixture value below is an obviously-fake literal, and no
// assertion or failure message ever prints a credential VALUE — only
// variable NAMES and booleans. Do not "improve" these messages by dumping
// the .env body.
//
// §11.4.263: these tests spawn no processes and send no signals.
//
// §11.4.27: no mocks. The .env failure is a real filesystem condition and
// the Jackett failure is a real local HTTP server returning 500.

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/milos85vasic/qBitTorrent-go/internal/db/repos"
	"github.com/milos85vasic/qBitTorrent-go/internal/envfile"
	"github.com/milos85vasic/qBitTorrent-go/internal/jackett"
)

// Obviously-fake fixture values. Never printed by any assertion.
const (
	fakeUser = "fake-not-a-real-username"
	fakePass = "fake-not-a-real-password"
	fakeCook = "fake-not-a-real-cookie"
)

// breakEnvWrites makes every envfile mutation of envPath fail while LEAVING
// envPath itself byte-identical and readable.
//
// Mechanism (real, no mocking): envfile.mutate writes through "<path>.tmp".
// Pre-creating that path as a DIRECTORY makes os.OpenFile(tmp, O_WRONLY|
// O_CREATE|O_TRUNC) return EISDIR, so mutate returns "open tmp: ..." before
// touching the target. Chosen over chmod-based mechanisms because opening a
// directory for writing fails for root too, so the injection cannot be
// silently bypassed when the suite runs as uid 0 (which would turn this RED
// into a false GREEN).
//
// Returns a control-needle assertion: it PROVES the injection actually fires
// before the test draws any conclusion from it (§11.4.201(7)(b)).
func breakEnvWrites(t *testing.T, envPath string) {
	t.Helper()
	if err := os.Mkdir(envPath+".tmp", 0o700); err != nil {
		t.Fatalf("inject: mkdir tmp-blocker: %v", err)
	}
	// CONTROL NEEDLE: the injection must make a real envfile.Delete fail.
	// A nil here means the instrument is blind and every downstream
	// conclusion would be a §11.4.201(6) false-null.
	if err := envfile.Delete(envPath, []string{"NEEDLE_PROBE_KEY"}); err == nil {
		t.Fatal("control needle: envfile.Delete unexpectedly SUCCEEDED — " +
			"the failure injection did not fire, so this test proves nothing")
	}
}

// envHasKey reports whether the .env at path still defines key. It returns a
// bool ONLY — the caller must never print the file body (§11.4.10).
func envHasKey(t *testing.T, path, key string) bool {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read env: %v", err)
	}
	for _, line := range strings.Split(string(b), "\n") {
		if strings.HasPrefix(strings.TrimSpace(line), key+"=") {
			return true
		}
	}
	return false
}

// TestRED_BOB204_DeleteFailOpenLeavesCredentialOnDisk is the core RED.
//
// credentials.go:239-244 discards the error of envfile.Delete and :253
// returns an UNCONDITIONAL 204. When the .env delete fails, the plaintext
// credential variables REMAIN ON DISK while the API reports the credential
// deleted — and the DB row (the encrypted, canonical copy) is already gone,
// so the surviving plaintext is now unmanaged by the very system that is
// supposed to own it.
//
// EXPECTED PRE-FIX: FAIL at the status assertion (handler returns 204).
// EXPECTED POST-FIX: PASS (handler returns 5xx naming the unresolved
// precondition, per §11.4.252(2)).
func TestRED_BOB204_DeleteFailOpenLeavesCredentialOnDisk(t *testing.T) {
	h := newCredsHarness(t)

	if err := h.deps.Repo.Upsert("RUTRACKER", "userpass",
		strPtr(fakeUser), strPtr(fakePass), nil); err != nil {
		t.Fatalf("seed db: %v", err)
	}
	if err := os.WriteFile(h.envPath, []byte(
		"RUTRACKER_USERNAME="+fakeUser+"\n"+
			"RUTRACKER_PASSWORD="+fakePass+"\n"+
			"FOO=bar\n"), 0o600); err != nil {
		t.Fatalf("seed env: %v", err)
	}

	breakEnvWrites(t, h.envPath)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest("DELETE", "/api/v1/jackett/credentials/RUTRACKER", nil)
	h.deps.HandleDeleteCredential(rec, req)

	// (b) USER-OBSERVABLE HARM — assert FIRST, because it is the fact that
	// makes a 204 a lie. If this ever stops holding, the fixture no longer
	// reproduces the defect and the status assertion below would be
	// meaningless.
	userStillOnDisk := envHasKey(t, h.envPath, "RUTRACKER_USERNAME")
	passStillOnDisk := envHasKey(t, h.envPath, "RUTRACKER_PASSWORD")
	if !userStillOnDisk || !passStillOnDisk {
		t.Fatalf("fixture broken: expected the credential variables to survive "+
			"the failed .env write, but RUTRACKER_USERNAME present=%v "+
			"RUTRACKER_PASSWORD present=%v", userStillOnDisk, passStillOnDisk)
	}

	// End-state characterisation: the canonical DB copy IS gone.
	_, dbErr := h.deps.Repo.Get("RUTRACKER")
	dbRowGone := dbErr != nil

	// (a) THE CONTRACT: the API must not report success for a delete that
	// demonstrably did not complete.
	if rec.Code == http.StatusNoContent {
		t.Fatalf("FAIL-OPEN (§11.4.252): DELETE returned 204 No Content while "+
			"RUTRACKER_USERNAME and RUTRACKER_PASSWORD are STILL PRESENT in %s "+
			"(db row removed=%v). The operator is told the credential is "+
			"deleted while the plaintext remains on disk.",
			filepath.Base(h.envPath), dbRowGone)
	}
	if rec.Code < 500 {
		t.Fatalf("expected a 5xx naming the unresolved precondition, got %d", rec.Code)
	}
	// §11.4.252(2): the refusal must NAME the unresolved precondition.
	if !strings.Contains(strings.ToLower(rec.Body.String()), "env") {
		t.Fatalf("error body does not name the failed .env precondition (status %d)", rec.Code)
	}
}

// TestRED_BOB204_DeleteFailOpenOnJackettCascade covers the second discarded
// error on the same path: credentials.go:249 `_ = d.Jackett.DeleteIndexer(id)`.
// The linked indexer is left configured at Jackett — still able to
// authenticate with the credential the operator just "deleted" — while the
// API reports 204.
//
// EXPECTED PRE-FIX: FAIL (204). EXPECTED POST-FIX: PASS.
func TestRED_BOB204_DeleteFailOpenOnJackettCascade(t *testing.T) {
	h := newCredsHarness(t)

	// Real local Jackett that refuses the cascade delete.
	var sawDelete bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "DELETE" {
			sawDelete = true
		}
		w.WriteHeader(http.StatusInternalServerError)
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

	rec := httptest.NewRecorder()
	req := httptest.NewRequest("DELETE", "/api/v1/jackett/credentials/RUTRACKER", nil)
	h.deps.HandleDeleteCredential(rec, req)

	if !sawDelete {
		t.Fatal("fixture broken: the handler never issued the Jackett cascade DELETE")
	}
	if rec.Code == http.StatusNoContent {
		t.Fatalf("FAIL-OPEN (§11.4.252): DELETE returned 204 while the Jackett " +
			"cascade delete failed (HTTP 500) — indexer rutracker-idx is left " +
			"configured at Jackett against a credential reported deleted")
	}
	if rec.Code < 500 {
		t.Fatalf("expected a 5xx naming the unresolved precondition, got %d", rec.Code)
	}
}

// TestRED_BOB204_RollbackClaimIsFalse covers the second defect:
// credentials.go:174 emits `env_write_failed_db_rolled_back` while the
// rollback at :168-173 is unverified.
//
// The mechanism proven here is STRONGER than a discarded error. The rollback
// calls Repo.Upsert with ifSet(prior.Username), and ifSet("") returns nil;
// repos.Credentials.Upsert maps nil to COALESCE(excluded.x, x) — "leave
// unchanged". So when the prior row had an EMPTY username and the failed
// request SET one, the compensating Upsert returns nil (it "succeeds") and
// leaves the new value in place. The DB is NOT rolled back, no error is
// available to check, and the API asserts a rollback anyway.
//
// EXPECTED PRE-FIX: FAIL (code says rolled_back; DB still holds the new
// value). EXPECTED POST-FIX: PASS — either the rollback really restores the
// prior state, or a distinct honest code is emitted.
func TestRED_BOB204_RollbackClaimIsFalse(t *testing.T) {
	h := newCredsHarness(t)

	// Prior row: cookie-kind, NO username stored.
	if err := h.deps.Repo.Upsert("NNMCLUB", "cookie", nil, nil, strPtr(fakeCook)); err != nil {
		t.Fatalf("seed db: %v", err)
	}
	before, err := h.deps.Repo.Get("NNMCLUB")
	if err != nil {
		t.Fatalf("read prior: %v", err)
	}
	if before.HasUsername {
		t.Fatal("fixture broken: prior row must have NO username")
	}

	breakEnvWrites(t, h.envPath)

	// A request that ADDS a username, whose .env mirror will fail.
	body := `{"name":"NNMCLUB","username":"` + fakeUser + `"}`
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("POST", "/api/v1/jackett/credentials", strings.NewReader(body))
	h.deps.HandleUpsertCredential(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("fixture broken: expected 500 from the failed .env mirror, got %d", rec.Code)
	}

	after, err := h.deps.Repo.Get("NNMCLUB")
	if err != nil {
		t.Fatalf("read post-rollback: %v", err)
	}
	rolledBack := !after.HasUsername
	claimsRolledBack := strings.Contains(rec.Body.String(), "env_write_failed_db_rolled_back")

	if claimsRolledBack && !rolledBack {
		t.Fatalf("FALSE ROLLBACK CLAIM (§11.4/§11.4.6): response asserts " +
			"`env_write_failed_db_rolled_back`, but the DB row still carries the " +
			"username the failed request introduced (has_username=true, prior was " +
			"false). The compensating Upsert no-ops on nil fields " +
			"(COALESCE keeps the new value) so it returns no error to check.")
	}
	if !rolledBack {
		t.Fatalf("db was not rolled back and the response did not say so honestly; body code check=%v", claimsRolledBack)
	}
}

// TestGOLDENFALSE_BOB204_HealthyPathsUnaffected is the §11.4.201(1)
// false-positive guard required by BOB-204 acceptance item (4): whatever
// fail-closed check the fix installs, it MUST NOT refuse the healthy path.
// This test PASSES today and MUST keep passing after the fix.
func TestGOLDENFALSE_BOB204_HealthyPathsUnaffected(t *testing.T) {
	h := newCredsHarness(t)
	if err := h.deps.Repo.Upsert("KINOZAL", "userpass",
		strPtr(fakeUser), strPtr(fakePass), nil); err != nil {
		t.Fatalf("seed db: %v", err)
	}
	if err := os.WriteFile(h.envPath, []byte(
		"KINOZAL_USERNAME="+fakeUser+"\nKINOZAL_PASSWORD="+fakePass+"\nFOO=bar\n"), 0o600); err != nil {
		t.Fatalf("seed env: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest("DELETE", "/api/v1/jackett/credentials/KINOZAL", nil)
	h.deps.HandleDeleteCredential(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("healthy DELETE must still return 204, got %d body=%s", rec.Code, rec.Body.String())
	}
	if envHasKey(t, h.envPath, "KINOZAL_USERNAME") || envHasKey(t, h.envPath, "KINOZAL_PASSWORD") {
		t.Fatal("healthy path: credential variables should be gone from .env")
	}
	if !envHasKey(t, h.envPath, "FOO") {
		t.Fatal("healthy path: unrelated FOO must survive")
	}
	if _, err := h.deps.Repo.Get("KINOZAL"); err == nil {
		t.Fatal("healthy path: db row should be gone")
	}
}
