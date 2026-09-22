package jackettapi

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/milos85vasic/qBitTorrent-go/internal/db/repos"
	"github.com/milos85vasic/qBitTorrent-go/internal/envfile"
	"github.com/milos85vasic/qBitTorrent-go/internal/jackett"
)

// CredentialsDeps wires the runtime dependencies the credentials endpoints
// need. EnvPath is the absolute path to the .env file we mirror writes to
// (per spec §7 row 1: "✅ atomic mirror"). AutoconfigTrigger is invoked
// after a successful upsert to replay the autoconfig pass; nil disables
// the replay (useful for unit tests). Jackett may be nil for tests; in
// production it's used by [HandleDeleteCredential] for the cascade
// `DELETE /api/v2.0/indexers/{id}` per spec §7 row 2.
//
// NOTE on transactionality: the spec demands "hybrid C: BOTH writes must
// succeed". The Phase 1 [repos.Credentials] does not expose a transaction
// handle (its Upsert/Delete are single-statement Execs against *sql.DB),
// so we cannot wrap DB + .env writes in a single SQL tx. Instead we use
// a compensating-action pattern: snapshot the prior DB state, perform the
// DB write, perform the .env write, and on .env failure undo the DB
// write (delete-if-new, restore-prior-values-if-update). The end-state
// guarantee is the same as a true 2PC: both succeed or both end in their
// pre-call state. Documented choice over modifying Phase 1 repo surface.
type CredentialsDeps struct {
	Repo              *repos.Credentials
	Indexers          *repos.Indexers
	Jackett           *jackett.Client
	EnvPath           string
	AutoconfigTrigger func()
}

// credentialDTO is the GET / POST response shape per spec §8.1. Plaintext
// values are NEVER serialized — only "has_*" booleans and metadata.
// `last_used_at` is omitted when nil so the JSON shape matches the spec
// (which lists it as optional).
type credentialDTO struct {
	Name        string     `json:"name"`
	Kind        string     `json:"kind"`
	HasUsername bool       `json:"has_username"`
	HasPassword bool       `json:"has_password"`
	HasCookies  bool       `json:"has_cookies"`
	CreatedAt   time.Time  `json:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at"`
	LastUsedAt  *time.Time `json:"last_used_at,omitempty"`
}

func toDTO(c *repos.Credential) credentialDTO {
	return credentialDTO{
		Name:        c.Name,
		Kind:        c.Kind,
		HasUsername: c.HasUsername,
		HasPassword: c.HasPassword,
		HasCookies:  c.HasCookies,
		CreatedAt:   c.CreatedAt,
		UpdatedAt:   c.UpdatedAt,
		LastUsedAt:  c.LastUsedAt,
	}
}

// credentialPostBody is the POST request body. PATCH semantics — only
// fields whose JSON keys are present (non-nil pointers after decode) are
// updated in DB and mirrored into .env.
type credentialPostBody struct {
	Name     string  `json:"name"`
	Username *string `json:"username,omitempty"`
	Password *string `json:"password,omitempty"`
	Cookies  *string `json:"cookies,omitempty"`
}

// HandleListCredentials handles GET /credentials. Returns a JSON array of
// [credentialDTO] (never plaintext). An empty list serializes as `[]`,
// not `null`, because the dashboard distinguishes "no credentials yet"
// from "API error".
func (d *CredentialsDeps) HandleListCredentials(w http.ResponseWriter, r *http.Request) {
	rows, err := d.Repo.List()
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "list_failed", err.Error())
		return
	}
	out := make([]credentialDTO, 0, len(rows))
	for _, c := range rows {
		out = append(out, toDTO(c))
	}
	writeJSON(w, http.StatusOK, out)
}

// HandleUpsertCredential handles POST /credentials with PATCH semantics
// (spec §8.1: "only fields present are updated"). On success:
//
//  1. The credentials row is upserted in the encrypted DB.
//  2. The matching `<NAME>_USERNAME` / `<NAME>_PASSWORD` / `<NAME>_COOKIES`
//     keys are mirrored atomically into .env (spec §7 row 1).
//  3. The autoconfig orchestrator is replayed via [CredentialsDeps.AutoconfigTrigger]
//     so the new credential is immediately reflected in Jackett.
//
// On .env failure — including a write that returns nil but does not land,
// caught by the read-back — the DB write is reverted (compensating action)
// and VERIFIED. Only a verified revert reports 500
// `env_write_failed_db_rolled_back`; an unverified one reports 500
// `env_write_failed_db_rollback_failed`, because asserting a rollback that
// did not happen is a false statement about system state (§11.4.6,
// BOB-204). The autoconfig replay is NOT triggered on failure.
//
// Existing-row kind preservation: when a row already exists, the row's
// existing `kind` is preserved on partial updates (e.g. PATCHing only
// `cookies` on a "userpass" row leaves the row's kind as "userpass").
// This matches "only fields present are updated" — kind is derived, not
// supplied, so an unspecified update should not flip it.
func (d *CredentialsDeps) HandleUpsertCredential(w http.ResponseWriter, r *http.Request) {
	var body credentialPostBody
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSONError(w, http.StatusBadRequest, "bad_json", err.Error())
		return
	}
	if body.Name == "" {
		writeJSONError(w, http.StatusBadRequest, "missing_name", "name is required")
		return
	}

	// Snapshot prior state for compensating rollback.
	var prior *repos.Credential
	if existing, err := d.Repo.Get(body.Name); err == nil {
		prior = existing
	} else if !errors.Is(err, repos.ErrNotFound) {
		writeJSONError(w, http.StatusInternalServerError, "snapshot_failed", err.Error())
		return
	}

	// Derive kind. If the row pre-exists, preserve the existing kind on
	// partial updates (PATCH semantics — see GoDoc above). Otherwise,
	// userpass when user/pass present, cookie when only cookies present.
	kind := ""
	if prior != nil {
		kind = prior.Kind
	} else if body.Username != nil || body.Password != nil {
		kind = "userpass"
	} else if body.Cookies != nil {
		kind = "cookie"
	} else {
		writeJSONError(w, http.StatusBadRequest, "no_fields", "username/password or cookies required")
		return
	}

	// 1) DB upsert.
	if err := d.Repo.Upsert(body.Name, kind, body.Username, body.Password, body.Cookies); err != nil {
		writeJSONError(w, http.StatusInternalServerError, "db_upsert_failed", err.Error())
		return
	}

	// 2) .env mirror — only the fields the caller actually supplied.
	envKV := map[string]string{}
	if body.Username != nil {
		envKV[body.Name+"_USERNAME"] = *body.Username
	}
	if body.Password != nil {
		envKV[body.Name+"_PASSWORD"] = *body.Password
	}
	if body.Cookies != nil {
		envKV[body.Name+"_COOKIES"] = *body.Cookies
	}
	if len(envKV) > 0 {
		envErr := envfile.Upsert(d.EnvPath, envKV)
		if envErr == nil {
			// READ BACK (§11.4.201): a nil from Upsert says the write call
			// did not error, not that the file on disk now defines the
			// keys. Presence-only — never compare or log VALUES (§11.4.10),
			// and a value comparison would false-positive on the parser's
			// whitespace-trim / quote-strip round trip (§11.4.201(1)).
			keys := make([]string, 0, len(envKV))
			for k := range envKV {
				keys = append(keys, k)
			}
			present, err := envKeysPresent(d.EnvPath, keys)
			switch {
			case err != nil:
				envErr = fmt.Errorf("env write unverifiable: %w", err)
			case len(present) != len(keys):
				envErr = errors.New("env write did not land: .env does not define " +
					strings.Join(missing(keys, present), ", "))
			}
		}
		if envErr != nil {
			// Compensating rollback — PERFORMED, then VERIFIED. The claim
			// in the response code is only made when the verification
			// proves the DB really is back in its pre-call state
			// (§11.4.6: never assert an action that did not happen).
			if rbErr := d.rollbackCredential(body.Name, prior, clearsNewField(prior, &body)); rbErr != nil {
				writeJSONError(w, http.StatusInternalServerError,
					"env_write_failed_db_rollback_failed",
					envErr.Error()+"; rollback: "+rbErr.Error())
				return
			}
			writeJSONError(w, http.StatusInternalServerError, "env_write_failed_db_rolled_back", envErr.Error())
			return
		}
	}

	// 3) Autoconfig replay (spec §7 row 1 "✅ replay autoconfig for that
	// single tracker"). The orchestrator runs the FULL pass — there's no
	// one-tracker mode in [jackett.Autoconfigure] — but it's idempotent
	// (already-configured indexers aren't re-POSTed), so triggering the
	// whole bundle is acceptable and matches the Python parity stance.
	// Production wraps this in `go jackett.Autoconfigure(...)` so the
	// HTTP request thread isn't blocked on Jackett round-trips. Failure
	// here is best-effort: the DB + .env are already consistent.
	if d.AutoconfigTrigger != nil {
		d.AutoconfigTrigger()
	}

	// 4) Re-read for response body so the caller sees post-write timestamps.
	out, err := d.Repo.Get(body.Name)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "post_write_read_failed", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, toDTO(out))
}

// HandleDeleteCredential handles DELETE /credentials/{name} per spec
// §7 row 2: removes the row from DB, removes the `<NAME>_*` triple from
// .env, and removes any linked indexers from Jackett. Linked-indexer
// rows in our DB get their `linked_credential_name` set to NULL via the
// schema's `ON DELETE SET NULL` FK — no application-side cascade needed.
//
// Returns 204 on success (spec §8.1). Idempotent: deleting a missing
// name still returns 204 because the underlying [repos.Credentials.Delete]
// is no-error-on-empty, envfile.Delete of an absent key is a no-op, and
// [jackett.Client.DeleteIndexer] treats 404 as success.
//
// FAIL-CLOSED (§11.4.252, BOB-204). This path combines four dangerous
// capabilities — credential access, shared-state mutation, an external
// side effect, and an irreversible delete — so EVERY step's error is
// checked and any failure returns a 5xx NAMING the unresolved
// precondition. A 204 is emitted only when all three deletes completed.
// Reporting 204 while the plaintext survived in .env (the pre-BOB-204
// behaviour) told the operator a credential was gone while it was still
// readable on disk and no longer managed by the DB.
//
// STEP ORDER is load-bearing, chosen so each failure leaves the least
// harmful residue and a retry converges:
//
//  1. Jackett cascade — the only step reaching an external system, so the
//     most likely to fail. Refusing here leaves DB and .env in the exact
//     pre-call state.
//  2. .env delete, then READ BACK — removes the plaintext. Refusing here
//     leaves the credential intact in BOTH stores (DB and .env agree), so
//     nothing about the credential itself has drifted; only the linked
//     indexer was removed at Jackett, which the autoconfig pass re-derives.
//  3. DB delete last — the canonical record goes only after the plaintext
//     is provably gone, so the DB can never be the one thing missing.
func (d *CredentialsDeps) HandleDeleteCredential(w http.ResponseWriter, r *http.Request) {
	name := strings.TrimPrefix(r.URL.Path, "/api/v1/jackett/credentials/")
	if name == "" || strings.Contains(name, "/") {
		writeJSONError(w, http.StatusBadRequest, "bad_name", "name path segment required")
		return
	}

	// Snapshot linked indexer IDs BEFORE anything mutates: the schema's
	// ON DELETE SET NULL clears `linked_credential_name`, so reading
	// after the DB delete loses the link. A snapshot we cannot take is an
	// unresolvable precondition for the cascade — refuse rather than
	// silently cascade nothing (§11.4.252(2)).
	var jackettIDs []string
	if d.Indexers != nil {
		all, err := d.Indexers.List()
		if err != nil {
			writeJSONError(w, http.StatusInternalServerError, "indexer_snapshot_failed", err.Error())
			return
		}
		for _, idx := range all {
			if idx.LinkedCredentialName != nil && *idx.LinkedCredentialName == name {
				jackettIDs = append(jackettIDs, idx.ID)
			}
		}
	}

	// 1) Jackett-side cascade.
	if d.Jackett != nil {
		for _, id := range jackettIDs {
			if err := d.Jackett.DeleteIndexer(id); err != nil {
				writeJSONError(w, http.StatusBadGateway, "jackett_cascade_failed",
					"indexer "+id+" could not be removed from Jackett, so the credential "+
						"was NOT deleted: "+err.Error())
				return
			}
		}
	}

	// 2) .env delete, then READ BACK (§11.4.201: assert the real condition
	// — a nil error says the call did not fail, not that the key is gone).
	keys := []string{name + "_USERNAME", name + "_PASSWORD", name + "_COOKIES"}
	if err := envfile.Delete(d.EnvPath, keys); err != nil {
		writeJSONError(w, http.StatusInternalServerError, "env_delete_failed",
			"the .env credential variables could not be removed, so the credential "+
				"was NOT deleted: "+err.Error())
		return
	}
	present, err := envKeysPresent(d.EnvPath, keys)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "env_delete_unverified",
			"the .env delete could not be verified, so the credential was NOT deleted: "+err.Error())
		return
	}
	if len(present) > 0 {
		writeJSONError(w, http.StatusInternalServerError, "env_delete_unverified",
			"the .env still defines "+strings.Join(present, ", ")+
				" after the delete, so the credential was NOT deleted")
		return
	}

	// 3) DB delete (FK SET NULL handles indexers.linked_credential_name).
	if err := d.Repo.Delete(name); err != nil {
		writeJSONError(w, http.StatusInternalServerError, "db_delete_failed", err.Error())
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// envKeysPresent re-reads the .env at path and returns which of keys it
// still defines. Returns KEY NAMES only — never values (§11.4.10). A
// missing file is not an error: envfile deliberately does not materialize
// a placeholder, so "no file" genuinely means "no key defined".
func envKeysPresent(path string, keys []string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	defer f.Close()
	kv, err := envfile.Parse(f)
	if err != nil {
		return nil, err
	}
	var out []string
	for _, k := range keys {
		if _, ok := kv[k]; ok {
			out = append(out, k)
		}
	}
	return out, nil
}

// missing returns the members of all that are absent from got. Key names
// only (§11.4.10).
func missing(all, got []string) []string {
	have := make(map[string]bool, len(got))
	for _, g := range got {
		have[g] = true
	}
	var out []string
	for _, a := range all {
		if !have[a] {
			out = append(out, a)
		}
	}
	return out
}

// clearsNewField reports whether the request introduced a value into a
// field the prior row did not have. That is exactly the case a plain
// compensating Upsert CANNOT undo: [repos.Credentials.Upsert] maps a nil
// pointer to COALESCE(excluded.x, x) — "leave unchanged" — so restoring
// "this field was absent" by passing nil silently keeps the new value.
func clearsNewField(prior *repos.Credential, body *credentialPostBody) bool {
	if prior == nil {
		return false
	}
	set := func(p *string) bool { return p != nil && *p != "" }
	return (set(body.Username) && !prior.HasUsername) ||
		(set(body.Password) && !prior.HasPassword) ||
		(set(body.Cookies) && !prior.HasCookies)
}

// rollbackCredential undoes the DB write [CredentialsDeps.HandleUpsertCredential]
// performed, then VERIFIES the undo by reading the row back. It returns a
// non-nil error when the pre-call state was NOT restored, so the caller can
// report honestly instead of asserting a rollback that did not happen
// (§11.4.6 — the BOB-204 false-claim defect).
//
// mustClear selects the restore strategy. When the failed request only
// OVERWROTE fields the prior row already had, a plain Upsert restores them
// and preserves created_at / last_used_at. When it INTRODUCED a field the
// prior row lacked, COALESCE cannot clear it, so the row is dropped and
// re-inserted from the snapshot. Known, bounded cost of that branch: the
// re-inserted row gets fresh created_at/updated_at and loses last_used_at,
// because the Phase 1 [repos.Credentials] surface exposes no
// restore-exactly primitive. The credential PAYLOAD (kind + the three
// secret fields) is restored exactly, which is what the verification below
// asserts; the timestamp metadata is not, and that is stated rather than
// silently claimed.
//
// Error strings carry field NAMES and outcomes only, never values (§11.4.10).
func (d *CredentialsDeps) rollbackCredential(name string, prior *repos.Credential, mustClear bool) error {
	if prior == nil {
		if err := d.Repo.Delete(name); err != nil {
			return fmt.Errorf("delete newly-created row: %w", err)
		}
		if _, err := d.Repo.Get(name); err == nil {
			return errors.New("row is still present after the rollback delete")
		} else if !errors.Is(err, repos.ErrNotFound) {
			return fmt.Errorf("verify rollback delete: %w", err)
		}
		return nil
	}

	if mustClear {
		if err := d.Repo.Delete(prior.Name); err != nil {
			return fmt.Errorf("clear row before restore: %w", err)
		}
	}
	if err := d.Repo.Upsert(prior.Name, prior.Kind,
		ifSet(prior.Username), ifSet(prior.Password), ifSet(prior.Cookies)); err != nil {
		return fmt.Errorf("restore prior row: %w", err)
	}

	// VERIFY the real end state, not the absence of an error.
	got, err := d.Repo.Get(prior.Name)
	if err != nil {
		return fmt.Errorf("verify restored row: %w", err)
	}
	if got.Kind != prior.Kind {
		return errors.New("restored row kind does not match the pre-call state")
	}
	if got.HasUsername != prior.HasUsername || got.Username != prior.Username {
		return errors.New("restored row username field does not match the pre-call state")
	}
	if got.HasPassword != prior.HasPassword || got.Password != prior.Password {
		return errors.New("restored row password field does not match the pre-call state")
	}
	if got.HasCookies != prior.HasCookies || got.Cookies != prior.Cookies {
		return errors.New("restored row cookies field does not match the pre-call state")
	}
	return nil
}

// ifSet returns &s when s != "", else nil — for compensating-rollback
// restoration via [repos.Credentials.Upsert] (which treats nil as
// "leave unchanged" and a non-nil empty pointer also as "leave unchanged",
// per its PATCH semantics).
func ifSet(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

// writeJSON serializes v as JSON with the given status. Errors during
// the encode write are intentionally not surfaced — by the time encoding
// runs, the response status has already been sent and a second write
// would corrupt the wire response.
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// writeJSONError writes a structured `{error, detail}` body. Format
// mirrors what the merge-service dashboard already consumes elsewhere.
func writeJSONError(w http.ResponseWriter, status int, code, msg string) {
	writeJSON(w, status, map[string]string{"error": code, "detail": msg})
}
