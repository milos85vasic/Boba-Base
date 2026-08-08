# Boba — Multi-Track Development Registration

**Revision:** 1
**Last modified:** 2026-08-08T17:10:00Z
**Status:** active

## Decision (operator mandate, 2026-08-08)

Boba permanently adopts the constitution's multi-track development discipline
(§11.4.58 parallel work-unit pipeline, §11.4.176 work-division, §11.4.178
track-qualified identity, §11.4.182 work-stream labels, §11.4.187 automatic
ruler orchestration, §11.4.192 continuous auto-backfill) as its **standing
working mode going forward** — not a one-off exercise.

**This checkout (`/run/media/milosvasic/DATA4TB/Projects/boba`, host `nezha`)
is permanently registered as the home of Track 11** in the operator's
multi-track fleet, chosen to avoid colliding with track numbers already in
use by other projects/hosts (`/mnt/track1..4` are occupied elsewhere).

**Execution scope right now (operator instruction, 2026-08-08): single-track
only.** No parallel background ruler/subagent streams have been spawned for
this project yet. The identity/labeling convention below is adopted
immediately and permanently; actual parallel dispatch is deferred until the
operator asks for it.

## Label convention

Every work-stream label for boba follows §11.4.182's
`(T<N>/<branch> - <alias> - <model> - <effort>)` form, derived via
`scripts/multitrack/track_branch_label.sh` (a thin, boba-owned wrapper —
never a copy — around the canonical, fleet-wide
`constitution/scripts/multitrack/track_branch_label.sh`, per §11.4.28(B)/
§11.4.177 decoupling: shared engines are wrapped, never edited in place).

- **Trunk (`main`/`master`) work is ALWAYS `T1`** — the canonical script's
  hard-coded TRUNK RULE (§11.4.182 amendment, 2026-07-28) is intentionally
  **never overridden**. This is deliberate: the rule exists so trunk work is
  never mistaken for "an unknown track" across the operator's whole fleet,
  and weakening it here would misrepresent trunk work as a numbered track it
  isn't.
- **Non-trunk work (`feat/`/`product/`/`flavor/` branches per §11.4.195)
  dispatched from this checkout is `T11`.** The canonical script has no way
  to know that a checkout outside `/mnt/track<N>` should map to track 11 —
  it honestly emits `T?` there — so the wrapper's only job is filling that
  specific `?` in with `11`, and only on non-trunk branches.

Verified 2026-08-08 (real invocation, on `main`):
```
$ bash scripts/multitrack/track_branch_label.sh
(T1/main - milos85vasic - ? - xhigh)
```
(`?` for `<model>` is the labeler's own honest fallback for this
native-alias's session-transcript lookup shape — not a bug in this wrapper.)

## Cross-references

- `scripts/multitrack/track_branch_label.sh` — the boba-owned wrapper.
- `constitution/scripts/multitrack/track_branch_label.sh` — the canonical,
  inherited-by-reference engine this wrapper delegates to.
- `docs/CONTINUATION.md` — session handoff, references this decision.
- `CLAUDE.md` — Critical Constraints section carries a one-line pointer here.
