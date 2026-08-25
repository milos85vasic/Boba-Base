# T018 — Independent review of `docker-compose.yml` scope: **GO**

**Revision:** 1
**Last modified:** 2026-08-23T00:00:00Z

Supersedes `T018-review-NOGO.md` (round 1) and `T018-round3-remediation.md`.
Four review rounds on the §11.4.209 substrate, iterated to a zero-finding /
zero-warning GO per §11.4.134.

## Verdict

**GO on T018** — every finding from the original NO-GO and from rounds 3 and 4
is closed with evidence the reviewer generated itself.

## The substantive T018 question, answered

On the current `docker-compose.yml`, no service that mounts an in-scope path is
configured in a way that defeats operator-owned writes:

| Assertion | Measured |
|---|---|
| `userns_mode` active keys | **0** |
| `user:` keys | **0** |
| `PUID=0`/`PGID=0` preserved on the two linuxserver services | yes (deliberate, per CLAUDE.md) |
| credential store mode | **600** |
| world-writable under `config/` | **0** |
| group-writable under `config/` | **0** |

## Findings closed across rounds

| Finding | Round | Closure |
|---|---|---|
| IMPORTANT-3 | 3 | closed |
| MINOR-4 (special-bit / non-owner assert) | 3 | rewritten to mask `8#77` + `8#6000`, remediation path printed |
| MINOR-5 + NIT-2 | 3 | header block rewritten to state WHAT HOLDS vs WHAT DOES NOT |
| MINOR-6 (label/comment mismatch) | 4 | closed on a two-form instrument; see below |
| MINOR-7 (count reported as path coverage) | 4 | wiring guard now resolves the `--recreate` dispatch region and asserts per-path, not per-count |
| NIT-3 (surviving absolutes) | 4 | one hit remains and it is a *negated quotation* inside `WHAT DOES NOT HOLD` — the correction, not a survivor |

## MINOR-6 — the reviewer's own instrument was the defect

The round-3 audit reported *"denominators: all 50, single value"*. That
instrument matched only `^echo "\[N/M\]"` — **41 of 50 labels.** The nine
`run_const_gate "N/M"` sites were invisible to it.

Checked against git: at HEAD all 50 labels read `/49`; in the working tree the
bracket labels had been renumbered to `/50` while the nine `run_const_gate`
sites still read `/49`. **Two denominators were live and the audit reported
one.** This is §11.4.201(6) — a partially blind scan returning the same quiet,
clean answer a healthy file returns — inside the reviewer's own instrument.

Re-derived with a two-form instrument, control-needle proven against a
known-present `run_const_gate` line:

```
TOTAL labels: 50   (comment-paired: 41, matched: 41, MISMATCHED: 0)
strictly increasing across ALL forms: YES
distinct denominators: 50(x50)   duplicate numerators: 0   gaps in 1..50: 0
```

Line 1507's `Invariant 40` pairs with `run_const_gate "40/50"` — the earlier
revert is correct. A bracket-only scan would have skipped that label and paired
the comment with the next *bracket* label instead, which is the exact mechanism
by which the mismatch hid.

## Resolver hardening — four hazards, all land safe

| Hazard | Result |
|---|---|
| H1 dispatch condition reworded (`bash -n` OK) | BLIND branch **reachable, not dead** — FAILs naming the unresolved region |
| H2 dispatch nested one level deeper (`bash -n` OK) | adapts — region re-resolved, both paths still found |
| H3 premature `fi` at same indent (`bash -n` OK) | truncates → **FAIL**, and semantically accurate: after a premature `fi` those calls really are unconditional |
| H5 one-sided deletion (default-path `harden` removed) | **FAIL** naming `harden` on the DEFAULT path; `assert` still correctly passes both |

The expected false-pass case (`_in`=1 / `_out`=1 from an H3 split plus a
one-sided deletion) is **not constructible**: closing the `if` early makes every
trailing call unconditional, so any split producing `_in≥1 ∧ _out≥1` describes a
script that genuinely is wired on both paths. Mis-resolution can only shrink or
grow the region, and both directions drive a count to zero and FAIL.

**Observation, not a finding:** the resolver is anchored on the exact condition
text, so a benign rewording converts the wiring check into a loud FAIL on a
healthy script. That is the safe direction and the message is self-describing,
but it is a real maintenance coupling; the looser-pattern alternative trades that
safety for robustness.

## Ordering question — judged, and deliberately NOT asserted

Recreate path: `… → stack_up → harden → assert`.
Default path: `harden (create_directories) → … → start_container → … → assert`.

The difference is **heal-vs-refuse, not security**: on `--recreate` a container
that widens the store during boot gets corrected then confirmed; on the default
path harden has already run, so `assert` refuses instead of healing. Both are
fail-closed — neither can report a successful start over a widened store.

An order assertion was considered and **rejected**. The property worth asserting
is "assert runs after the last thing that can widen the store", but that last
thing includes container runtime behaviour, which is not a static property of
`start.sh`. A static order check would assert a proxy for a runtime condition —
§11.4.201(7), the shape this feature has already been bitten by twice.

## Scope of this GO — what it does NOT discharge

- **T042** remains owed: the full 50-invariant gate, on a genuinely quiescent tree.
- **§11.4.185 manual-QA** remains the terminal human gate.
- No live `./start.sh` / `--recreate` run (four sibling streams live) — static verification only.
- Container-internal runtime behaviour unobserved; mitigated by the post-up assert on both paths, not proven.
- Docker-rootless detection branch unexercised — no rootful docker on this host; the code declares that gap itself.

## Residue

0 probe-shaped lines in the working diff, 0 staged, 0 new root-level files.
Every probe ran in a mirrored scratch tree deleted in the same command window,
each with its fixture verified before the mutation was trusted.
