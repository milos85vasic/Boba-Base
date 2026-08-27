# Continue — Project Status Snapshot

**Revision:** 28
**Last modified:** 2026-08-27T04:05:00Z

## HOW TO RESUME THIS WORK

Point a fresh session at this file, then run the SpecKit execute command for
feature `002-user-owned-downloads`. Everything below is the live state at the
moment of this write; every number in it was measured, not remembered.

    /speckit-superspec-execute 002-user-owned-downloads

## ONE-PARAGRAPH STATE

Feature `002-user-owned-downloads` is at **40 of 42 tasks complete**. The two
open tasks are **T041** (final independent review of `git diff main...HEAD`) and
**T042** (run the full 52-invariant gate with no skip flag). Neither can close
yet: T042 will report **3 failures of 39** bash suites, all three of them
correctly-authored RED tests for open defects, and four independent review
chains are mid-iteration under §11.4.134 (iterate to zero findings AND zero
warnings). All work is committed and pushed; nothing is in flight in a
working tree.

## THE FOUR REVIEW CHAINS — exact round state

Each chain is a code artifact plus its own adversarial review loop. §11.4.134
requires iterating to a zero-finding, zero-warning GO. None has reached one.

| Chain | Artifact | Last completed | Verdict | Next action |
|---|---|---|---|---|
| BOB-102 | LAN-route auth gate | round 13 remediation | — | **round 14 review OWED** (killed by session limit) |
| BOB-195 | dangerous-combination gate | round 15 remediation | — | **round 16 review OWED** (killed by session limit) |
| BOB-221 | expected-RED mechanism | round 4 review | **NO-GO** 0B/1I/4M/3N | round 5 remediation |
| BOB-207 | ownership uid/gid primitive | evidence correction | 0 BLOCKING | short re-review |

### BOB-102 — LAN-route authentication gate
- **PASS=197 FAIL=0**, exit 0. Real tree: 74 routes / 3 services / 23 known-gaps,
  `--json` md5 `ecd4b31c2f40c87ed321a00c43cacb26`.
- Round 12 found the **real primitive had been misidentified for three rounds**:
  it is not "a selector can split at a dot" but *a construct whose ABSENCE
  disarms a refusal, rather than dropping a credit*. Silence is safe for a
  credit-carrier and unsafe for a refusal-armer. That sentence is now in-source.
- Round 13 fixed it at the class level and swept nine refusal-arming constructs
  across three axes, finding two more open doors (an aliased gin import, and all
  nine unmodelled-construct members) — both gofmt-stable.
- **Round 14 review never ran.** Its brief is reconstructable from this file plus
  the round-13 report; the highest-value task is verifying the "nine refusal-arming
  constructs" enumeration is complete, and adjudicating round 13's correction of
  round 12 (it says the `.Group(` "collateral" was not new to the poison).

### BOB-195 — dangerous-combination fail-closed gate
- **144 assertions, 0 failures, exit 0.** The gate script has been
  **byte-identical since round 11** (md5 `b90c5945d44b891c793c448e7165682c`) —
  every defect found in rounds 12-15 was under-pinning, never a live bug.
- Round 14 found the first door in the **primary AST analyzer** (all prior 13
  rounds were in the degraded text fallback): excluding `str` constants from the
  trivial-literal predicate makes `return "unknown"` and `return ""` pass clean.
  Root cause measured: `grep -c 'return "'` across the harness was **0**.
- Round 15 swept every AST predicate (22 mutations) and found **12 more doors**,
  worst being `suppress(builtins.Exception)` — the flagship violation with a
  qualified name — classified NARROW and dropped with no trace.
- **Round 16 review never ran.** Its first task is attacking three survivors
  round 15 classified as non-doors, and sweeping the two areas round 15 names as
  unswept: the bash driver and the non-Python scanners.

### BOB-221 — expected-RED declaration mechanism (blocks T042)
- Suite **19/19**, deterministic x3 (`80aecdb63bf348be`). Empty-table parity
  proven byte-identical against HEAD.
- Round 4 review verdict: **NO-GO, 0 BLOCKING / 1 IMPORTANT / 4 MINOR / 3 NIT.**
  No path yields HONOURED for an undeclared suite — that was hunted specifically
  and not found.
- **IMPORTANT-1**: the conflicting-markers refusal is unvalidated instrumentation.
  Deleting it survives 19/19 and fails OPEN — a suite carrying markers for two
  different items is honoured when the table id sorts first. Needs a P19 scenario.
- **MINOR-1**: boundary row 7 claims duplicated markers BLOCK; measurement shows
  two byte-identical markers are deduped by `sort -u` and **HONOURED**. Doc-vs-code
  drift on a documented refusal; also the candidate twentieth boundary row.
- MINOR-2 the status cache is dead code at its only call site (subshell); MINOR-3
  boundary 19 asserted by nothing; MINOR-4 the marker-MISMATCH reason is unpinned.

### BOB-207 — ownership uid/gid primitive (T042 blocker, CLOSED)
- **Closed and verified.** `test_ownership_gid_agreement.sh` 5/0/0,
  `test_ownership_repair.sh` 146/0/0, `test_check_cm_ownership_invariants.sh` 42/42.
- The fix is one line: the repair's walk now selects on uid alone, while the
  `chown` still writes `uid:gid`. Design artifacts settle the direction —
  `data-model.md` E4 models the probe with `probe_uid`/`expected_uid` and no gid
  field anywhere.
- The suite was re-based off a gid proxy onto a **real foreign uid** via
  `podman unshare chown 1:1` (host view `100000:100000`), correcting a header that
  claimed such a fixture was impossible unprivileged. All 23 fixtures re-based,
  none dropped.
- Review returned 0 BLOCKING; one evidence-accuracy correction was applied.

## T042 — WHY IT WILL FAIL, PRECISELY

Invariant 30 discovers 41 bash suites, excludes 2 self-recursive, runs **39**.
It will report **3 failures**, all intentional REDs for open defects:

    tests/unit/test_ownership_gid_agreement.sh        BOB-207  -> now rc=0, PASSES
    tests/pre_build/test_bob221_expected_red_declaration.sh  BOB-221  -> now rc=0
    tests/pre_build/test_bob205_danger_roots_scope.sh  BOB-205  -> still rc=1

Corrections to earlier analysis, measured: **there is no rc=124 and no rc=127.**
Two suites *do* hit rc=124, but the driver excludes them by basename before the
run loop, so T042 never sees them. Reading the raw glob instead of the loop is
what produced the phantom.

**Remaining T042 blockers:** BOB-205 (still RED), plus a non-quiescent tree at
gate time (invariant 30's no-trace half fails if exports move mid-run).

## FILED THIS SESSION

    BOB-226  Task  major     repair-side foreign-owned interior directories untested
    BOB-227  Bug   critical  LAN-route auth gate artifacts were UNTRACKED (closed by this commit)
    BOB-228  Task  minor     README does not link the gate guide (11.4.212 orphan)

Tracker verified in sync: 227 items, DB and Markdown agree, all invariants satisfied.

Not re-minted, correctly deduped: the directory-setgid finding is already
**BOB-220**; the orphan security test is already **BOB-212**.

## FOUR LESSONS THIS SESSION PAID FOR

1. **Carrier-vs-thing bit five times.** A count matched its own summary line
   (three separate chains); a test oracle matched the word `abort` in its own
   scenario *filename*; a residue scan flagged prose describing the finding.
   BOB-221 fixed the class rather than the instance: every reason alternative
   must now be multi-word and every scenario path space-free, so a filename
   carrier is impossible by construction rather than by luck.
2. **Evidence custody failed in three chains independently.** Rounds worked on
   uncommitted files with no snapshot, so round-over-round diff claims became
   permanently uncheckable. BOB-195 and BOB-102 now snapshot reviewed bytes to
   `docs/qa/<item>/round-N/` with a manifest before editing. **This commit makes
   those durable for the first time.**
3. **Baseline before discrepancy.** `git diff` against HEAD spans every round,
   not the one under review. Three times a wrong baseline nearly became a
   fabricated finding. Establish which baseline a number used before calling it
   a contradiction.
4. **The reviewer-authored mutation channel found the load-bearing defect in
   eight consecutive rounds.** A reviewer must write at least one mutation the
   author did not (11.4.194(6)(d)). An unmeasured redundancy dismissal should be
   inadmissible — round 8 of BOB-102 dismissed a live PASS-bluff by reading
   regexes without running one.

## OPERATIONAL HAZARDS OBSERVED

- **The agent scratchpad is shared.** One stream overwrote another's mutation
  helper mid-run, producing 8 false negatives while the anchor was present
  throughout. Namespace scratch artifacts per-agent and re-verify any surprising
  negative before reporting it.
- **Backgrounded runs killed by a tool ceiling never fire their EXIT trap** —
  32 GB of orphaned fixture dirs accumulated in `/tmp` before a sweep. An
  age-gated sweep-on-start is the compensation.
- **A `mode=ro` SQLite open LEAVES `-wal`/`-shm` sidecars behind; a read-write
  open removes them on clean close.** Sidecar presence therefore proves nothing
  about write access — the opposite of the intuitive reading.
