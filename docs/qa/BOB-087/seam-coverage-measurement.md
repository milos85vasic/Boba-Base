# BOB-087 — §11.4.106(F) three-seam coverage measurement

**Item:** BOB-087 (RD2-20) — Wire docs_chain / commit-seam sync hook per §11.4.106(F)
**Type:** Task · **Status after this measurement:** In progress (2 of 3 seams covered)
**Measured:** 2026-08-21

## What §11.4.106(F) requires

> "the doc/DB sync is enforced at the COMMIT seam (hook refuses a commit whose staged
>  set touches a chain source while its exports/DB are stale) + the BUILD seam
>  (pre-build gate) + the CONSTITUTION-PULL seam (§11.4.164 post-update hook)"

Three seams. Each was measured separately.

---

## SEAM 1 — COMMIT: **COVERED** (measured, both polarities)

`scripts/hooks/docs-sync-commit-seam.sh` exists (368 lines) and is invoked from
`scripts/commit-push-all.sh` at **both** commit call sites — the `--scope` branch
(line 378) and the `git add -A` branch (line 386) — through `_docs_sync_seam_check`
(line 275), which runs *after* staging and *before* `git commit`, and `exit 1`s the
whole wrapper on refusal. There is no third path to `git commit` in that script.

Live run over the tracker file set:

    $ bash scripts/hooks/docs-sync-commit-seam.sh --files docs/Issues.md docs/Fixed.md docs/workable_items.db
    CHECK 1 workable-items validate ......... PASS
    CHECK 2 workable-items diff ............. PASS
    CHECK 3 body_md drift oracle ............ PASS

### The item's literal claim, tested in both directions

The acceptance text is *"a docs/workable_items.db write can never again land without its
MD mirror in the same commit"*. A one-directional oracle would satisfy the words and miss
half the defect, so both directions were driven. Everything ran on temp copies; the real
`docs/workable_items.db` sha256 was unchanged before and after (`28e12f219590e667`).

**MD drifts, DB stale** — the hook's own §11.4.107(10) self-test:

    golden-good     PASS  (clean tree reproduces tracked DB; oracle does not false-fire)
    golden-bad      PASS  (seeded body drift DETECTED and named: BOB-008)

**DB written, MD stale** — the direction the item actually names. A *real engine* write
(`workable-items update --id BOB-084 -status "In progress"`) was applied to a temp copy of
the DB with the working-tree Markdown deliberately left alone:

    negative control   PASS  (no DB write -> oracle silent; no false positive §11.4.201(1))
    golden-bad         PASS  (DB-only write DETECTED and named: BOB-084)

So the seam refuses a DB write whose MD mirror is absent, and does not refuse a clean tree.
It has also refused live commits in anger today on checks 1, 2, 3 and 5 (operator-reported).

---

## SEAM 2 — BUILD: **COVERED** (with one named residual)

`scripts/pre_build_verification.sh` invariant 17 (`CM-WORKABLE-ITEMS-VALIDATE`) runs
**both** halves, and passes the Markdown paths explicitly — not the flagless form:

    workable-items validate --db "${WORKABLE_DB}"
    workable-items diff --db "${WORKABLE_DB}" --issues "${ISSUES_MD}" --fixed "${FIXED_MD}"

Invariant 18 / 22 cover `workable-items-export.sh` (the .md→exports leg, including a
real-invocation assertion so a silently-skipping export cannot pass), and invariant 24
(`CM-DOCS-CHAIN-ENGINE-VERIFY`) runs the real Docs Chain engine `verify --all` against
`.docs_chain/contexts/*`.

**Residual (named, not silently absorbed):** the build seam has no equivalent of the
commit seam's CHECK 3. `diff` is structurally blind to body-only drift — that blindness
is BOB-136, and it is exactly how BOB-008's Evidence text rotted unnoticed. The build seam
therefore enforces doc/DB sync but cannot see the body_md class. This is a *narrower*
instrument at that seam, not an absent one.

---

## SEAM 3 — CONSTITUTION-PULL: **NOT COVERED** (measured absence, control-needled)

Neither hook that runs on a constitution pull performs any doc/DB sync check.

    $ grep -cE "workable-items|docs-sync|docs_chain|11\.4\.106" constitution/scripts/post_update_hook.sh
    0
    $ grep -cE "workable-items|docs-sync|docs_chain|11\.4\.106" scripts/verify-all-constitution-rules.sh
    0

A zero is not evidence until the instrument is proven able to see through the same path
(§11.4.201(7)(b)). Control needles, same grep, same files:

    post_update_hook.sh            "skill"                        -> 38   (sees)
    post_update_hook.sh            "ZZZ_NOT_PRESENT_NEEDLE"       ->  0   (negative control)
    verify-all-constitution-rules  "covenant_propagation_suite"   ->  7   (sees)

The instrument sees. The zeros are real.

Nor does the sweep pick a sync check up transitively: of the 172 gates under
`constitution/scripts/gates/`, only two mention the workable-items or docs_chain engines
(`cm_covenant_114_202_propagation.sh`, `cm_covenant_114_213_propagation.sh`) and both are
*anchor-literal presence* gates — they assert a governance file contains a string, and
perform no DB↔Markdown comparison. `config/constitution-sweep.conf` adds no such check
either.

**Consequence:** a constitution pull that lands a doc-affecting change can be treated as
canonical with the tracker's DB and Markdown never re-compared. §11.4.32 names
`scripts/verify-all-constitution-rules.sh` as boba's sweep, so that is where the missing
check belongs.

---

## Remaining work (precise)

1. Add a doc/DB sync stage to `scripts/verify-all-constitution-rules.sh` that invokes the
   already-existing seam by reference — `bash scripts/hooks/docs-sync-commit-seam.sh
   --files docs/Issues.md docs/Fixed.md docs/workable_items.db` — reporting PASS /
   FAIL / SKIP-with-reason in the sweep's existing verdict vocabulary, never a silent pass
   on an absent tool (§11.4.3 / §11.4.201). No new gate logic: the seam already exists and
   is self-validated, so this is a wiring change, not a second implementation (§11.4.227).
2. Optional, tracked separately as the BOB-136 class: give the build seam the CHECK 3
   body_md oracle so `diff`'s blindness is not the build seam's blindness.

Not done in this round: both files are outside the declared file scope of the working
brief (`scripts/pre_build_verification.sh` is explicitly forbidden;
`scripts/verify-all-constitution-rules.sh` is not in the granted scope). Naming the gap
and leaving the item open is the honest outcome rather than exceeding scope (§11.4.6).

## Honest boundary (§11.4.6)

The commit seam proves the tracked DB and the working-tree Markdown agree at commit time.
It does not prove either side is *correct*, and it only fires when the staged set touches
a chain source — a pure-code commit stages none, which is why CHECK 5 (BOB-136 closure
seam) deliberately runs before the early exit.
