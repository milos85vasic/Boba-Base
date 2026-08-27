# T028 — Round-2 independent re-review of `scripts/ownership_repair.sh`: **NO-GO**

**Revision:** 1
**Last modified:** 2026-08-26T14:55:00Z

Reviewer: independent agent, label `(T11/002-user-owned-downloads - milos85vasic - fable - ?)`,
structurally separate from the author and from the conductor whose probes it re-ran
(§11.4.142/§11.4.194/§11.4.209/§11.4.134). Reviewed tree: HEAD `a3e1141`, all four
artifacts committed and clean (`git status --porcelain` empty for them). Content
identities (sha256, first 16): `ownership_repair.sh ae025b74602414ca`,
`lib/ownership.sh b1b4e7ce217c8635`, `test_ownership_repair.sh e3aaa7ed49e663f0`,
`owned_paths.yaml 26375798edfee773`. Remediation commit under review: `8a08d49`.

**0 BLOCKING · 0 IMPORTANT · 1 MINOR · 2 NIT.** Every round-1 finding is verified
closed (one by reconciliation-with-diagnosis, stated below). The three residual
findings are NEW, authored by this round's mutations, and none touches the primary
hazard T028 exists for (a chown of the wrong tree). Under §11.4.134 the loop
terminates only on zero findings and zero warnings, so the verdict is NO-GO and the
checkbox stays unchecked — but the remaining iteration is small and enumerated.

Suite baseline reproduced twice: **86 passed, 0 failed, 0 skipped** (run under
`nice -n 19`; the script additionally re-execs itself under `nice -n 19 ionice -c 3`).
All destructive probes ran against fixture scopes under `--scope` with `--state-dir`
pointed at a scratch directory; the real `config/owned_paths.yaml` was never edited
and the live `logs/ownership/` never written by this review.

---

## 1 — Round-1 findings: verified status

### IMPORTANT-2 (no containment fence on the declared path) — **CLOSED, verified by execution**

The fence now exists as `ownership_path_fence()` + `ownership_normalise_path()` in
`scripts/lib/ownership.sh:314-529`, consumed by the repair at
`scripts/ownership_repair.sh:493-519` BEFORE the marker check (`:630`) and before any
walk. I re-ran the conductor's probes with the correct instrument (`--scope`, after
first proving the needle: a 1-entry fixture reports `(1 declared locations)`, not the
real scope's 6):

```
path "/"                    → exit 2  "'/' resolves to the filesystem root '/' — a recursive
                                       ownership change of the whole filesystem is never a declared scope"
path "/etc"                 → exit 2  "is inside the system tree /etc; …never a download root"
path "inside/../../OUTSIDE" → exit 2  "resolves OUTSIDE the project root … may not climb out with '..'"
/mnt/DATA (golden-FALSE)    → NOT refused; proceeds to walk, fails honestly only because the
                              path does not exist on this host (exit 1, "does not exist")
```

The original live vector is dead end-to-end: with the SHIPPED scope file unedited and
only the environment moved, `QBITTORRENT_DATA_DIR=/ … --dry-run` → exit 2, REFUSED,
"nothing was touched, no record was written, no marker was written". §11.4.251 held:
`ownership_precondition.sh:1074` consumes the SAME fence — no second dialect.
Suite Case 17 covers refusals AND the golden-FALSE legitimate shapes (all PASS,
re-run live this round).

### IMPORTANT-1 (empty-parsing scope fail-open) — **CLOSED, verified by execution**

`paths: []` → exit 2, "the declared scope contains no locations … refusing to write a
completion marker — nothing was touched" (`ownership_repair.sh:434-439`), matching the
sibling precondition's semantics. Suite Case 16 covers all three total-empty shapes
(`paths: []`, mistyped `path:`, every `${VAR}` expanding empty) with a control needle;
all PASS live. The PARTIAL-empty case is NOT covered — see R2-M1 below.

### MINOR-2 (chown stderr discarded) — **CLOSED, verified by execution**

All three mutation sites capture stderr (`:719`, `:731`, `:916` — `2>&1 >/dev/null`);
the remaining `2>/dev/null` occurrences (`:585,:598,:619,:645`) are non-mutating
record housekeeping, each with its own failure handling. Injected-EROFS run (chown
shim on PATH, fixture scope, temp state dir):

```
FAILED …/erofs-tree/item — cannot change ownership to 1000:1000 (1/1 …):
  chown: chown: changing ownership of 'X': Read-only file system;
  fallback: no container runtime available for the namespace fallback
EXIT=1, no marker written
```

The reason and the fallback's reason both reach the operator (§11.4.201(5)).

### MINOR-3 (chmod `|| true` swallowed FR-015) — **CLOSED**

`:916-921` captures `_chmod_err`, reports "ownership repaired, but mode … could not be
restored (FR-015)", counts `TOTAL_MODE_FAILED` separately, records
`mode-restore-failed`, sets `RC=1` (blocks the marker). Suite Case 20 executed PASS in
both baseline runs this round.

### MINOR-1 (hardlink impossibility overclaim) — **CLOSED**

The header (`:161-191`) now states the escape as MEASURED, bounds it (same-filesystem,
needs an in-scope writer, ownership-only, always TOWARD the operator), and records why
a `st_nlink > 1` fence was rejected (it would refuse the ordinary torrent-client/
library sharing case — a §11.4.201(1) false positive). Case 18 machine-checks that the
text and behaviour agree; PASS live.

### NIT-1 (fingerprint prose vs computation) — **CLOSED**

`:132-152` now documents that the fingerprint is computed from the parsed,
environment-expanded entries, with measured hashes for env-unset / env-set / file-bytes
(all three distinct) and the operational edge (a shell that has not sourced `.env`
computes a different fingerprint). Case 21 asserts the prose matches measurement; PASS.

### NIT-2 (find names the declared root) — **CLOSED BY RECONCILIATION, verified by execution; the factual predicate stands**

This was mine to verify independently. Both halves executed:

* The walk DOES still name the declared root: a fixture whose root directory itself is
  wrongly-grouped produced `would chown 1000:1000 (was 1000:10) …/rootcase` under
  `--dry-run` — the root itself, not only its contents.
* With a shim failing chown ONLY on the root: `FAILED …/rootcase — …` followed by the
  new diagnosis "`^ that path is the DECLARED ROOT of this entry, not a file inside
  it … the remedy is the mount … the next start re-walks the whole declared scope`",
  exit 1, NO marker.

So a root-owned mount point still suppresses the marker and forces a full re-walk
every start — the remediation deliberately PRESERVED the failure and added the
diagnosis, with the recorded argument (`:816-834`) that writing the marker over an
unrepaired in-scope item would be the §11.4.201 false pass and §11.4.120 forbids
weakening the assertion. I judge that a legitimate reconciliation, not a dodge: the
operator is now told the remedy is the mount, and the alternative behaviours are all
worse. Case 22 machine-checks the diagnosis with a control needle.

---

## 2 — Reviewer-authored mutations (§11.4.194(6)(d)) — none previously written

Every probe below is new to this review. Instrument honesty first: two of my own
probes misfired before yielding data — an `| head` pipeline SIGPIPE'd the script and
reported `EXIT=141` (my pipe, not the artifact), and one re-run consumed a scope file
a previous probe had clobbered (reported the wrong shape's exit). Both were detected
by re-reading the lines rather than trusting the numbers, and re-run cleanly
(§11.4.201(7)(c): the path is part of the instrument).

| # | Mutation | Result |
|---|----------|--------|
| M1 | `--force --dry-run` with shipped scope + `QBITTORRENT_DATA_DIR=/` — does any flag bypass the fence? | **KILLED.** Exit 2, REFUSED; fence at `:493-519` runs before the marker check and the dry-run branch. |
| M2 | Multi-entry scope, LEGAL entry first, `/etc` second — is only the first entry fenced? | **KILLED.** Every entry judged; one refusal fails the whole run (exit 2, "names 1 path(s) this repair must never walk"), nothing walked. |
| M3 | Symlinked declared ROOT (`link → target` holding a wrongly-owned file) — does `find -P` really refuse to descend, or was that assumed? | **KILLED, claim confirmed empirically.** `0/0 items need repair`; control needle: the same scope pointed at the real target names the victim (`would chown … (was 1000:10)`). |
| M4 | Trailing-slash spellings `link/` and `link//` (a surviving slash would make the kernel resolve the link) | **KILLED.** `absolutise()` strips one slash and `ownership_normalise_path()` (applied to `E_PATH` at `:508`) removes the rest; both spellings → `0/0`, no traversal. |
| M5 | INTERMEDIATE symlink component: entry `…/piv/hop/data` with pre-existing `hop → real` | **SURVIVED, as documented.** The kernel resolves the non-final component and the walk names `…/hop/data/victim2`. No race needed. Bounded: exploiting it requires write control ABOVE the declared root (outside every container bind mount), and such an actor can edit `.env` anyway. Already catalogued by round 1 and linked to BOB-159; this round upgrades it from reasoned to measured. See R2-N1 for the one documentation sentence owed. |
| M6 | Env-supplied RELATIVE escape: `QBITTORRENT_DATA_DIR='../../../../etc'` through the shipped entry shape | **KILLED.** Treated as repo-relative, normalised to `/run/media/etc`, refused: "resolves OUTSIDE the project root", exit 2. |
| M7 | Shape variants `//etc`, `/./etc`, `/etc/.`, `/etc/..`, `/etc/passwd/..` | **ALL KILLED.** Normalisation collapses each to its real target; `/etc/..` → `/` (root refusal), the rest → `/etc` (system-tree refusal); all exit 2. |
| M8 | Command-substitution injection: `path: "/tmp/x$(touch /tmp/T028_PWNED)/y"` | **KILLED.** No eval anywhere on the path's route; `/tmp/T028_PWNED` was never created; the entry is treated as a literal string. |
| M9 | Whitespace-only path `"   "` | **KILLED (honest failure).** Resolved as repo-relative to `<root>/   `, fence-accepted (inside root), fails honestly at the walk ("does not exist and is not optional", exit 1). No silent nothing, no escape. |
| M10 | Newline smuggled through the env var (`QBITTORRENT_DATA_DIR=$'…/tree\n/etc'`) — row-splitting in the TSV entry stream | **KILLED.** The smuggled fragment becomes its own row and the FENCE judges it: `/etc` refused, exit 2. Row-splitting is real but every fragment is fenced, and an env-writer could set a legal-shape path directly — no capability gained. The first fragment's blanked metadata fields default conservative (`recursive=""` → `-maxdepth 0`). |
| M11 | PARTIAL-empty expansion: 2-entry scope where one entry is `${UNSET_VAR}` (no default) | **SURVIVED — new finding R2-M1.** Reports `(1 declared locations)`, walks the survivor, exit 0. One DECLARED location silently vanished. |
| M12 | Depth-floor boundary: `/mnt` vs `$HOME` | `/mnt` **KILLED** (1 component, floor refusal). `/home/milosvasic` **ACCEPTED** — the walk started (killed by my own 20s probe timeout; dry-run, harmless). In-bounds per the fence's documented shape-only honest boundary; see R2-N2 for the one hazard worth naming. |

Not attempted, with reasons: very-long-path (bounded by ARG_MAX; the fence is pure
string ops; low yield), NUL-in-path (bash command substitution strips NUL before both
the fence and the walk see it, so both readers agree, and no Linux path can carry NUL),
and a timed check-vs-walk race for M5's link swap (the pre-existing-link form proves
the same reach deterministically without a race, which is strictly stronger evidence).

---

## 3 — New findings this round

### R2-M1 — MINOR: a `${VAR}`-without-default entry that expands empty is dropped silently (partial scope narrowing)

`ownership_scope_entries` (`lib/ownership.sh:96-121`) drops an entry whose expanded
path is empty (`if not path: continue`). The IMPORTANT-1 remediation refuses the
TOTAL-empty scope; the PARTIAL case walks the survivors and exits 0. Measured:

```
scope declares 2 paths (${UNSET_VAR_T028} + fixture dir)
→ "(1 declared locations)" … "0/0 items need repair" … EXIT=0
```

Same §11.4.201(6) false-null family the remediation itself names: a declared location
becomes invisible to the repair, the precondition (same parser, no raw-vs-parsed
crosscheck — grepped) and the marker, with no report. Bounds that keep it MINOR:
unreachable from the shipped scope (every entry is literal or carries `:-default`,
and the parser's `or`-semantics make set-but-empty fall to the default); both
consumers drop identically (no divergence); the `(N declared locations)` line gives
weak detectability; the fingerprint still moves when the env changes, so re-arming
works. No suite coverage (`unset var / partial drop` greps: 0 matches, against a
suite that matches 40+ lines for the sibling shapes). Remediation shape: refuse the
scope (exit 2) when a raw `paths:` entry produced no parsed row — the exact decision
already taken for the total case, applied per-entry.

### R2-N1 — NIT: the fence's HONEST BOUNDARY does not name static intermediate-symlink resolution

M5 measured that a pre-existing symlink in a NON-final component steers the walk to
the link's target while the fence judges only the spelling. The class is acknowledged
obliquely (the TOCTOU rationale in `ownership_normalise_path`, `lib/ownership.sh:319-324`,
frames it as a race artifact) and round 1 linked it to BOB-159 — but the static,
no-race form is not stated where the fence declares its limits. One sentence in the
fence's HONEST BOUNDARY paragraph ("the fence judges the spelling; the kernel resolves
intermediate components at walk time, so a symlink above the declared root steers the
walk — contained only by who can write those components") closes the documentation gap.

### R2-N2 — NIT: one concrete in-bounds hazard worth naming (or cheaply denying): rootless-podman storage under `$HOME`

`/home/<user>` (2 components, not denylisted — deliberately, per the recorded
`/run/media` reasoning) passes the fence; measured, the walk started. A declared root
at or above `~/.local/share/containers` would, via the `podman unshare` fallback,
rewrite the subuid-owned rootless container storage this project's own §11.4.161
mandate depends on — recoverable (re-pull images) but destructive to the runtime.
A computed, targeted deny of `$HOME/.local/share/containers` has ~zero
false-positive cost (no download root lives inside container storage); at minimum the
fence header's honest boundary should name the hazard. Not graded higher because the
documented shape-only boundary explicitly anticipates well-shaped absolute paths it
cannot judge, and `/home/<user>/Downloads` is an ordinary download root the fence
must keep accepting.

---

## 4 — The ordering violation (NOT closed here) and the real-run ledger

The 2026-08-21T17:01:55 run's harmlessness proof STANDS: `39af66c` (the revision that
ran) still carries `discovered -eq 0 → continue` (re-read from the immutable object
this round), the journal shows `0/0` at all 3 then-declared locations, and the counter
is live, not constant (my fixture runs named items whenever they existed; the suite
proves the same). The violation itself remains OPEN as recorded in `tasks.md` — a
later review cannot un-violate the ordering, and this one does not claim to.

**New fact this round, recorded rather than absorbed:** a SECOND real-data run
happened at 2026-08-25 20:52:21 local (18:52:21Z, `boba-stack.service`) — after
round 1's NO-GO (18:00Z) and 17 minutes BEFORE the remediation commit `8a08d49`
(21:09:12 +0200) landed, so which exact working-tree bytes ran is not reconstructable.
The harmlessness proof is therefore built revision-independently: the journal shows
`0/0 items need repair` at ALL SIX locations (including the real library
`/run/media/milosvasic/DATA4TB/Downloads`) and `complete: 0 item(s) repaired`, and
BOTH candidate revisions (`7b45113:760`, HEAD `:980`) carry the short-circuit, so
`chown(2)` was never invoked either way. This supersedes round 1's "the
currently-shipped scope has never been exercised by a real run" — it now has been,
harmlessly. The run belongs to the SAME open ordering-violation record (§11.4.214:
recurrence links, never a new mint), not a new violation class. Round 1's "unresolved
contradiction" (51 items at 100999 in the provenance vs 0 found) remains UNKNOWN;
nothing this round settled it.

## 5 — What this round did not analyse

Carried forward unchanged from round 1: the `podman unshare` fallback path has still
never been executed against a real subuid-owned item (UNCONFIRMED — every run and
fixture here used `CONTAINER_RUNTIME=` set-but-empty per the Hard Stop);
`CONTAINER_RUNTIME` as an unvalidated command name at `:731`; scale behaviour at
`BATCH_SIZE=256` over the 6458-item library (the 20:52 run walked it but discovered
0, so the batch path stayed cold); intermediate revisions between reviews unaudited.

## Verdict

**NO-GO** under §11.4.134 — 1 MINOR + 2 NIT remain, all new, all enumerated with
remediation shapes above. All 7 round-1 findings verified closed (NIT-2 by
reconciliation-with-diagnosis). The fence holds against every escape this round could
author except the two documented-and-bounded reaches (hardlinks, intermediate
symlinks), both of which are recorded honestly in the artifact or tracked. One more
small iteration closes the loop.
