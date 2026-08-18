# Batch fix verdict — 457cca4..a7e55f9 review: 2 NIT + MINOR-6

**Revision:** 1
**Last modified:** 2026-08-18T00:00:00Z

Source: `.superpowers/sdd/task-review-457cca4-a7e55f9-report.md`. This batch's
declared scope: `challenges/scripts/resource_pressure_signature_challenge.sh`
(if NITs land there — they do not), `scripts/install-dev-tools.sh` (MINOR-6),
and this evidence directory. Explicitly out of this batch's scope:
`docs/CONTINUATION.md`, `docs/incidents/`, `docs/QA_DISCOVERY_LEDGER.md`, and
any other subagent's in-flight scope.

## NIT-1 — QA_DISCOVERY_LEDGER.md re-wording — SKIP (out of scope by task design)

**Finding:** re-word the ledger's `new-check:` line from "§11.4.115 polarity
verified" to "§11.4.115 polarity per-signature captured — see
docs/qa/BOB-076/polarity/" citing per-detector artefacts, **in the same
fix-forward round that closes IMPORTANT-1**.

**Verdict: honest SKIP.** Two independent reasons, either alone sufficient:

1. The finding's own fix instruction ties it explicitly to the IMPORTANT-1
   remediation round (the per-signature polarity fixtures IMPORTANT-1
   requires do not exist yet in this checkout as of this batch — creating
   them is IMPORTANT-1's job, not this batch's). Re-wording the ledger
   line now, before those fixtures land, would either (a) cite artefacts
   that do not yet exist (a fresh §11.4.6 bluff replacing the old one), or
   (b) require this batch to silently absorb IMPORTANT-1's scope, which
   was not assigned here.
2. `docs/QA_DISCOVERY_LEDGER.md` is explicitly listed in this batch's
   "Do NOT touch" constraint. Editing it would violate the assigned scope
   regardless of (1).

**Recommendation:** the subagent/round that closes IMPORTANT-1 should apply
this exact re-wording as its own final step, citing the per-detector
artefact paths it just created — this NIT is trivially closed as a
byproduct of that round and should not be tracked as a separate item.

## NIT-2 — BOB-068 label-collision reconciliation ticket — SKIP (scope + concurrency risk)

**Finding:** the incident doc
`docs/incidents/2026-08-18-auto-committer-BOB-068-investigation.md` is
honest as written (§11.4.6 clean per the reviewer) — no doc edit needed.
The action item is to surface the doc's own §8 open item ("reconcile
BOB-068 label collision") as a tracked workable item via
`TASK :: reconcile BOB-068 label collision …` (§11.4.140/§11.4.202) so the
§11.4.197 tracker owns follow-through, not the incident doc.

**Verdict: honest SKIP, deliberately not actioned in this batch.** Filing a
workable item through the `TASK ::` directive mutates the shared SSoT
(`docs/workable_items.db`) and regenerates `Issues.md` /
`Issues_Summary.md` / `Fixed.md` / their exports — every one of those files
is OUTSIDE this batch's declared `--scope`
(`challenges/scripts/resource_pressure_signature_challenge.sh`,
`scripts/install-dev-tools.sh`,
`docs/qa/task-review-457cca4-a7e55f9-nit-fixes/`).

Doing it anyway would be the exact class of risk **IMPORTANT-2 in this
same review** flags: a shared-checkout, shared-SSoT mutation landing inside
a narrowly-scoped batch commit, un-isolated from whatever concurrent
subagent work is touching `docs/workable_items.db` this session (per
`docs/incidents/.../BOB-068-investigation.md` §4.3-4.5's independently
confirmed shared-checkout race). Filing this ticket from inside a batch
explicitly forbidden from touching `docs/incidents/` and scoped to two
unrelated scripts would itself be a scope-boundary violation, not a fix.

**Recommendation:** the conductor/orchestrator runs
`TASK :: reconcile BOB-068 label collision — <link to the incident doc §8>`
as its own isolated, correctly-scoped action (its own `--scope` covering
`docs/workable_items.db` + the regenerated doc set), never bundled into an
unrelated batch.

## MINOR-6 — `install-dev-tools.sh` bash>=4.0 gap — FIXED

**Finding:** `declare -A RESULT` requires bash >= 4.0; macOS ships bash 3.2
by default; no early version check existed, producing a cryptic
`declare: -A: invalid option` on stock macOS instead of an actionable
error.

**Verdict: FIXED.** Per the suggested portable-pattern fix (not the
"document Linux-only" alternative, since the script already supports macOS
throughout via its Homebrew install paths — declaring it Linux-only would
be a regression, not a fix):

1. Header comment gained a "Runtime requirement — bash >= 4.0 (§11.4.35
   consumer-DATA declaration)" paragraph naming the cause, the macOS
   failure mode, and the exact remediation.
2. A guard immediately after `set -uo pipefail` checks the real
   `BASH_VERSINFO[0]` (never OS-family-inferred — a Homebrew/upgraded bash
   on macOS is a legitimate PASS, per §11.4.201 guard-asserts-real-condition)
   and exits 2 with an actionable message naming the exact fix
   (`brew install bash` + explicit re-invocation path) before any other
   script logic runs.

**Evidence:** `docs/qa/task-review-457cca4-a7e55f9-nit-fixes/minor-6-bash-version-guard.md`
— golden-good (real bash 5.2 host, `--check` unaffected, exit 0) +
golden-bad (isolated probe proving the exact numeric-comparison +
exit-2 + actionable-message logic trips on a bash-3-shaped version array).
Honest boundary: no real macOS/bash-3.2 host was available in this session
to independently verify the shipped guard end-to-end — the header comment
states this limitation explicitly; the probe verifies the logic pattern,
not the exact shipped invocation.

**Verification:** `bash -n scripts/install-dev-tools.sh` clean before and
after the edit.

## Summary

| Finding | Verdict | Reason |
|---|---|---|
| NIT-1 | SKIP | Fix target (`docs/QA_DISCOVERY_LEDGER.md`) is out-of-scope for this batch by task design AND is IMPORTANT-1's own remediation-round responsibility |
| NIT-2 | SKIP | Fix action mutates shared SSoT files outside this batch's declared `--scope`; doing it here would repeat the exact concurrent-shared-checkout risk IMPORTANT-2 flags |
| MINOR-6 | FIXED | `bash >= 4.0` guard added with header documentation, verified golden-good + golden-bad |
