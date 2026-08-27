# T041 Review-Scope Map — `git diff main...HEAD` (002-user-owned-downloads)

**Revision:** 1
**Last modified:** 2026-08-26T19:05:00Z
**Status:** active
**Status summary:** Read-only PREFLIGHT scope map for T041. Produced so the
§11.4.209 Fable-`xhigh` review can be exhaustive per §11.4.194(1) rather than
sampling whatever the diff surfaces first. This document performs NO review and
issues NO verdict.
**Authority:** §11.4.194(1) scenario-space enumeration; §11.4.201(6)(7) needled
measurement; §11.4.44 revision header.
**Scope:** `git diff main...HEAD` measured at HEAD `a3e1141`, merge-base
`79c00b9`, 97 commits.

---

## 0. Preflight facts + instrument discipline

| Fact | Value |
|---|---|
| Branch | `002-user-owned-downloads` |
| HEAD | `a3e1141777914f3d71d62a6cd32a4c79c7f43842` |
| merge-base with `main` | `79c00b9bf8e4a73e50f87e7c5601ee87d74d2431` |
| Commits `main..HEAD` | 97 |
| Files changed | **923** |
| Insertions / deletions | **+143,745 / −3,815** |
| Binary files in diff | 322 (321 PDF + 1 `.db`) |
| Measured at (UTC) | 2026-08-26T18:57–19:05Z |

### Instruments and their control needles (§11.4.201(7)(b))

Every count below came from an instrument that was proven able to see through
the **same path** before any zero was reported. Needle results:

| Instrument | Known-present needle | Negative control |
|---|---|---|
| `git diff --numstat` → grep on path | `specs/…/tasks.md` = 1 | absent path = 0 |
| `git ls-files` → grep -x | `start.sh` = 1 | absent = 0 |
| `git ls-files --others` | `lan_route_auth_analyzer.py` = 1 | absent = 0 |
| `grep -rl` into `tests/` | `def test_` = 200 files | absent = 0 |
| `find -mmin` | `ownership.sh -mmin -600` = 1 | absent name = 0 |
| gate-registration grep | 8/8 gates found | `check_cm_zzz_absent_gate` = 0 |

**Two false-nulls were caught by this discipline and are recorded because the
reviewer will hit the same traps:**

1. **`grep -E '^specs/'` on `--numstat` output returns ZERO.** `--numstat` rows
   are `ins \t del \t path`, so the line does not start with the path. The
   corrected instrument is `awk -F'\t' '$3 ~ /^specs\//'`, which returns 21.
   A line-anchored pattern against numstat is a silent false-null.
2. **Gate-mutation pairing under one naming convention returns ZERO.** The repo
   uses **two** conventions side by side — `tests/pre_build/test_check_cm_<x>.sh`
   *and* `tests/pre_build/test_cm_<x>.sh`. Searching for one misses the other.
   All 8 changed gates are paired; a single-convention scan would have reported
   3 of them unpaired. See §2.
3. `find -newermt` with a **relative** argument errors on this host's `find`
   (it is `bfs`); with stderr swallowed that reads as an empty result. All
   recency measurements here use `-mmin`.
4. `git status --porcelain` collapses untracked **directories** to one entry.
   The 20 `??` entries expand to **24 untracked files**; each collapsed
   directory was expanded with `find -type f` (§6).

---

## 1. The diff, measured and classified

### 1.1 Classification rule (reproducible)

First match wins, top to bottom. Reproduce with
`awk -F'\t' -f classify.awk <(git diff main...HEAD --numstat)`:

```awk
if (p == "constitution")                                      -> submodule-pointer
if (p ~ /\.db$/)                                              -> tracked-data
if (p ~ /^docs\/qa\/.*\.(json|txt|log|diff)$/)                -> qa-evidence
if (p ~ /^tests\//)                                           -> test+fixture
if (p ~ /\/fixtures?\//)                                      -> test+fixture
if (p ~ /(^|\/)(test_[^\/]*|[^\/]*_test)\.(py|sh|go|ts|js)$/) -> test+fixture
if (p ~ /\.spec\.ts$/)                                        -> test+fixture
if (p ~ /\.(html|pdf|docx)$/)                                 -> generated-export
if (p ~ /^scripts\/pre_build\//)                              -> gate-script
if (p ~ /^constitution\/scripts\/gates\//)                    -> gate-script
if (p ~ /^challenges\/scripts\//)                             -> gate-script
if (p ~ /(^|\/)pre_build_verification\.sh$/)                  -> gate-script
if (p ~ /(^|\/)(check|cm|guard)_[^\/]*\.(sh|py)$/)            -> gate-script
if (p ~ /\.(py|sh|go|ts|tsx|js|scss)$/)                       -> executable-source
if (p ~ /\.(json|ya?ml|toml|service|target|conf|cfg|ini)$/)   -> config
if (p ~ /(^|\/)\.gitignore$/ || /(^|\/)\.env/)                -> config
if (p ~ /(^|\/)(Dockerfile|Makefile|docker-compose[^\/]*)$/)  -> config
if (p ~ /\.(log|diff)$/)                                      -> qa-evidence
if (p ~ /\.(md|txt)$/)                                        -> governance+docs
otherwise                                                     -> UNCLASSIFIED
```

**Precedence is load-bearing, not incidental.** `tests/` precedes the
`.html` rule *on purpose*: `tests/ux/fixtures/*.html` are hand-authored
oracles, not generated exports. This was independently confirmed in §5 —
those four files are the only changed `.html` with no `.md` source anywhere
on disk.

### 1.2 Bucket totals

| Bucket | Files | Insertions | Deletions | Binary |
|---|---:|---:|---:|---:|
| generated-export | 641 | 84,617 | 1,709 | 321 |
| qa-evidence | 75 | 13,664 | 799 | 0 |
| governance+docs | 74 | 14,260 | 687 | 0 |
| test+fixture | 57 | 18,396 | 56 | 0 |
| **executable-source** | **53** | **8,353** | **427** | 0 |
| config | 11 | 470 | 10 | 0 |
| **gate-script** | **10** | **3,984** | **126** | 0 |
| tracked-data | 1 | — | — | 1 |
| submodule-pointer | 1 | 1 | 1 | 0 |
| **TOTAL** | **923** | **143,745** | **3,815** | 322 |

Verification: `UNCLASSIFIED = 0`; row count 923 = numstat 923; recomputed
`ins=143745 del=3815` reconciles exactly with `--shortstat`.

### 1.3 The headline ratio

**The adversarial-review surface is `gate-script` + `executable-source` = 63
files, +12,337 / −553 — 6.8% of the files and 8.6% of the insertions.**
The other 860 files are exports, evidence, docs and data. §5 says which of
those still need eyes.

### 1.4 Two classification caveats the reviewer should know

- `download-proxy/requirements.txt` (+114/−15) landed in **governance+docs**
  because the rule keys on `.txt`. It is a **dependency manifest** and belongs
  to the §11.4.246 supply-chain surface. Do not let the bucket hide it.
- `docs/qa/BOB-164/*.py` (662 lines) landed in **executable-source** correctly,
  but they live under `docs/` and will be invisible to any reviewer who scopes
  by directory rather than by extension.

---

## 2. The executable surface — what actually needs adversarial review

Coverage columns: **DOC** = companion doc at `docs/scripts/<stem>.md`
(§11.4.18); **MUT** = a paired mutation harness exists; **TEST** = the stem is
referenced by a file under `tests/`. Absences below are reported **as
findings-for-the-reviewer**, not fixed here.

### 2.1 Tier 1 — the feature core (ownership), 4,086 new executable lines

| File | Δ | DOC | MUT | TEST |
|---|---:|:--:|:--:|:--:|
| `scripts/ownership_precondition.sh` | +1,229 | YES | — | YES |
| `scripts/pre_build/check_cm_ownership_invariants.sh` | +1,095 | **NO** | YES (`tests/pre_build/test_check_cm_ownership_invariants.sh`, 934 ln) | YES |
| `scripts/ownership_repair.sh` | +1,059 | YES | — | YES |
| `scripts/lib/ownership.sh` | +529 | **NO** | — | YES |
| `config/owned_paths.yaml` | +174 | (data pack) | — | YES |

Backed by **4,256 lines of test**: `test_ownership_repair.sh` (+2,109),
`test_check_cm_ownership_invariants.sh` (+934), `test_ownership_precondition.sh`
(+594), `test_ownership_rootless_detection.sh` (+348),
`tests/ownership/test_container_writes_owned_files.py` (+262).

**Findings for the reviewer:**
- **F-1** `scripts/lib/ownership.sh` — the shared library every other ownership
  component sources — has **no `docs/scripts/ownership.md`** (§11.4.18 requires
  one for every shell script). It is also the only Tier-1 file with no
  dedicated test file of its own; it is covered only transitively through its
  callers, so a defect in a library function no caller currently exercises is
  invisible.
- **F-2** `check_cm_ownership_invariants.sh` (1,095 lines, the FR-011 gate) has
  **no companion doc**, unlike 6 of the 8 other changed gates which do.

### 2.2 Tier 2 — the other new/changed gates

| File | Δ | DOC | Paired harness | Harness ln |
|---|---:|:--:|---|---:|
| `scripts/pre_build/check_cm_closure_seam_binds.sh` | +674 | YES | `test_check_cm_closure_seam_binds.sh` | 258 |
| `scripts/pre_build/check_cm_go_toolchain_matches_builder.sh` | +364 | YES | `test_check_cm_go_toolchain_matches_builder.sh` | 271 |
| `scripts/pre_build/check_cm_plugin_count.sh` | +351 | **NO** | `test_check_cm_plugin_count.sh` | 313 |
| `scripts/pre_build/check_cm_runtime_deps_parity.sh` | +343 | YES | `test_check_cm_runtime_deps_parity.sh` | 313 |
| `scripts/pre_build/check_cm_served_bundle_fresh.sh` | +200 | **NO** | `test_cm_served_bundle_fresh.sh` | 264 |
| `scripts/pre_build/check_cm_export_charset_valid.sh` | +107 | YES | `test_cm_export_charset_valid.sh` | 324 |
| `scripts/pre_build/check_cm_workable_items_binary_fresh.sh` | +97 | YES | `test_cm_workable_items_binary_fresh.sh` | 100 |
| `scripts/pre_build_verification.sh` | +410 / −61 | **NO** | — | — |
| `challenges/scripts/ddos_resilience_challenge.sh` | +343 / −65 | **NO** | — | — |

All 8 `check_cm_*` gates **do** register in `pre_build_verification.sh`
(verified per-gate; negative control returned 0). The file now declares
invariants up to **51** and references `check_cm_` 38 times.

**Findings for the reviewer:**
- **F-3** The **harness naming is split** across `test_check_cm_*` (5 files) and
  `test_cm_*` (3 files). This is not cosmetic: it defeats convention-based
  discovery and produced a live false-null during this preflight. Any gate
  added under the wrong convention will read as unpaired.
- **F-4** `pre_build_verification.sh` (+410/−61, touched by **12 commits**) has
  no companion doc and no harness of its own. It is the seam through which all
  51 invariants run — a defect in its dispatch logic silently disarms gates
  that each individually pass their own mutation test. Per §11.4.249 it is the
  **gate** role; nothing here audits it (the **verifier** role is vacant).
- **F-5** The mutation harnesses were located and their vocabulary counted, but
  **this preflight did not execute any of them**, so "a fixture that dies under
  the mutation" is **UNVERIFIED** for all 8. Vocabulary-hit counts
  (`mutat|golden.?bad|MUST FAIL|polarity`) range 4→34; the two lowest
  (`closure_seam_binds` = 4, `served_bundle_fresh` = 4,
  `workable_items_binary_fresh` = 6) are the ones most worth opening first.

### 2.3 Tier 3 — runtime service code (Python / Go)

| File | Δ | DOC | MUT | TEST |
|---|---:|:--:|:--:|:--:|
| `download-proxy/src/merge_service/deduplicator.py` | +417 / −199 | — | YES | YES |
| `plugins/download_proxy.py` | +375 | — | — | YES |
| `download-proxy/src/api/hooks.py` | +257 / −29 | — | YES | YES |
| `download-proxy/src/main.py` | +180 / −28 | — | — | YES |
| `download-proxy/src/merge_service/search.py` | +172 / −11 | — | YES | YES |
| `plugins/rutracker.py` | +71 / −11 | — | — | YES |
| `download-proxy/src/api/routes.py` | +57 / −2 | — | YES | YES |
| `download-proxy/src/api/rate_limit.py` | +42 / −5 | — | YES | YES |
| `qBitTorrent-go/cmd/boba-jackett/main.go` | +18 / −1 | — | — | YES |

`deduplicator.py` is the largest **rewrite** in the diff (−199 lines deleted,
the highest deletion count of any executable file). It has a 3,475-line golden
fixture (`tests/unit/merge_service/bob145_dedup_golden.json`) — per §11.4.245
the reviewer must confirm that golden is an **independent** oracle and not a
record of what the new code happens to emit.

### 2.4 Tier 4 — infrastructure / orchestration scripts

| File | Δ | DOC | Note |
|---|---:|:--:|---|
| `scripts/flight-recorder/flight-recorder.sh` | +591 | YES | new subsystem |
| `start.sh` | +348 / −5 | **NO** | invokes the ownership precondition |
| `scripts/diagnostics/bob131_container_death_triage.sh` | +334 | YES | |
| `scripts/hooks/check-brief-inputs.sh` | +282 | YES | |
| `scripts/testing/update_readme_doc_links.sh` | +259 | YES | |
| `scripts/hooks/unattributed-commit-guard.sh` | +237 | YES | commit seam |
| `scripts/flight-recorder/install.sh` | +114 | **NO** | writes systemd user units |
| `scripts/flight-recorder/uninstall.sh` | +109 | **NO** | **no test** |
| `scripts/compute-badges.sh` | +97 / −4 | YES | §11.4.259 |
| `scripts/verify-all-constitution-rules.sh` | +73 | **NO** | **no test** |
| `scripts/diagnostics/bob137_thread_census.sh` | +69 | **NO** | **no test** |
| `scripts/run_all_challenges.sh` | +56 / −9 | **NO** | |
| `scripts/hooks/docs-sync-commit-seam.sh` | +43 / −7 | **NO** | **no test** |
| `scripts/install.sh` | +31 / −5 | **NO** | |
| `ci.sh` | +32 | **NO** | |
| `scripts/boba-svc.sh` | +15 | **NO** | **no test** |
| `scripts/commit-push-all.sh` | +5 / −1 | YES | §11.4.234 |

**F-6** Six changed shell scripts have **neither a companion doc nor any test
reference**: `flight-recorder/uninstall.sh`, `verify-all-constitution-rules.sh`,
`bob137_thread_census.sh`, `docs-sync-commit-seam.sh`, `boba-svc.sh`,
`bob137_soak.sh`. §11.4.18 requires the doc unconditionally; §11.4.224(A)
requires an executing test through the real invocation path (a `bash -n`
parse-check does not satisfy it). `uninstall.sh` and `docs-sync-commit-seam.sh`
are the two that mutate state.

### 2.5 Tier 5 — frontend

**15 of 22 frontend files are cosmetic** (≤10 changed lines each, 46 insertions
total — palette-token renames). The substantive set is only:
`palette.model.ts` (+338/−14), `styles.scss` (+27/−2),
`dashboard.component.scss` (+56/−44), `node-shims.d.ts` (+30), plus two new
spec files (`palette.contrast.spec.ts` +285, `style-contrast.spec.ts` +579).

**F-7** Nine frontend files show **no test reference at all** (the `jackett/`
component subtree). They are all in the cosmetic set, so the risk is low — but
it is a real coverage hole, not an absence of risk.

### 2.6 Analyzers under `docs/`

`docs/qa/BOB-164/axe_contrast_scan.py` (+544) and `measure_rendered_cascade.py`
(+118) are **analyzers**. §11.4.107(10) requires every analyzer to ship
golden-good + golden-bad self-validation. Neither has a doc, a test, or a
visible fixture pair. **F-8.**

---

## 3. The §11.4.194(1) scenario space

This is the section past rounds kept finding under-covered. Each factor below
is an **independent term**; a degenerate value in **any one** flips the outcome,
so each must be verified separately rather than assumed from a sibling.

### 3.1 `probe_location()` — `scripts/lib/ownership.sh:299`

Emits `ok | wrong-owner:<uid> | unwritable | absent`. The verdict is a product
of **at least seven** independent terms:

| # | Factor | Degenerate value | Consequence |
|---|---|---|---|
| 1 | path exists | missing | `absent` |
| 2 | path **type** | file vs directory | **two entirely different code paths** — a file `stat`s the target directly, a directory creates a probe. Both must be covered. |
| 3 | `mktemp` in the dir | fails | `unwritable` |
| 4 | `stat -c %u` on the probe | empty output | `unwritable` |
| 5 | uid equality vs `id -u` | mismatch | `wrong-owner:<uid>` |
| 6 | **filesystem uid semantics** | `vfat`/`exfat`/`ntfs` mounted with `uid=` | **every** file reports the mount uid, so the probe can return `ok` on a filesystem that cannot express ownership at all |
| 7 | mount kind under the path | bind vs volume vs overlay | changes which uid the write lands as |

**Factor 6 is the classic multi-factor gap.** The download root is
`QBITTORRENT_DATA_DIR` (`/mnt/DATA`) — a host-specific mount whose filesystem
the reviewer must not assume. The source header justifies probing over
inspecting, which is correct, but the reviewer must confirm whether a
uid-flattening filesystem produces a **false `ok`** (a §11.4 PASS-bluff) and
whether that case is covered by `tests/unit/test_ownership_rootless_detection.sh`
or anywhere else.

### 3.2 `ownership_precondition.sh` — four distinct refusal triggers

The header names **four** triggers plus one deliberate non-trigger. Each has
its own factor product:

| Trigger | Refuse when | Independent factors |
|---|---|---|
| **R1** probe failure | any declared location probes not-`ok` | scope parse × per-path probe (all 7 factors of §3.1) × entry count |
| **R2** *(non-trigger)* P1 unavailable | **SKIP**, deliberately not a refusal | runtime present × probe reachable — refusing here would be a §11.4.201(1) false positive on every host with no runtime |
| **R3** PUID=0 on rootful | measured-rootful **AND** some service declares `PUID=0` | (a) `detect_rootless` verdict **and** (b) compose parse finding `PUID=0` |
| **R4** non-root `user:` on rootless | measured-rootless **AND** service declares non-root `user:` **AND** that service mounts a declared location | **three** terms — a two-term check would refuse healthy configurations |

**The reviewer must independently verify each term of R3 and R4.** R4 in
particular is a three-way product; verifying two and assuming the third is
precisely the §11.4.194(1) failure mode. The source states R4 exists because
*"neither this check nor the FR-011 pre-build gate read the compose `user:`
key"* — so this term has no second line of defence.

### 3.3 `detect_rootless()` — the tri-state that gates R3 and R4

Returns `rootless | rootful | unknown:<reason>`. Factors:

1. Which runtime binary is in use (`podman` vs `docker` — different probes).
2. Whether the runtime's rootless field parses to a recognised value.
3. **The `unknown:` branch.** Both R3 and R4 consume this verdict. The header
   documents the asymmetry explicitly: reading silence as `rootful` refuses
   healthy hosts; reading it as `rootless` waves through the case the check
   exists to catch. **The reviewer must confirm what `unknown:` actually does
   at each of the two consumption sites, and that both do the same thing** —
   the source warns that "the two checks must never refuse on different facts."
4. A **carrier trap the source already documents**: a profile *path* containing
   the word `rootless` must not match the `name=rootless` marker
   (§11.4.201(7)(a) substring-vs-structure). Confirm the guard, and confirm a
   golden-FALSE fixture exercises it.
5. **Honest gap named in the source itself:** the docker branch "is written
   from Docker's documented rootless [behaviour]" — i.e. it is **not measured**.
   Per §11.4.6 that is an untested term, and it is a term in both R3 and R4.

### 3.4 `ownership_scope_fingerprint()` — the marker-invalidation product

Guards the repair completion marker: if the fingerprint does not change when
scope changes, a newly-declared path is **never repaired** while the marker
says "already done." Factors:

1. Scope parse success (a refusal must emit **nothing**, not a plausible hash).
2. Entry set contents.
3. **Empty-entry branch** — `paths: []` returns rc 0 with zero rows; the source
   documents that command substitution strips trailing newlines, so a naive
   re-add would hash `"\n"` instead of `""` and produce a *different*
   fingerprint for that shape.
4. Whether a marker already exists on disk written by the **old** code path.

The source claims byte-identity with the pipe it replaces, verified against the
live scope (`c41619d2…`). **That claim is a change made in this branch and is
the reviewer's to re-verify**, because it is precisely the "green because the
value looks plausible" shape: an empty pipe previously emitted
`e3b0c442…` (sha256 of the empty string) on stdout while returning non-zero.

### 3.5 `ownership_path_fence()` / `ownership_fence_runtime_trees()`

Refuses recursive chown inside container-runtime storage (subuid-owned by
design; a recursive change there breaks the rootless runtime per §11.4.161).
Factors: path normalisation × symlink resolution × runtime-storage root
detection × the fail-closed default on an unresolvable root. The source records
a live near-miss: with an empty runtime root the fence "refused on its
fail-closed [path]" and read the root as `absent` — **both** misdiagnoses that
FR-010a exists to prevent. Confirm the current default and its golden-FALSE.

### 3.6 Non-ownership executables — dimensions to enumerate

- **`deduplicator.py`** (+417/−199): input dimensions = tracker count ×
  result-set size × duplicate topology (identical / near / none) × unicode
  normalisation × event-loop blocking (there is a dedicated
  `test_dedup_event_loop_blocking.py`). The −199 means **behaviour was removed**;
  §11.4.124 requires investigate-before-remove evidence for each removal.
- **`rate_limit.py` + `test_rate_limit_download_proxy.py` (+673)**: dimensions =
  limit class × burst shape × concurrent callers × response contract (a
  dedicated `test_bob129_slowapi_response_contract.py` exists). §11.4.253
  idempotency-under-retry applies.
- **`hooks.py`** (+257/−29): two new tests name **persistence failure**
  (`test_bob173_hook_persistence_failure.py`) and **corrupt store**
  (`test_bob174_corrupt_hook_store.py`, +854). This is a §11.4.239
  critical-invariant **integrity** surface; failure-path scenarios are required
  as gates, not optional.
- **`rutracker.py` + `test_rutracker_redos_bounds.py`**: ReDoS bounds —
  dimensions = pattern × adversarial input length × timeout budget.
- **`start.sh`** (+348): the reload-level matrix (`--reload-python` /
  `--reload-plugins` / `--recreate`) × runtime detection × ownership-precondition
  exit code (1 = refuse, 2 = cannot-run — **these must not be conflated**).

---

## 4. Cross-cutting risk register

Pairs where two work-streams touch one file, or where one change's assumption
is another change's output.

| # | Shared surface | Touched by | Risk |
|---|---|---|---|
| **X-1** | `scripts/pre_build_verification.sh` | **12 commits**; all 8 new gates register here | Single dispatch seam for 51 invariants. A registration merged correctly in isolation can still be mis-ordered or shadowed here. This file has no harness (F-4). |
| **X-2** | `docs/workable_items.db` | **37 commits**, binary, tracked (§11.4.95) | Binary ⇒ **no merge resolution possible**. Prior session memory records a shared-checkout race on exactly this file. Any concurrent write is last-writer-wins with no conflict signal. |
| **X-3** | `docs/Issues.md` (37) / `Issues_Summary` (34) / `Issues.html` (34) / `.pdf` (33) | many | Counts diverge (37 / 34 / 34 / 33) ⇒ the `.md` moved without its exports in ≥3 commits. §11.4.106 docs-chain question, not a code question. |
| **X-4** | `specs/002-user-owned-downloads/tasks.md` | 12 commits, **and modified in the worktree right now** | The task ledger driving this very review is itself in flux. |
| **X-5** | `config/owned_paths.yaml` → 3 consumers | precondition (FR-010), repair (FR-004), gate (FR-011) | One data pack, three readers with **different** correctness requirements. A scope entry valid for the gate may be un-probeable by the precondition. Scope changes must invalidate the repair marker (§3.4) — that coupling is the fingerprint. |
| **X-6** | `detect_rootless()` verdict → R3 **and** R4 | one producer, two consumers | The source itself warns the two "must never refuse on different facts." Verify both consumption sites agree on `unknown:`. |
| **X-7** | `docker-compose.yml` (+56/−4) → `ownership_compose_rows()` | compose file is the parser's input | The parser reads `userns_mode`, `PUID`, `user:`, mount sources. A compose edit landing without a parser update (or vice versa) silently changes R3/R4 coverage. **Both changed in this branch.** |
| **X-8** | `scripts/systemd/user/boba-stack.service` + `boba.target` + `flight-recorder/install.sh` | new systemd units, new installer | The installer writes user units; the units are also tracked. Divergence between the two is undetectable at review time. |
| **X-9** | `docs/scripts/check_cm_lan_routes_authenticated.md` **tracked & modified** vs its script **untracked** | sibling work-stream | §11.4.215 inversion: the binding doc is in the repo, the code it binds is not. See §6. |
| **X-10** | `pyproject.toml` / `requirements.txt` / `package.json` / `package-lock.json` | 4 manifests changed | §11.4.246 supply-chain surface; `requirements.txt` alone is +114/−15 and is bucketed as "docs" by extension (§1.4). |

---

## 5. What a reviewer should NOT spend budget on

**Verified per file, not assumed by extension.**

### 5.1 Safe to skip — 267 orphan export twins

Measured: 324 changed export stems (`.html`/`.pdf`/`.docx`), 74 changed `.md`
stems. **271 export stems have no correspondingly-changed `.md`.** Of those,
**267 have an unchanged `.md` on disk** — i.e. the source did not change and
only the rendered twin did. That is mechanical re-render churn (roughly
**84,617 insertions**, 59% of the whole diff) and carries no reviewable logic.

Examples: `AGENTS.*`, `CONSTITUTION.*`, `CHANGELOG.*`, the entire
`docs/browser_extension/**` export tree, `docs/CODEGRAPH.*`.

> This churn is worth **one** note to the reviewer, not 267: 267 exports moved
> without their sources. That is a §11.4.106 docs-chain / §11.4.222 export-wave
> observation, not a code finding.

### 5.2 NOT safe to skip, despite the extension

- **`tests/ux/fixtures/{a11y,keyboard}_{good,bad}.html`** — the only 4 changed
  `.html` with **no `.md` source anywhere on disk**. They are hand-authored
  accessibility oracles. `a11y_bad.html` / `keyboard_bad.html` are the
  **golden-bad fixtures** (§11.4.107(10)); if they do not actually fail the
  analyzer, the whole UX suite is decoration.
- **`specs/002-user-owned-downloads/tasks.md`** — the task ledger. Load-bearing.
- **`specs/002-user-owned-downloads/{spec,plan,data-model,research}.md`** and
  `contracts/{repair-cli,startup-precondition}.md` — the acceptance criteria the
  executable surface is reviewed *against*. The two `contracts/` files are the
  CLI/precondition contracts and should be read **before** the scripts.
- **`specs/002-user-owned-downloads/checklists/requirements.md`** — the
  requirements checklist.
- **`specs/002-user-owned-downloads/progress.yml`** — bucketed `config`, but it
  is ledger state.
- **`download-proxy/requirements.txt`** — bucketed `governance+docs` by
  extension; actually a dependency manifest (§1.4, X-10).
- **`docs/guides/file-ownership.md`** (+214) — the operator-facing contract for
  the feature under review.

### 5.3 Skim only

`qa-evidence` (75 files, +13,664): captured `.log` / `.diff` / `.json`
artifacts. Read the ones an executable change **cites as its evidence**; do not
read the corpus. `docs/Issues.md` / `Fixed.md` (+1,678 combined) are tracker
state generated from the DB — audit them only for §11.4.146(D3) status-custody,
not line by line.

---

## 6. Honest gaps (§11.4.6)

### 6.1 The tree is NOT quiescent — measured, with timestamps

Observed **2026-08-26T19:01:06Z**. 31 tracked files modified in the working
tree, i.e. **already diverged from the `main...HEAD` diff measured above**:

**Uncommitted deltas on the executable/test surface (+1,650 insertions):**

| File | Uncommitted Δ |
|---|---:|
| `tests/unit/test_ownership_repair.sh` | **+710 / −7** |
| `challenges/scripts/ddos_resilience_challenge.sh` | **+498 / −44** |
| `scripts/lib/ownership.sh` | **+302 / −9** — *the feature-core library* |
| `scripts/pre_build/check_cm_export_charset_valid.sh` | +109 / −62 |
| `scripts/ownership_precondition.sh` | +29 / −6 |
| `specs/002-user-owned-downloads/tasks.md` | +2 / −2 |

Also modified: `constitution` (submodule), `docs/workable_items.db`, and 18
doc/export twins.

> **Consequence for T041:** a review of `git diff main...HEAD` right now reviews
> a `scripts/lib/ownership.sh` that is **302 lines behind** the working tree.
> Per §11.4.115(F) / §11.4.236 the review verdict must name the exact tree state
> it read (HEAD `a3e1141` + whether the worktree delta was included), or the
> verdict's fingerprint does not match anything that will ship.

### 6.2 Files under active sibling-agent edit — observed times

`find -mmin -30` at **2026-08-26T19:01Z** (relative `-newermt` is unusable on
this host's `bfs` `find`):

| File | Status |
|---|---|
| `constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh` | modified <30 min ago |
| `constitution/scripts/gates/cm_dangerous_combination_fail_closed_mutation_test.sh` | modified <30 min ago |
| `specs/002-user-owned-downloads/tasks.md` | modified <30 min ago |
| `config/merge-service/scheduling.json` | modified <30 min ago |
| `config/qBittorrent/qBittorrent-data.conf` | modified <30 min ago |
| `config/boba.db-shm` | modified <30 min ago |

**Nothing in this document reports the content of those files as settled.**

### 6.3 The sibling LAN-route work is NOT in this diff at all

Measured, not inferred:

| Path | In `main...HEAD` | Tracked |
|---|:--:|:--:|
| `scripts/pre_build/lan_route_auth_analyzer.py` | **0** | **0 (untracked)** |
| `scripts/pre_build/check_cm_lan_routes_authenticated.sh` | **0** | **0 (untracked)** |
| `config/lan_route_auth_policy.yaml` | 0 | 0 (untracked) |
| `scripts/pre_build/lib/` (3 files) | 0 | 0 (untracked) |
| `docs/scripts/check_cm_lan_routes_authenticated.md` | **YES** | **YES, and modified now** |

**A T041 review scoped to `git diff main...HEAD` reviews NONE of the LAN-route
code, while its companion doc IS in scope.** That is the §11.4.215 inversion
(X-9): a binding doc tracked in the repo describing code that exists in no
commit. Either the review scope or the commit state must be reconciled before
T041 can claim completeness.

24 untracked files total. `git status --porcelain` showed only 20 `??` entries
because it collapses directories; expanded: `docs/qa/BOB-186|191|196|198` and
`docs/qa/T028-uid100999` = 1 file each, `scripts/pre_build/lib/` = 3 files.

### 6.4 The constitution submodule hides the largest change in the branch

```
constitution: f6cf86e -> 7a5e53a   (one line in the parent diff)
```

Measured inside the submodule:

- **11 commits**
- **164 files changed, +20,292 / −3,826**

**A reviewer reading only `git diff main...HEAD` sees ONE line where 20,292
insertions of governance content actually landed.** Per §11.4.233(G) I checked
the pointer's health, and it is good:

- **Resolvable:** `git cat-file -t 7a5e53a` → `commit` ✔
- **Checked out:** submodule HEAD == the recorded pointer ✔
- **Fetchable:** contained by `origin/main`, `github/main`, `gitlab/main`,
  `gitflic/main`, `gitverse/main` (all 5 remote-tracking refs) ✔ — so this is
  **not** the `not our ref` class.

But the submodule worktree is itself **dirty** (§6.2), so its content is moving.

### 6.5 What this preflight did NOT determine

1. **Whether any mutation harness actually kills its gate.** Harnesses were
   located and their vocabulary counted; **none were executed**. "MUT = YES"
   in §2 means *a paired harness exists*, **not** *a fixture dies under it*.
   That is F-5 and is the reviewer's to establish.
2. **Whether the golden fixtures are independent oracles** (§11.4.245) —
   specifically `bob145_dedup_golden.json` (3,475 lines) and the four
   `tests/ux/fixtures/*.html`.
3. **Filesystem-semantics coverage** (§3.1 factor 6) — I did not determine
   whether any test exercises a uid-flattening filesystem.
4. **Whether `detect_rootless`'s `unknown:` branch is handled identically at
   its two consumption sites** (§3.3 / X-6) — read the headers, did not trace
   both call sites.
5. **The docker rootless branch is documented-not-measured by the source's own
   admission** — I confirmed the admission, not the behaviour.
6. **`pre_build_verification.sh` was deliberately not executed** (~26 s
   fork-heavy long-op owned by the conductor), so no gate verdict here is
   runtime-confirmed. Every claim in this document is source/metadata class
   (§11.4.226) and none is offered as runtime evidence.
7. **Bucket boundary cases** — `.scss` was classified `executable-source`
   (shipped code, not prose); a reviewer preferring a separate "style" bucket
   would move 8 files / 79 insertions.

---

## 7. Recommended review order

1. `specs/…/contracts/*.md` + `spec.md` + `data-model.md` — the acceptance
   criteria (≈600 lines) **before** any code.
2. **Tier 1 ownership core** — 4,086 lines, against §3.1–§3.5 factor tables.
3. **X-6 / X-7** — the `detect_rootless` → R3/R4 coupling and the
   compose-parser ↔ `docker-compose.yml` pair.
4. **F-5** — open the 3 lowest-vocabulary harnesses and confirm they kill.
5. **X-1 / F-4** — `pre_build_verification.sh` dispatch (the unaudited gate).
6. Tier 3 runtime code, `deduplicator.py` first (largest rewrite, −199).
7. Tier 4 scripts, prioritising the 6 with neither doc nor test (F-6).
8. **Skip** the 267 orphan exports (§5.1); note the churn once.
