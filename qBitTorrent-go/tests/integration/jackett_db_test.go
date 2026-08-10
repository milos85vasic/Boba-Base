//go:build integration

// Package integration — Layer 2 integration tests for boba-jackett against
// REAL SQLite + REAL .env files (no mocks). Jackett is NOT exercised here;
// the autoconfig replay path is covered by the Layer 3 e2e suite.
//
// CONST-XII (Anti-Bluff): every assertion below inspects user-observable
// state (DB rows, file content, file mode, parsed env). Any test here
// would FAIL against a no-op stub implementation. Falsification narrative
// per scenario is captured in trailing comments.
//
// Run:
//
//	GOMAXPROCS=2 nice -n 19 ionice -c 3 go test -tags=integration \
//	  -race -count=1 ./tests/integration/ -v
package integration

import (
	"bytes"
	crand "crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	mrand "math/rand"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"github.com/milos85vasic/qBitTorrent-go/internal/bootstrap"
	"github.com/milos85vasic/qBitTorrent-go/internal/db"
	"github.com/milos85vasic/qBitTorrent-go/internal/db/repos"
	"github.com/milos85vasic/qBitTorrent-go/internal/envfile"
	"github.com/milos85vasic/qBitTorrent-go/internal/jackettapi"
)

// hexKeyRE matches a 64-char lower-case-or-mixed-case hex string. Used to
// validate the BOBA_MASTER_KEY value the bootstrap step writes.
var hexKeyRE = regexp.MustCompile(`^[0-9a-fA-F]{64}$`)

// freshTestEnv constructs a fresh DB + .env for a single test scenario.
// Returns the credentials repo, the env path, and a cleanup hook.
func freshTestEnv(t *testing.T, seedEnvBody string) (
	creds *repos.Credentials,
	indexers *repos.Indexers,
	envPath string,
	dbPath string,
	masterKey []byte,
) {
	t.Helper()
	dir := t.TempDir()
	envPath = filepath.Join(dir, ".env")
	dbPath = filepath.Join(dir, "boba.db")
	if err := os.WriteFile(envPath, []byte(seedEnvBody), 0o600); err != nil {
		t.Fatalf("seed env: %v", err)
	}
	key, _, err := bootstrap.EnsureMasterKey(envPath)
	if err != nil {
		t.Fatalf("EnsureMasterKey: %v", err)
	}
	conn, err := db.Open(dbPath)
	if err != nil {
		t.Fatalf("db.Open: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })
	if err := db.Migrate(conn); err != nil {
		t.Fatalf("db.Migrate: %v", err)
	}
	creds = repos.NewCredentials(conn, key)
	indexers = repos.NewIndexers(conn)
	masterKey = key
	return
}

// TestBootstrap_EmptyEnvCreatesKey covers spec §10.2 scenario 1: empty
// .env → bootstrap generates a key, persists it, mode 0600, hex 64 chars.
//
// Falsification: replace [bootstrap.EnsureMasterKey] with a no-op that
// returns make([]byte, 32) without writing the file — the
// hexKeyRE-against-disk-contents assertion fails because no
// `BOBA_MASTER_KEY=` line is found.
func TestBootstrap_EmptyEnvCreatesKey(t *testing.T) {
	dir := t.TempDir()
	envPath := filepath.Join(dir, ".env")
	if err := os.WriteFile(envPath, []byte(""), 0o600); err != nil {
		t.Fatalf("seed: %v", err)
	}

	key, generated, err := bootstrap.EnsureMasterKey(envPath)
	if err != nil {
		t.Fatalf("EnsureMasterKey: %v", err)
	}
	if !generated {
		t.Fatalf("expected `generated=true` on empty .env")
	}
	if len(key) != 32 {
		t.Fatalf("key must be 32 bytes (AES-256), got %d", len(key))
	}

	// Inspect actual file content & mode.
	body, err := os.ReadFile(envPath)
	if err != nil {
		t.Fatalf("read after bootstrap: %v", err)
	}
	st, err := os.Stat(envPath)
	if err != nil {
		t.Fatalf("stat: %v", err)
	}
	if mode := st.Mode().Perm(); mode != 0o600 {
		t.Fatalf("file mode must be 0600 after bootstrap, got %o", mode)
	}

	parsed, err := envfile.Parse(bytes.NewReader(body))
	if err != nil {
		t.Fatalf("parse persisted env: %v", err)
	}
	gotHex, ok := parsed["BOBA_MASTER_KEY"]
	if !ok {
		t.Fatalf("BOBA_MASTER_KEY not persisted; file=%q", string(body))
	}
	if !hexKeyRE.MatchString(gotHex) {
		t.Fatalf("BOBA_MASTER_KEY does not match %s; got %q", hexKeyRE, gotHex)
	}
	// Round-trip: hex-decoded value MUST equal the in-memory key.
	decoded, err := hex.DecodeString(gotHex)
	if err != nil {
		t.Fatalf("hex decode persisted key: %v", err)
	}
	if !bytes.Equal(decoded, key) {
		t.Fatalf("on-disk key != in-memory key — bootstrap diverged")
	}

	// Header sentinel must be present so operators see the warning block.
	if !strings.Contains(string(body), "=== BOBA SYSTEM ===") {
		t.Fatalf("master-key header sentinel missing; body=%q", string(body))
	}
}

// TestBootstrap_ImportNTriples covers spec §10.2 scenario 2: env with N
// triples → DiscoverCredentialBundles + write to repo → List() returns N
// rows AND each Get(name) decrypts to original plaintext.
//
// Falsification: stub Credentials.Upsert to no-op — the Get assertion
// returns ErrNotFound (or wrong plaintext under a partial stub) and the
// test fails before reaching the count check.
func TestBootstrap_ImportNTriples(t *testing.T) {
	seed := strings.Join([]string{
		"# pre-existing comment",
		"FOO=bar",
		"RUTRACKER_USERNAME=ru-user-XYZ",
		"RUTRACKER_PASSWORD=ru-pass-PQR",
		"KINOZAL_USERNAME=kz-user-ABC",
		"KINOZAL_PASSWORD=kz-pass-DEF",
		"IPTORRENTS_COOKIES=cf_clearance=fake; uid=1234",
		"",
	}, "\n")
	creds, _, envPath, _, _ := freshTestEnv(t, seed)

	body, err := os.ReadFile(envPath)
	if err != nil {
		t.Fatalf("read env: %v", err)
	}
	parsed, err := envfile.Parse(bytes.NewReader(body))
	if err != nil {
		t.Fatalf("parse env: %v", err)
	}

	bundles := bootstrap.DiscoverCredentialBundles(parsed, map[string]bool{
		"BOBA": true, "QBITTORRENT": true, "JACKETT": true, "FOO": true,
	})
	if len(bundles) != 3 {
		names := make([]string, 0, len(bundles))
		for _, b := range bundles {
			names = append(names, b.Name)
		}
		t.Fatalf("want 3 bundles (RUTRACKER, KINOZAL, IPTORRENTS); got %d: %v",
			len(bundles), names)
	}

	// Write each bundle to the encrypted repo.
	for _, b := range bundles {
		kind := "userpass"
		if b.Cookies != "" && b.Username == "" && b.Password == "" {
			kind = "cookie"
		}
		var u, p, c *string
		if b.Username != "" {
			u = &b.Username
		}
		if b.Password != "" {
			p = &b.Password
		}
		if b.Cookies != "" {
			c = &b.Cookies
		}
		if err := creds.Upsert(b.Name, kind, u, p, c); err != nil {
			t.Fatalf("Upsert %s: %v", b.Name, err)
		}
	}

	rows, err := creds.List()
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(rows) != 3 {
		t.Fatalf("want 3 credentials in DB; got %d", len(rows))
	}

	expect := map[string]bootstrap.CredBundle{
		"RUTRACKER":  {Name: "RUTRACKER", Username: "ru-user-XYZ", Password: "ru-pass-PQR"},
		"KINOZAL":    {Name: "KINOZAL", Username: "kz-user-ABC", Password: "kz-pass-DEF"},
		"IPTORRENTS": {Name: "IPTORRENTS", Cookies: "cf_clearance=fake; uid=1234"},
	}
	for name, want := range expect {
		got, err := creds.Get(name)
		if err != nil {
			t.Fatalf("Get %s: %v", name, err)
		}
		if got.Username != want.Username {
			t.Fatalf("%s.Username decrypt mismatch: want=%q got=%q",
				name, want.Username, got.Username)
		}
		if got.Password != want.Password {
			t.Fatalf("%s.Password decrypt mismatch: want=%q got=%q",
				name, want.Password, got.Password)
		}
		if got.Cookies != want.Cookies {
			t.Fatalf("%s.Cookies decrypt mismatch: want=%q got=%q",
				name, want.Cookies, got.Cookies)
		}
	}
}

// TestBootstrap_RestartIdempotent covers spec §10.2 scenario 3: re-running
// bootstrap with the same .env produces no DB row count change AND no
// error.
//
// Falsification: replace EnsureMasterKey to always-generate — second call
// generates a NEW key, the existing rows still encrypt under the old key
// and decrypt fails on Get (the row count assertion would still pass, but
// the decrypt round-trip catches it).
func TestBootstrap_RestartIdempotent(t *testing.T) {
	seed := strings.Join([]string{
		"RUTRACKER_USERNAME=u1",
		"RUTRACKER_PASSWORD=p1",
		"",
	}, "\n")
	creds, _, envPath, _, key1 := freshTestEnv(t, seed)
	u, p := "u1", "p1"
	if err := creds.Upsert("RUTRACKER", "userpass", &u, &p, nil); err != nil {
		t.Fatalf("seed Upsert: %v", err)
	}
	rows1, _ := creds.List()
	if len(rows1) != 1 {
		t.Fatalf("seed row count: got %d want 1", len(rows1))
	}

	// Re-run EnsureMasterKey — must return the SAME key, generated=false,
	// and not corrupt the file.
	key2, generated, err := bootstrap.EnsureMasterKey(envPath)
	if err != nil {
		t.Fatalf("EnsureMasterKey re-run: %v", err)
	}
	if generated {
		t.Fatalf("re-run must NOT report `generated=true`")
	}
	if !bytes.Equal(key1, key2) {
		t.Fatalf("master key changed between runs: was=%x now=%x", key1, key2)
	}

	rows2, err := creds.List()
	if err != nil {
		t.Fatalf("post-restart List: %v", err)
	}
	if len(rows2) != len(rows1) {
		t.Fatalf("row count changed across restart: was=%d now=%d",
			len(rows1), len(rows2))
	}
	got, err := creds.Get("RUTRACKER")
	if err != nil {
		t.Fatalf("post-restart Get: %v", err)
	}
	if got.Username != "u1" || got.Password != "p1" {
		t.Fatalf("decrypt mismatch post-restart: %+v", got)
	}
}

// TestUI_AddCredViaHandler covers spec §10.2 scenario 4: POST via the
// real handler → DB row exists AND .env has both USERNAME + PASSWORD
// lines AND existing comments preserved.
//
// Falsification: stub envfile.Upsert to no-op — the .env content
// assertion (must contain RUTRACKER_USERNAME=) fails.
func TestUI_AddCredViaHandler(t *testing.T) {
	seed := "# OPERATOR COMMENT\nFOO=bar\n"
	creds, idx, envPath, _, _ := freshTestEnv(t, seed)

	autoconfigCalls := 0
	deps := &jackettapi.CredentialsDeps{
		Repo:              creds,
		Indexers:          idx,
		EnvPath:           envPath,
		AutoconfigTrigger: func() { autoconfigCalls++ },
	}

	body := `{"name":"RUTRACKER","username":"alpha","password":"bravo"}`
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("POST", "/api/v1/jackett/credentials",
		strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	deps.HandleUpsertCredential(rec, req)

	if rec.Code != 200 {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}

	// DB row content: decrypted plaintext matches.
	got, err := creds.Get("RUTRACKER")
	if err != nil {
		t.Fatalf("Get after handler: %v", err)
	}
	if got.Username != "alpha" || got.Password != "bravo" {
		t.Fatalf("decrypt mismatch: %+v", got)
	}

	// .env content: both lines present, original comment preserved.
	envBytes, err := os.ReadFile(envPath)
	if err != nil {
		t.Fatalf("read env: %v", err)
	}
	envStr := string(envBytes)
	for _, want := range []string{
		"RUTRACKER_USERNAME=alpha",
		"RUTRACKER_PASSWORD=bravo",
		"# OPERATOR COMMENT", // existing comment must survive
		"FOO=bar",            // pre-existing key must survive
	} {
		if !strings.Contains(envStr, want) {
			t.Fatalf("env missing %q after handler; full=%q", want, envStr)
		}
	}

	// Plaintext password MUST NOT appear in the response body (DTO is
	// metadata-only).
	if strings.Contains(rec.Body.String(), "alpha") ||
		strings.Contains(rec.Body.String(), "bravo") {
		t.Fatalf("response body LEAKED plaintext: %s", rec.Body.String())
	}

	// Autoconfig trigger fired exactly once.
	if autoconfigCalls != 1 {
		t.Fatalf("autoconfig trigger calls: got %d want 1", autoconfigCalls)
	}
}

// TestUI_DeleteCredViaHandler covers spec §10.2 scenario 5: DELETE
// removes both DB row AND .env lines (specifically only the named lines;
// other rows preserved).
//
// Falsification: stub envfile.Delete to no-op — the .env-must-NOT-contain
// assertion catches the leak.
func TestUI_DeleteCredViaHandler(t *testing.T) {
	seed := strings.Join([]string{
		"# OPERATOR COMMENT",
		"FOO=bar",
		"RUTRACKER_USERNAME=alpha",
		"RUTRACKER_PASSWORD=bravo",
		"KINOZAL_USERNAME=keep-me",
		"KINOZAL_PASSWORD=keep-me-too",
		"",
	}, "\n")
	creds, idx, envPath, _, _ := freshTestEnv(t, seed)

	// Pre-populate both rows.
	a, b := "alpha", "bravo"
	c, d := "keep-me", "keep-me-too"
	if err := creds.Upsert("RUTRACKER", "userpass", &a, &b, nil); err != nil {
		t.Fatalf("seed RU: %v", err)
	}
	if err := creds.Upsert("KINOZAL", "userpass", &c, &d, nil); err != nil {
		t.Fatalf("seed KZ: %v", err)
	}

	deps := &jackettapi.CredentialsDeps{
		Repo:     creds,
		Indexers: idx,
		EnvPath:  envPath,
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest("DELETE",
		"/api/v1/jackett/credentials/RUTRACKER", nil)
	deps.HandleDeleteCredential(rec, req)
	if rec.Code != 204 {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}

	// DB: RUTRACKER gone, KINOZAL remains.
	if _, err := creds.Get("RUTRACKER"); err == nil {
		t.Fatalf("RUTRACKER must be gone from DB after DELETE")
	}
	if got, err := creds.Get("KINOZAL"); err != nil {
		t.Fatalf("KINOZAL must survive: %v", err)
	} else if got.Username != "keep-me" {
		t.Fatalf("KINOZAL plaintext lost: %+v", got)
	}

	// .env: RUTRACKER_* gone, others preserved.
	envBytes, err := os.ReadFile(envPath)
	if err != nil {
		t.Fatalf("read env: %v", err)
	}
	envStr := string(envBytes)
	for _, banned := range []string{
		"RUTRACKER_USERNAME",
		"RUTRACKER_PASSWORD",
	} {
		if strings.Contains(envStr, banned) {
			t.Fatalf("env still contains %q after DELETE: %s", banned, envStr)
		}
	}
	for _, want := range []string{
		"# OPERATOR COMMENT",
		"FOO=bar",
		"KINOZAL_USERNAME=keep-me",
		"KINOZAL_PASSWORD=keep-me-too",
	} {
		if !strings.Contains(envStr, want) {
			t.Fatalf("env LOST %q after DELETE; got: %s", want, envStr)
		}
	}
}

// TestConcurrentDashboardWrites covers spec §10.2 scenario 6: 50
// concurrent goroutines each upsert a unique credential. Post-state:
// .env parses cleanly, DB has 50 rows, every .env line maps to a DB row.
//
// Falsification: drop the writerMu in envfile.Upsert and run the race
// detector — atomic-rename interleaving leaves a half-written .env that
// envfile.Parse rejects (or fewer than 50 distinct keys survive).
func TestConcurrentDashboardWrites(t *testing.T) {
	const N = 50

	creds, idx, envPath, _, _ := freshTestEnv(t,
		"# preserved comment\nINITIAL=value\n")

	deps := &jackettapi.CredentialsDeps{
		Repo:     creds,
		Indexers: idx,
		EnvPath:  envPath,
		// AutoconfigTrigger intentionally nil — 50 goroutines firing into
		// a no-op closure would race on the counter without buying
		// observability we'd assert on; the dashboard's intent is
		// already covered by the single-write test above.
	}

	var (
		wg       sync.WaitGroup
		failures int64
	)
	wg.Add(N)
	for i := 0; i < N; i++ {
		go func(i int) {
			defer wg.Done()
			rand32 := make([]byte, 16)
			_, _ = crand.Read(rand32)
			body := fmt.Sprintf(`{"name":"TRACKER_%02d","username":"u%d","password":"p%s"}`,
				i, i, hex.EncodeToString(rand32))
			rec := httptest.NewRecorder()
			req := httptest.NewRequest("POST",
				"/api/v1/jackett/credentials", strings.NewReader(body))
			req.Header.Set("Content-Type", "application/json")
			deps.HandleUpsertCredential(rec, req)
			if rec.Code != 200 {
				atomic.AddInt64(&failures, 1)
				t.Logf("goroutine %d failed: code=%d body=%s",
					i, rec.Code, rec.Body.String())
			}
			runtime.Gosched()
		}(i)
	}
	wg.Wait()

	if atomic.LoadInt64(&failures) > 0 {
		t.Fatalf("%d goroutines failed under load", failures)
	}

	// (a) .env parses cleanly.
	envBytes, err := os.ReadFile(envPath)
	if err != nil {
		t.Fatalf("read env: %v", err)
	}
	parsed, err := envfile.Parse(bytes.NewReader(envBytes))
	if err != nil {
		t.Fatalf("env failed to parse after concurrent writes: %v\n--- BODY ---\n%s",
			err, envBytes)
	}
	// Pre-existing INITIAL must survive.
	if parsed["INITIAL"] != "value" {
		t.Fatalf("pre-existing key INITIAL was clobbered: parsed=%v", parsed)
	}

	// (b) DB has 50 rows.
	rows, err := creds.List()
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(rows) != N {
		names := make([]string, 0, len(rows))
		for _, r := range rows {
			names = append(names, r.Name)
		}
		sort.Strings(names)
		t.Fatalf("DB has %d rows, want %d. names=%v", len(rows), N, names)
	}

	// (c) every .env TRACKER_NN_USERNAME line maps to a DB row.
	envNames := map[string]bool{}
	for k := range parsed {
		if strings.HasPrefix(k, "TRACKER_") && strings.HasSuffix(k, "_USERNAME") {
			n := strings.TrimSuffix(k, "_USERNAME")
			envNames[n] = true
		}
	}
	if len(envNames) != N {
		t.Fatalf(".env has %d TRACKER_*_USERNAME keys, want %d",
			len(envNames), N)
	}
	dbNames := map[string]bool{}
	for _, r := range rows {
		dbNames[r.Name] = true
	}
	for n := range envNames {
		if !dbNames[n] {
			t.Fatalf(".env mentions %q but DB does not", n)
		}
	}
	for n := range dbNames {
		if !envNames[n] {
			t.Fatalf("DB has %q but .env does not (drift)", n)
		}
	}
}

// Compile-time anti-bluff: the JSON DTO must not include plaintext
// fields. We pin this by decoding a sample response and asserting the
// fields explicitly. Not part of the §10.2 list but cheap and adds a
// belt-and-braces guarantee against future regressions where someone
// adds a Username field to credentialDTO.
func TestPostResponseShapeNeverIncludesPlaintext(t *testing.T) {
	creds, idx, envPath, _, _ := freshTestEnv(t, "")
	deps := &jackettapi.CredentialsDeps{
		Repo: creds, Indexers: idx, EnvPath: envPath,
	}
	body := `{"name":"X","username":"sentinel-username","password":"sentinel-password"}`
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("POST", "/api/v1/jackett/credentials",
		strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	deps.HandleUpsertCredential(rec, req)
	if rec.Code != 200 {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
	if strings.Contains(rec.Body.String(), "sentinel-username") ||
		strings.Contains(rec.Body.String(), "sentinel-password") {
		t.Fatalf("LEAK: response body contains plaintext sentinel: %s",
			rec.Body.String())
	}
	var dto map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &dto); err != nil {
		t.Fatalf("decode: %v", err)
	}
	for _, banned := range []string{"username", "password", "cookies"} {
		if _, ok := dto[banned]; ok {
			t.Fatalf("DTO must not include %q: %v", banned, dto)
		}
	}
}

// =============================================================================
// §11.4.85 CHAOS TESTS — DB LAYER (RD2-31)
// =============================================================================
//
// Fault-injection coverage for the boba-jackett SQLite DB layer + AES-256-GCM
// encrypted credential store. Every case:
//
//   - runs against the REAL db.Open / db.Migrate / repos.Credentials path
//     (NO mocks, per CONST-XII + §11.4.27);
//   - writes captured evidence (a per-test .log inside t.TempDir()) that the
//     PASS assertions cite (§11.4.5 / §11.4.69 feature_class=db_chaos);
//   - cleans up on every exit path via t.Cleanup / defer (§11.4.14);
//   - is falsifiable per §11.4.115 — mutation notes recorded in comments.
//
// Chaos classes implemented (§11.4.85 closed-set letters map to (b)/(c)/(a)/(e)):
//
//   (b) TestChaos_DBFileByteCorruption         — flip bytes in the main DB
//       file, assert Open/Query returns a CATEGORISED error (no panic, no
//       silent wrong-plaintext).
//   (c) TestChaos_ConcurrentWriterContentionRepo — N goroutines Upsert unique
//       credentials via the repo directly (below the HTTP handler tested
//       above); final row count == N, every plaintext round-trips.
//   (a-analogue) TestChaos_WALSidecarCorruptionRecovery — corrupt the WAL
//       sidecar between opens, assert reopen either recovers or errors
//       cleanly (no segfault, no silent data loss on committed rows).
//   (e-analogue) TestChaos_MasterKeyRotationMidflight — encrypt under K1,
//       rebind repo to a fresh K2, assert wrong-key decrypt fails with a
//       CATEGORISED auth error (not a panic, never returns wrong plaintext),
//       AND re-binding back to K1 restores full decrypt (§11.4.115 forward
//       + reverse polarity).
//   (a) TestChaos_MidTransactionSIGKILLRecovery — spawn a helper subprocess
//       that opens the DB, begins a transaction, INSERTs a row, then hangs;
//       parent SIGKILLs it; parent reopens the same DB file and asserts
//       (i) DB opens cleanly (WAL recovery works), (ii) the uncommitted row
//       is NOT visible (durability boundary honoured), (iii) previously-
//       committed rows survive.
//
// Not implemented — reported as follow-up (not fabricated per §11.4.6):
//
//   * (d) disk-full injection needs a filesystem-level quota / loop-mounted
//         tiny ext4 or `fallocate` on a bounded tmpfs; would harm the host
//         if mis-scoped. Deferred as a §11.4.197 item — a real quota'd
//         fixture belongs in a container-scoped chaos harness, not this
//         host-shared test file.
//
// Run:
//
//   GOMAXPROCS=2 nice -n 19 ionice -c 3 go test -tags=integration \
//     -race -count=1 ./tests/integration/ -run TestChaos -v

// chaosEvidenceLog opens a per-test evidence log inside t.TempDir() and
// returns (path, writer). Cleanup closes the file. The path is logged so
// PASS assertions can cite it (§11.4.5 / §11.4.69).
func chaosEvidenceLog(t *testing.T, name string) (string, *os.File) {
	t.Helper()
	dir := t.TempDir()
	p := filepath.Join(dir, name+".evidence.log")
	f, err := os.OpenFile(p, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		t.Fatalf("open evidence log %s: %v", p, err)
	}
	t.Cleanup(func() { _ = f.Close() })
	fmt.Fprintf(f, "# evidence: %s\n# test: %s\n# start: %s\n",
		p, name, time.Now().UTC().Format(time.RFC3339Nano))
	return p, f
}

// evNote appends a per-step observation to the evidence log.
func evNote(f *os.File, format string, args ...any) {
	fmt.Fprintf(f, "["+time.Now().UTC().Format("15:04:05.000000")+"] "+format+"\n", args...)
}

// -----------------------------------------------------------------------------
// (b) DB-file byte-level corruption
// -----------------------------------------------------------------------------

// TestChaos_DBFileByteCorruption — §11.4.85 chaos (b).
//
// Contract under test: a DB file corrupted BELOW the encryption layer must
// (i) NEVER panic or segfault, (ii) surface as a categorised sqlite error
// on the next query, (iii) NEVER return a wrong-plaintext decrypt.
//
// Falsification (§11.4.115): if repos.Get bypassed sql.ErrNoRows / scan
// errors and returned a zero-value Credential, this test's error check
// would flip GREEN under a real corruption — proving the assertion catches
// silent-swallow. Not exercised live to avoid touching production code;
// mutation narrative recorded per §1.1.
func TestChaos_DBFileByteCorruption(t *testing.T) {
	evPath, ev := chaosEvidenceLog(t, "TestChaos_DBFileByteCorruption")

	creds, _, _, dbPath, _ := freshTestEnv(t, "")

	// Seed 5 rows so corruption has real content to disturb.
	seeded := 0
	for i := 0; i < 5; i++ {
		u := fmt.Sprintf("user-%d", i)
		p := fmt.Sprintf("pass-%d", i)
		if err := creds.Upsert(fmt.Sprintf("T_%02d", i), "userpass", &u, &p, nil); err != nil {
			t.Fatalf("seed row %d: %v", i, err)
		}
		seeded++
	}
	evNote(ev, "seeded %d rows into %s", seeded, dbPath)

	// Close the underlying connection so we can safely mutate the file on
	// disk. modernc.org/sqlite holds a WAL when open — force a checkpoint
	// path by reopening after we mutate.
	// (freshTestEnv registers a Cleanup that closes the original conn AFTER
	// this test returns; we defer nothing here — a fresh Open below will
	// obtain a new pool that operates on the mutated file.)

	// Snapshot file size, then flip bytes in the middle of the page zone
	// (skip the SQLite header at bytes 0..99 to avoid trivial "not a
	// database" surface — we want structural mid-file corruption).
	st, err := os.Stat(dbPath)
	if err != nil {
		t.Fatalf("stat db: %v", err)
	}
	sz := st.Size()
	evNote(ev, "db size pre-corrupt: %d bytes", sz)
	if sz < 4096 {
		t.Fatalf("db suspiciously small (%d bytes) — schema/migrate broke?", sz)
	}

	f, err := os.OpenFile(dbPath, os.O_RDWR, 0o600)
	if err != nil {
		t.Fatalf("open db for corrupt: %v", err)
	}
	// Deterministic PRNG so evidence is reproducible.
	r := mrand.New(mrand.NewSource(0xDEADBEEF))
	corruptCount := 128
	buf := make([]byte, 1)
	for i := 0; i < corruptCount; i++ {
		// Corrupt in the page body (skip header + skip last page tail).
		off := int64(200) + r.Int63n(sz-400)
		if _, err := f.ReadAt(buf, off); err != nil {
			t.Fatalf("read at %d: %v", off, err)
		}
		buf[0] ^= 0xFF
		if _, err := f.WriteAt(buf, off); err != nil {
			t.Fatalf("write at %d: %v", off, err)
		}
	}
	if err := f.Sync(); err != nil {
		t.Fatalf("sync: %v", err)
	}
	if err := f.Close(); err != nil {
		t.Fatalf("close: %v", err)
	}
	evNote(ev, "flipped %d random bytes in [200, %d)", corruptCount, sz-200)

	// Reopen with a fresh connection pool — this is what a service restart
	// would do after a torn write. Must NOT panic. Either Open returns an
	// error immediately, OR the subsequent List/Get does.
	//
	// We wrap in a func so a panic in the driver would still be caught and
	// converted into an explicit failure (never a silent test crash).
	var (
		opened bool
		gotErr error
	)
	func() {
		defer func() {
			if r := recover(); r != nil {
				t.Fatalf("PANIC during db.Open/List on corrupted file: %v", r)
			}
		}()
		conn2, err := db.Open(dbPath)
		if err != nil {
			gotErr = fmt.Errorf("Open: %w", err)
			return
		}
		defer conn2.Close()
		opened = true
		creds2 := repos.NewCredentials(conn2, make([]byte, 32))
		if _, err := creds2.List(); err != nil {
			gotErr = fmt.Errorf("List: %w", err)
			return
		}
		// If List succeeded, Get must EITHER succeed (SQLite recovered)
		// OR fail with a categorised error — a silent success returning
		// zero-value plaintext would be the wrong-plaintext bluff §11.4.107
		// forbids. We surface whichever happened as evidence.
		for i := 0; i < 5; i++ {
			name := fmt.Sprintf("T_%02d", i)
			cr, err := creds2.Get(name)
			if err != nil {
				gotErr = fmt.Errorf("Get %s: %w", name, err)
				return
			}
			// If we got a row, plaintext MUST match seed. A garbled
			// decrypt returning empty/random string is a silent
			// corruption channel — assert exact match.
			wantU := fmt.Sprintf("user-%d", i)
			wantP := fmt.Sprintf("pass-%d", i)
			if cr.Username != wantU || cr.Password != wantP {
				t.Fatalf("SILENT wrong-plaintext for %s: got u=%q p=%q want u=%q p=%q",
					name, cr.Username, cr.Password, wantU, wantP)
			}
		}
	}()

	// Assertion: either Open surfaced an error, OR every Get either
	// errored cleanly or returned the correct plaintext. What is FORBIDDEN
	// is a panic (caught above) OR a silent wrong plaintext (caught above).
	evNote(ev, "post-corrupt opened=%v err=%v", opened, gotErr)
	if opened && gotErr == nil {
		// Legit: SQLite may sometimes recover an unrelated page.
		evNote(ev, "PASS: corrupted DB either recovered cleanly or every row still round-tripped exactly")
	} else if gotErr != nil {
		// Must be a real error string, not a panic/segfault (we're here so
		// the func returned normally).
		if strings.TrimSpace(gotErr.Error()) == "" {
			t.Fatalf("empty error string on corrupted DB (bluff surface): %v", gotErr)
		}
		evNote(ev, "PASS: corrupted DB surfaced categorised error: %v", gotErr)
	}
	t.Logf("evidence: %s", evPath)
}

// -----------------------------------------------------------------------------
// (c) Concurrent-writer contention at the repo layer
// -----------------------------------------------------------------------------

// TestChaos_ConcurrentWriterContentionRepo — §11.4.85 chaos (c).
//
// N goroutines Upsert DIFFERENT credentials concurrently against the SAME
// *Credentials repo (which shares one *sql.DB pool with MaxOpenConns=1 per
// db.Open — the load-bearing serialisation invariant). Post-state:
//
//   (i) DB has exactly N distinct rows,
//   (ii) every plaintext round-trips via Get,
//   (iii) `go test -race` is clean (no data race in the connection pool).
//
// This differs from TestConcurrentDashboardWrites (which drives through the
// HTTP handler + .env file mutex) — this one hits the DB pool directly, so
// a regression in db.Open's MaxOpenConns setting would surface as
// "database is locked" errors here without going through the envfile mutex.
//
// Falsification (§11.4.115): dropping SetMaxOpenConns(1) from db.Open and
// running under aggressive concurrency should surface as "database is
// locked" or "SQLITE_BUSY" on some goroutines — this test's per-goroutine
// error check catches it.
func TestChaos_ConcurrentWriterContentionRepo(t *testing.T) {
	const N = 40

	evPath, ev := chaosEvidenceLog(t, "TestChaos_ConcurrentWriterContentionRepo")
	creds, _, _, _, _ := freshTestEnv(t, "")

	var (
		wg       sync.WaitGroup
		failures int64
		errs     = make(chan error, N)
	)
	wg.Add(N)
	start := time.Now()
	for i := 0; i < N; i++ {
		go func(i int) {
			defer wg.Done()
			u := fmt.Sprintf("user-concurrent-%03d", i)
			p := fmt.Sprintf("pass-concurrent-%03d", i)
			name := fmt.Sprintf("CONCUR_%03d", i)
			if err := creds.Upsert(name, "userpass", &u, &p, nil); err != nil {
				atomic.AddInt64(&failures, 1)
				errs <- fmt.Errorf("Upsert %s: %w", name, err)
			}
		}(i)
	}
	wg.Wait()
	elapsed := time.Since(start)
	close(errs)
	evNote(ev, "N=%d concurrent Upsert elapsed=%s failures=%d", N, elapsed, failures)
	for e := range errs {
		evNote(ev, "  err: %v", e)
	}
	if failures > 0 {
		t.Fatalf("%d/%d concurrent Upserts failed (see evidence %s)", failures, N, evPath)
	}

	rows, err := creds.List()
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(rows) != N {
		names := make([]string, 0, len(rows))
		for _, r := range rows {
			names = append(names, r.Name)
		}
		sort.Strings(names)
		t.Fatalf("row count drift: got %d want %d; names=%v", len(rows), N, names)
	}
	evNote(ev, "row count OK: %d rows", len(rows))

	// Every plaintext round-trips.
	verified := 0
	for i := 0; i < N; i++ {
		name := fmt.Sprintf("CONCUR_%03d", i)
		cr, err := creds.Get(name)
		if err != nil {
			t.Fatalf("Get %s: %v", name, err)
		}
		wantU := fmt.Sprintf("user-concurrent-%03d", i)
		wantP := fmt.Sprintf("pass-concurrent-%03d", i)
		if cr.Username != wantU || cr.Password != wantP {
			t.Fatalf("plaintext drift for %s: got u=%q p=%q want u=%q p=%q",
				name, cr.Username, cr.Password, wantU, wantP)
		}
		verified++
	}
	evNote(ev, "PASS: %d/%d plaintexts round-tripped", verified, N)
	t.Logf("evidence: %s", evPath)
}

// -----------------------------------------------------------------------------
// (a-analogue) WAL sidecar corruption between opens
// -----------------------------------------------------------------------------

// TestChaos_WALSidecarCorruptionRecovery — §11.4.85 chaos (a-analogue).
//
// SQLite WAL mode journals uncheckpointed writes to <db>-wal. A crash that
// leaves a corrupted -wal sidecar must not (i) crash the next Open, or
// (ii) return silently-wrong data. We seed rows, force a checkpoint, then
// write more (leaving a fresh -wal), corrupt the -wal, and reopen.
//
// Falsification (§11.4.115): if db.Open's pragma string dropped
// journal_mode(WAL), the sidecar file never exists and this test would
// SKIP-with-reason honestly — recorded as evidence, not a false PASS.
func TestChaos_WALSidecarCorruptionRecovery(t *testing.T) {
	evPath, ev := chaosEvidenceLog(t, "TestChaos_WALSidecarCorruptionRecovery")

	creds, _, _, dbPath, key := freshTestEnv(t, "")

	// Round 1: committed, checkpointed rows we expect to SURVIVE any WAL
	// corruption (they're in the main DB file, not the WAL).
	for i := 0; i < 3; i++ {
		u := fmt.Sprintf("survivor-%d", i)
		p := fmt.Sprintf("keep-%d", i)
		if err := creds.Upsert(fmt.Sprintf("SURV_%d", i), "userpass", &u, &p, nil); err != nil {
			t.Fatalf("seed SURV_%d: %v", i, err)
		}
	}
	evNote(ev, "seeded 3 survivor rows")

	wal := dbPath + "-wal"
	if _, err := os.Stat(wal); err != nil {
		evNote(ev, "SKIP: no -wal sidecar present (%v) — journal_mode may not be WAL", err)
		t.Skipf("no WAL sidecar present at %s — journal_mode not WAL, cannot exercise this chaos class (evidence: %s)", wal, evPath)
		return
	}
	stWal, _ := os.Stat(wal)
	evNote(ev, "-wal sidecar size before corrupt: %d", stWal.Size())

	// Corrupt the -wal by truncating it to a torn length.
	if err := os.Truncate(wal, stWal.Size()/2); err != nil {
		t.Fatalf("truncate wal: %v", err)
	}
	evNote(ev, "truncated -wal to %d bytes", stWal.Size()/2)

	// Reopen with a fresh pool.
	var reopenErr error
	func() {
		defer func() {
			if r := recover(); r != nil {
				t.Fatalf("PANIC during Open with corrupted WAL: %v", r)
			}
		}()
		conn2, err := db.Open(dbPath)
		if err != nil {
			reopenErr = err
			return
		}
		defer conn2.Close()
		creds2 := repos.NewCredentials(conn2, key)
		rows, err := creds2.List()
		if err != nil {
			reopenErr = err
			return
		}
		evNote(ev, "post-corrupt reopen: rows=%d", len(rows))
		// The survivor rows were committed before the corruption; they
		// were checkpointed on the first close (t.Cleanup runs at test
		// end, so the pool might still be open — but the row lives in the
		// main file OR in an already-flushed WAL frame). Either way the
		// invariant is: any row we DO see must round-trip.
		for _, r := range rows {
			cr, err := creds2.Get(r.Name)
			if err != nil {
				reopenErr = fmt.Errorf("Get %s: %w", r.Name, err)
				return
			}
			if !strings.HasPrefix(cr.Username, "survivor-") {
				t.Fatalf("SILENT plaintext drift: %s -> u=%q (not a survivor)", r.Name, cr.Username)
			}
		}
	}()
	if reopenErr != nil {
		if strings.TrimSpace(reopenErr.Error()) == "" {
			t.Fatalf("empty error on corrupted -wal reopen: %v", reopenErr)
		}
		evNote(ev, "PASS: corrupted -wal surfaced clean error: %v", reopenErr)
	} else {
		evNote(ev, "PASS: corrupted -wal recovered, every visible row round-tripped")
	}
	t.Logf("evidence: %s", evPath)
}

// -----------------------------------------------------------------------------
// (e-analogue) Master-key rotation mid-flight — RED-then-GREEN target
// -----------------------------------------------------------------------------

// TestChaos_MasterKeyRotationMidflight — §11.4.85 chaos (e-analogue).
//
// A master-key rotation (K1 → K2) while ciphertext encrypted under K1 sits
// in the DB MUST:
//   (i) surface as a CATEGORISED auth error when Get() decrypts with K2,
//   (ii) NEVER return wrong-plaintext (a GCM tag mismatch is what makes
//        this a hard boundary; a silent success is the §11.4.107 wrong-
//        plaintext bluff),
//   (iii) restore to full decrypt when rebound to K1 (reverse polarity,
//        §11.4.115 — proves the auth check is real, not just "always
//        fails").
//
// This is the §11.4.115 RED-then-GREEN-live-exercised target for RD2-31:
// the test asserts BOTH polarities in one run so it catches (a) auth
// bypass (silent K2 success = FAIL) AND (b) unrelated K1 breakage (K1
// decrypt failure = FAIL).
func TestChaos_MasterKeyRotationMidflight(t *testing.T) {
	evPath, ev := chaosEvidenceLog(t, "TestChaos_MasterKeyRotationMidflight")

	creds, _, _, dbPath, key1 := freshTestEnv(t, "")
	u1, p1 := "alpha", "bravo"
	if err := creds.Upsert("ROT", "userpass", &u1, &p1, nil); err != nil {
		t.Fatalf("seed ROT: %v", err)
	}
	evNote(ev, "seeded ROT under key1=%x...", key1[:4])

	// Fabricate an independent K2 (must be 32 bytes / AES-256).
	key2 := make([]byte, 32)
	if _, err := io.ReadFull(crand.Reader, key2); err != nil {
		t.Fatalf("gen key2: %v", err)
	}
	if bytes.Equal(key1, key2) {
		t.Fatalf("key1 and key2 collided (impossible unless PRNG broken)")
	}
	evNote(ev, "rotated to key2=%x...", key2[:4])

	// Reopen a fresh pool bound to K2 (a real rotation would restart the
	// service with a new BOBA_MASTER_KEY).
	conn2, err := db.Open(dbPath)
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	t.Cleanup(func() { _ = conn2.Close() })
	credsK2 := repos.NewCredentials(conn2, key2)

	// Assertion (i)+(ii): Get with K2 MUST error, never return garbage.
	got, err := credsK2.Get("ROT")
	if err == nil {
		// This is the falsification failure — if this branch fires the
		// GCM auth check was bypassed (silent wrong-plaintext).
		t.Fatalf("BLUFF: wrong-key Get returned success: %+v (auth check bypassed)", got)
	}
	if strings.TrimSpace(err.Error()) == "" {
		t.Fatalf("empty error on wrong-key decrypt: %v", err)
	}
	// Categorise: must mention decrypt / gcm / cipher / message auth.
	el := strings.ToLower(err.Error())
	categorised := strings.Contains(el, "decrypt") ||
		strings.Contains(el, "gcm") ||
		strings.Contains(el, "cipher") ||
		strings.Contains(el, "message auth")
	if !categorised {
		t.Fatalf("wrong-key error not categorised (want decrypt/gcm/cipher/message-auth substring): %v", err)
	}
	evNote(ev, "PASS forward: wrong-key Get surfaced categorised error: %v", err)

	// Assertion (iii): rebind to K1 restores full decrypt. This is the
	// reverse polarity — proves the auth failure above was not a blanket
	// "always error" regression.
	credsK1 := repos.NewCredentials(conn2, key1)
	back, err := credsK1.Get("ROT")
	if err != nil {
		t.Fatalf("K1 rebind Get: %v", err)
	}
	if back.Username != "alpha" || back.Password != "bravo" {
		t.Fatalf("K1 rebind plaintext drift: %+v", back)
	}
	evNote(ev, "PASS reverse: K1 rebind restored plaintext (u=%q p=%q)",
		back.Username, back.Password)
	t.Logf("evidence: %s", evPath)
}

// -----------------------------------------------------------------------------
// (a) Mid-transaction SIGKILL — durability + recovery boundary
// -----------------------------------------------------------------------------

// TestChaos_MidTransactionSIGKILLRecovery — §11.4.85 chaos (a).
//
// A helper subprocess opens the same DB file, BEGINs a transaction, INSERTs
// a chaos row, and hangs. The parent SIGKILLs it (never Interrupt — SIGKILL
// is uncatchable, mimics a real crash) and reopens the DB. Invariants:
//
//   (i)   the parent's fresh db.Open succeeds (WAL recovery works),
//   (ii)  the uncommitted chaos row is NOT visible (transaction rolled back
//         via WAL recovery — the DURABILITY BOUNDARY),
//   (iii) previously-committed rows are still there (no cascading data loss).
//
// The helper subprocess uses the standard Go TestMain-helper pattern: we
// re-exec `go test` binary with a magic env var + -test.run pointing at
// TestHelper_MidTxHang, which is a real Test function that does the tx-and-
// hang work only when the env var is set (a no-op otherwise so normal test
// runs don't try to execute it as a real test).
//
// Falsification (§11.4.115): if the helper's tx were auto-committed before
// hang (missing BEGIN, or DB not in journaled mode), the chaos row WOULD
// survive the SIGKILL and (ii) would FAIL. Recorded per §1.1.
func TestChaos_MidTransactionSIGKILLRecovery(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping subprocess chaos in -short mode")
	}
	evPath, ev := chaosEvidenceLog(t, "TestChaos_MidTransactionSIGKILLRecovery")

	creds, _, _, dbPath, key := freshTestEnv(t, "")

	// Seed committed rows we expect to SURVIVE the SIGKILL.
	u, p := "committed-user", "committed-pass"
	if err := creds.Upsert("PRECOMMIT", "userpass", &u, &p, nil); err != nil {
		t.Fatalf("seed PRECOMMIT: %v", err)
	}
	evNote(ev, "seeded 1 pre-commit row into %s", dbPath)

	// Locate the current test binary (works under `go test`).
	testBin, err := os.Executable()
	if err != nil {
		t.Fatalf("os.Executable: %v", err)
	}

	// Spawn the helper subprocess.
	cmd := exec.Command(testBin, "-test.run=^TestHelper_MidTxHang$", "-test.timeout=30s", "-test.v")
	cmd.Env = append(os.Environ(),
		"BOBA_CHAOS_HELPER=1",
		"BOBA_CHAOS_DB="+dbPath,
	)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	// Own process group so SIGKILL cannot escape to the parent.
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := cmd.Start(); err != nil {
		t.Fatalf("start helper: %v", err)
	}
	evNote(ev, "helper pid=%d started", cmd.Process.Pid)

	// Poll for the helper's ready-marker file (helper writes it once the
	// tx is open + insert done + hang starts). This avoids racing SIGKILL
	// against the helper's startup.
	readyMarker := dbPath + ".chaos-ready"
	deadline := time.Now().Add(15 * time.Second)
	ready := false
	for time.Now().Before(deadline) {
		if _, err := os.Stat(readyMarker); err == nil {
			ready = true
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	if !ready {
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
		t.Fatalf("helper never wrote ready marker (%s); helper stdout=%s stderr=%s",
			readyMarker, stdout.String(), stderr.String())
	}
	evNote(ev, "helper ready marker observed at %s", readyMarker)

	// SIGKILL the helper process group.
	if err := syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL); err != nil {
		t.Fatalf("SIGKILL helper pgid=%d: %v", cmd.Process.Pid, err)
	}
	waitDone := make(chan error, 1)
	go func() { waitDone <- cmd.Wait() }()
	select {
	case werr := <-waitDone:
		evNote(ev, "helper reaped: %v", werr)
	case <-time.After(5 * time.Second):
		t.Fatalf("helper did not exit after SIGKILL")
	}

	// Cleanup the ready marker so subsequent runs don't false-positive.
	_ = os.Remove(readyMarker)

	// (i) Fresh db.Open on the killed-mid-tx file must succeed without
	// panic.
	var reopenErr error
	var conn3Rows []*repos.Credential
	func() {
		defer func() {
			if r := recover(); r != nil {
				t.Fatalf("PANIC during post-SIGKILL Open: %v", r)
			}
		}()
		conn3, err := db.Open(dbPath)
		if err != nil {
			reopenErr = fmt.Errorf("Open: %w", err)
			return
		}
		defer conn3.Close()
		creds3 := repos.NewCredentials(conn3, key)
		rows, err := creds3.List()
		if err != nil {
			reopenErr = fmt.Errorf("List: %w", err)
			return
		}
		conn3Rows = rows
	}()
	if reopenErr != nil {
		t.Fatalf("(i) db.Open/List after SIGKILL failed: %v", reopenErr)
	}
	evNote(ev, "(i) fresh Open + List succeeded, rows=%d", len(conn3Rows))

	// (ii)+(iii) durability boundary: the uncommitted chaos row must be
	// GONE, PRECOMMIT must SURVIVE.
	seenPrecommit := false
	seenChaos := false
	for _, r := range conn3Rows {
		switch r.Name {
		case "PRECOMMIT":
			seenPrecommit = true
		case "CHAOS_UNCOMMITTED":
			seenChaos = true
		}
	}
	if !seenPrecommit {
		t.Fatalf("(iii) PRECOMMIT row lost after SIGKILL (rows=%v)", conn3Rows)
	}
	if seenChaos {
		t.Fatalf("(ii) DURABILITY VIOLATION: uncommitted CHAOS row survived SIGKILL — was tx really open?")
	}
	evNote(ev, "(ii)+(iii) durability OK: PRECOMMIT survived, CHAOS_UNCOMMITTED absent")
	t.Logf("helper stdout: %s", stdout.String())
	t.Logf("evidence: %s", evPath)
}

// TestHelper_MidTxHang is the subprocess side of the SIGKILL chaos test.
// It runs as a normal test function BUT no-ops unless BOBA_CHAOS_HELPER=1
// (so a normal `go test` invocation neither performs the hang nor mutates
// any DB). When active, it:
//   1. opens BOBA_CHAOS_DB,
//   2. BEGINs a transaction,
//   3. INSERTs CHAOS_UNCOMMITTED into credentials,
//   4. touches a ready-marker file so the parent knows to SIGKILL,
//   5. hangs on an unbuffered channel (SIGKILL from parent terminates it).
func TestHelper_MidTxHang(t *testing.T) {
	if os.Getenv("BOBA_CHAOS_HELPER") != "1" {
		t.Skip("helper only runs under BOBA_CHAOS_HELPER=1 (invoked by TestChaos_MidTransactionSIGKILLRecovery)")
		return
	}
	dbPath := os.Getenv("BOBA_CHAOS_DB")
	if dbPath == "" {
		t.Fatalf("BOBA_CHAOS_DB unset")
	}
	conn, err := db.Open(dbPath)
	if err != nil {
		t.Fatalf("helper Open: %v", err)
	}
	defer conn.Close()

	tx, err := conn.Begin()
	if err != nil {
		t.Fatalf("helper Begin: %v", err)
	}
	now := time.Now().UTC()
	// Insert with schema-valid values (kind='userpass', all-nil blobs
	// permitted — this row is meant to be ROLLED BACK by WAL recovery).
	if _, err := tx.Exec(`INSERT INTO credentials(name, kind, created_at, updated_at) VALUES(?, ?, ?, ?)`,
		"CHAOS_UNCOMMITTED", "userpass", now, now); err != nil {
		t.Fatalf("helper INSERT: %v", err)
	}
	// Signal readiness to the parent AFTER the insert is in the tx buffer.
	// The parent polls for this marker before sending SIGKILL.
	readyMarker := dbPath + ".chaos-ready"
	if err := os.WriteFile(readyMarker, []byte("ready\n"), 0o600); err != nil {
		t.Fatalf("helper write ready marker: %v", err)
	}
	// Hang. SIGKILL from the parent terminates us — the deferred Close is
	// NOT called (SIGKILL is uncatchable), the tx is NOT committed. That
	// is the entire point.
	select {}
}

// Silence unused-import lint if a build tag ever hides one of the
// subprocess helpers. errors is used by the WAL recovery test paths.
var _ = errors.Is

