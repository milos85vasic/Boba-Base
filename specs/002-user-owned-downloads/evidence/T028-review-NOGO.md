# T028 — Dedicated independent review of `scripts/ownership_repair.sh`: **NO-GO**

**Revision:** 1
**Last modified:** 2026-08-25T18:00:00Z

0 BLOCKING · 2 IMPORTANT · 3 MINOR · 2 NIT. Under §11.4.134 the loop terminates
only on a clean GO with zero findings AND zero warnings. Remediation dispatched.

## The ordering violation is NOT closed by this review

The script ran against the operator's real library at **2026-08-21T17:01:55**,
before this review existed. That stays recorded in `tasks.md`. This review
establishes only (a) safety for FUTURE runs and (b) whether the first real-data
run did harm. It does not un-violate the ordering.

## IMPORTANT-2 — no containment fence on the declared path itself

`:741-742` claims *"The filter IS the scope fence: only items under a declared
path are ever named, so an out-of-scope item cannot be reached even by accident
(FR-005)."* The claim is circular — it fences to the declared path, and nothing
constrains what the declared path may BE.

**Independently re-verified by the conductor, not taken from the review.**
`absolutise()` at `scripts/ownership_repair.sh:379-385`:

```bash
absolutise() {
    local p="$1"
    [[ "${p}" == /* ]] || p="${PROJECT_ROOT}/${p}"
    p="${p%/}"
    [[ -n "${p}" ]] || p="/"
    printf '%s' "${p}"
}
```

Trace for input `/`: starts with `/` so no prefix; `${p%/}` → empty;
`[[ -n "" ]]` false → `p="/"`. **`absolutise("/") → "/"`.**

And `config/owned_paths.yaml:87` ships, verbatim:

```yaml
  - path: "${QBITTORRENT_DATA_DIR:-/mnt/DATA}"
```

So the declared scope contains an env-controlled entry, and `.env` — untracked
by §11.4.10/§11.4.30 design, therefore unreviewed — fully determines which tree
is recursively chowned. **`QBITTORRENT_DATA_DIR=/` yields a recursive walk of the
entire filesystem.** No length, prefix, or containment check exists on that value.

Three escapes were executed under `--dry-run` (mutates nothing, prints exactly
what the fence names): absolute path outside the project; `inside/../../OUTSIDE`
with `..` never resolved; and the live env vector using the SHIPPED entry
unedited.

The fence design is non-trivial and must be surfaced rather than guessed: the
download tree is INTENTIONALLY outside `PROJECT_ROOT`, so a naive
"must be under PROJECT_ROOT" rule would break the feature.

## IMPORTANT-1 — an empty-parsing scope is a fail-open (§11.4.252)

`:355-366` guards unreadable and unparseable scopes (exit 2). Nothing guards a
scope that is valid YAML yielding ZERO entries: empty tokens dropped at
`:388-395`, `(0 declared locations)` at `:610`, walk skipped, marker written and
**exit 0** at `:825-833`.

The script's own header at `:351-353` forbids exactly this — *"Reporting an
unreadable scope as an empty scope would be the §11.4.201(6) false-null: a blind
instrument and a clean tree return the same quiet zero"* — and defends only half.

The sibling `scripts/ownership_precondition.sh:1011-1013` DOES defend it. Executed
side-by-side on one `paths: []` fixture:

```
precondition: OWNERSHIP-PRECONDITION: CANNOT-RUN
  - the declared scope contains no locations
  - a precondition that checked zero locations has verified nothing   EXIT=2
repair    : (0 declared locations) ... complete: 0 item(s) repaired   EXIT=0
```

Two readers of ONE scope file disagree — the identical divergence class the
repair's own header at `:119-130` records having already fixed once for
`absolutise`. Three inputs reproduce, all exit 0 with fingerprint
`e3b0c442…b855` = `sha256("")`.

**Severity is IMPORTANT not BLOCKING, and the reviewer checked rather than
assumed:** `run_ownership_gate()` and the `--recreate` dispatch run the
precondition FIRST, so `./start.sh` refuses. The uncovered path is
`bash scripts/ownership_repair.sh` standalone — the exact remediation command
`start.sh` prints at `:489`, `:966`, and on the precondition-failure path.

## MINOR / NIT

- **MINOR-1** hardlink escape: `chown` acts on the INODE, so `chown -h` does not fence it. Executed: an in-scope hardlink changed an out-of-scope file's owner (`1000:100` → `1000:1000`, links=2). The code CLAIMS impossibility-by-construction at `:136-140`; the claim is wrong as written.
- **MINOR-2** `:573`/`:580` discard stderr; a `FAILED` line cannot distinguish EPERM / EROFS / ENOENT (§11.4.201(5)).
- **MINOR-3** `:702` `chmod … 2>/dev/null || true` — the step that DELIVERS FR-015 swallows its own failure.
- **NIT-1** `:132-134` says the fingerprint is from the scope file's literal text; `lib/ownership.sh:161-163` computes it from the env-EXPANDED parse, so it moves with the environment.
- **NIT-2** `:743` `find` names the declared root itself; a root-owned mount point would suppress the marker permanently and force a full re-walk every start.

## Verified good — with what was executed

- **§11.4.263 clean.** Zero `kill`/`killpg`/`pkill` in the script, `lib/ownership.sh`, or `start.sh` (control-needled). The one `kill` in the call path validates the pid as an integer AND `(( BG_PID > 1 ))` — textbook §11.4.263.
- **Idempotency (§11.4.253) genuine.** `--force` on a repaired tree: `0/0 items need repair`, no new record. The mechanism is the `\( ! -uid -o ! -gid \)` filter at `:743`, not the marker.
- **Symlink fence holds, with teeth.** T018's MINOR-3 ("the scope fence has no test") is REMEDIATED — cases landed in `649622a`. Proven by **two reviewer-authored mutations the author did not write** (§11.4.194(6)(d)), baseline 44/0: dropping `-h` → **5 FAIL**; `find -L` → **3 FAIL**. Both killed.
- **But empty-scope and path-escape are NOT covered:** `grep -niE 'empty scope|no locations|paths: \[\]|absolute|traversal'` over the suite returns **0**, with a same-shape needle returning **89** on the same file.

## Was the 2026-08-21 real-data run harmful? **No — provably**

The reviewer read the revision that ACTUALLY RAN (`39af66c`, 16:52:48, predating
the 17:01:55 run) rather than today's file — today's mtime is 21:00, *after* the
run, so the reviewed code is not the executed code and that distinction is
load-bearing.

`39af66c:scripts/ownership_repair.sh:531-534` carries the short-circuit
`if [[ "${discovered}" -eq 0 ]]; then … continue`. The journal shows `0/0 items
need repair` for all three declared locations ⇒ no path entered `BATCH_PATHS` ⇒
`flush_batch` never ran ⇒ **`chown(2)` was never invoked.**

The counter was proven LIVE, not a constant: an identical run over a tree with
one wrongly-owned item reported `complete: 1 item(s) repaired`.

**Since that run the scope has grown 3 → 6 locations, so the currently-shipped
scope has never been exercised by a real run.**

## Unresolved contradiction, honestly unresolved

`config/owned_paths.yaml:37-41` records 51 items at uid 100999 in `config/` and 1
in the download root; the 17:01:55 run found `0/0`; `config/` today measures **0**
wrongly-owned (control-needle-verified). Either the provenance measurement
predates a repair by other means, or those items were fixed out of band.
**UNKNOWN:** which — the marker and record that would have settled it were
deleted before the review looked.

## What could not be analysed

1. The reviewed code is not the executed code; intermediate revisions (`649622a`, `3a83506`, `7b45113`) unaudited for transient defects.
2. `podman unshare chown -h 0:0` (`:580`) never executed (`CONTAINER_RUNTIME=` empty per the Hard Stop) — and it is the ONLY path that can repair the actual production defect (uid 100999). **UNCONFIRMED.**
3. TOCTOU on non-final path components: `chown -h` protects only the last one. Linked to **BOB-159** (warm-start write window) rather than minting a new id (§11.4.214).
4. `CONTAINER_RUNTIME` interpolated as a command name at `:580` with no validation — reasoned about, not executed. **UNKNOWN.**
5. Journal coverage partial — only `boba-stack.service`; manual runs would not appear.
6. Scale: experiments ran on trees of a few files; `BATCH_SIZE=256` behaviour on a 6458-item library untested.

## Owed follow-up

IMPORTANT-2 is a §11.4.238 coverage escape — found by a review agent reading
source, not by the automated regime. It needs its own tracked item and a
coverage-escape audit. **Filing deferred:** `docs/workable_items.db` is a tracked
SQLite and four agents are live in this checkout; concurrent DB writes are the
known BOB-068 shared-checkout race. File once the tree is quiescent.
