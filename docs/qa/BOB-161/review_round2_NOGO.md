# BOB-161 CM-NO-FAIL-OPEN-SKIP — §11.4.209 independent review, round 2

**Verdict: NO-GO** — 0 BLOCKING / **1 IMPORTANT / 1 MINOR** (round 1 was 5 / 7).
Substrate: Fable. Reviewer distinct from round 1's. 2026-08-25. Loop re-arms (§11.4.134).

## Every round-1 finding verified fixed BY EXECUTION, not by reading claims

Suite 31/31 with 9 mutations · `bash -n` + `shellcheck -x` clean · all three round-1 killers
re-run in a scratch mirror and now caught (SESSION_HINTS → 29/2, subscript arm → 29/2,
tuple-flag → 29/2) · `RESPONSE_DERIVERS` gone from code · live corpus unchanged at exactly 6,
same files same lines · all three author-self-reported suite defects genuinely fixed, including
the chmod-000 file now persisting into the mutation section so `unreadable_blind` bites ·
ratchet honest (synthetic 7th → exit 1; no self-write path; the new warning lives only in the
PASS-below-baseline branch) · wiring proven wiring-only by mechanical diff partition, charset
baseline 301 untouched · companion doc accurate rather than aspirational, twins real.

**The `.status` narrowing is load-bearing, not decorative** — the reviewer rebuilt the pre-fix
syntactic version: it produces 2 false positives on the domain-status shape where the current
gate passes, and both report the identical 6 on the real corpus. FP surface removed at zero
detection cost.

## IMPORTANT-A — the `with ... as` sub-rule carries a real finding and has zero coverage

`check_cm_no_fail_open_skip.sh:425-427` (the `ast.withitem` clause in `response_names`). No
fixture anywhere uses `urlopen` or `with … as`. Mutation `elif False and isinstance(n,
ast.withitem):` leaves the suite **31/31 GREEN** while real detection drops **6 → 5** — the
vanished finding is `tests/integration/test_tracker_auth_live.py:108`, whose taint seeds
exclusively through `with urllib.request.urlopen(req, timeout=1) as resp:`. The gate header
(line 55) and the doc's R2 row both advertise that form.

**It defeats the defense added for its own predecessor.** An author drops the withitem clause,
runs the suite (green), sees 5 against baseline 6, obeys the new warning verbatim — "FIRST run
the mutation suite and confirm every mutation still bites", and all 9 do — then lowers BASELINE
to 5. A genuine fail-open and a detection rule are both gone with every defense reporting clean.
§11.4.115(F): a sub-rule never observed to fail on its broken form is unvalidated
instrumentation. Round 1 rated this identical shape (SESSION_HINTS, 6→4) IMPORTANT.

## MINOR-B — the alias `as` arm is half-unvalidated

HONEST LIMITS (129-130), the `skip_aliases` docstring (250) and the doc all claim
`from pytest import skip [as x]` is tracked. The code genuinely handles it — the reviewer
confirmed the gate flags a `skip as s` fail-open — but the ALIAS fixture (suite line 399) uses
only the plain form, and mutation `out.add(a.asname or a.name)` → `out.add(a.name)` survives
31/31. Round 1's MINOR-4 class exactly.

## Correction to the conductor's own round-1 brief

The six findings live under `tests/integration/`, not `tests/unit/` as the dispatch brief said.
The gate header had it right; the brief did not.

## Could not analyse (stated, never assumed safe)

The 6 baseline findings' own remediation (needs the live stack; tracked as BOB-192) · the ~170
dirty `docs/**` html/pdf — BOB-169 regen fallout, out of scope, confirmed only that the charset
baseline was not lowered · root-privileged runs, where a chmod-000 fixture cannot be unreadable
(the suite would fail loudly on a grep mismatch, never pass silently) · the declared honest
limits (helper-returned bools, fixture-boundary dataflow, non-Python harnesses).
