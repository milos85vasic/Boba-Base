# BOB-165 closure evidence — 2026-09-23

## Fix (the item's own acceptance criterion's second, documentation-only
branch — "OR CLAUDE.md is corrected to document the supported runner
explicitly")

`CLAUDE.md` already correctly documents `.venv/bin/python -m pytest ...`.
`AGENTS.md` (which §11.4.157 requires stay in lockstep with `CLAUDE.md`) had
drifted: its "Single test / subset" section still documented the BROKEN
`python3 -m pytest ...` form. Corrected `AGENTS.md`'s three example commands
to `.venv/bin/python -m pytest`, matching `CLAUDE.md`, with an in-source
comment explaining why (this also restores §11.4.157 lockstep, a second
defect the drift itself constituted).

## Independently verified this session

```
$ python3 -m pytest tests/unit/test_freeleech.py -v --import-mode=importlib
/usr/bin/python3: No module named pytest
```
(System python3 on THIS host doesn't even have pytest installed — an even
harder failure than the item's originally-measured stale-ABI-rpds
ModuleNotFoundError, but the same conclusion: the documented `python3 -m
pytest` command cannot reach collection.)

```
$ .venv/bin/python -m pytest tests/unit/test_freeleech.py -v --import-mode=importlib
...
13 passed in 1.39s
```
(The corrected, now-consistently-documented command works.)

```
$ grep -n "python3 -m pytest" AGENTS.md
271:# system python3 -m pytest cannot even reach collection. .venv/bin/python is
```
Only remaining occurrence is inside the explanatory comment itself — no live
command in AGENTS.md still documents the broken form.

## Honest boundary (not silenced, per the item's own framing)

This does NOT touch the host's `~/.local/lib/python3/site-packages/rpds/`
install (a system-level, out-of-repo mutation this session deliberately did
not perform) nor the separate BOB-154 venv-rebuild-to-3.12 item. Both remain
open, unrelated follow-ups. This closure satisfies BOB-165's acceptance
criterion via its explicitly-permitted second branch: the documented command
and the working command now agree.

## git diff --stat

```
AGENTS.md | 8 +++++++-
1 file changed, 7 insertions(+), 1 deletion(-)
```
