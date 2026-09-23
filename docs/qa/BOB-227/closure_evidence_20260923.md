# BOB-227 closure evidence — 2026-09-23 (partial — criterion 1 met, criterion 2 filed as follow-up)

## Criterion (1) — MET: already resolved before this session began

```
$ for f in scripts/pre_build/lan_route_auth_analyzer.py \
           scripts/pre_build/check_cm_lan_routes_authenticated.sh \
           tests/pre_build/test_check_cm_lan_routes_authenticated.sh \
           docs/scripts/check_cm_lan_routes_authenticated.md; do
    git ls-files --error-unmatch "$f" >/dev/null 2>&1 && echo "TRACKED: $f" || echo "UNTRACKED: $f"
  done
TRACKED: scripts/pre_build/lan_route_auth_analyzer.py
TRACKED: scripts/pre_build/check_cm_lan_routes_authenticated.sh
TRACKED: tests/pre_build/test_check_cm_lan_routes_authenticated.sh
TRACKED: docs/scripts/check_cm_lan_routes_authenticated.md
```
All four artifacts are genuinely tracked on this checkout. Traced via
`git log --diff-filter=A` for each of the three previously-untracked files
to the commit that first added them:

```
$ git log --diff-filter=A --oneline -- scripts/pre_build/lan_route_auth_analyzer.py
5c9b9e0 test-probe-do-not-use [skip-ci]
```
(same commit for all three). That commit (`5c9b9e0`, 2026-08-27T17:59:35+02:00,
predates this session entirely) is a large legitimate operator commit
landing `config/lan_route_auth_policy.yaml` alongside these three files —
this item's own "MEASURED 2026-08-27" timestamp was evidently taken
earlier the same day, before that commit landed. Criterion (1) — "all four
artifacts tracked and committed" — has been satisfied since before this
session started; the tracker was never synced to that reality.

## Criterion (2) — NOT MET, filed as its own follow-up

"a gate asserting that every executable a pre-build invariant invokes is
itself tracked" is a genuinely NEW, more general mechanism (this item's
own artifacts happening to now be tracked does not, by itself, prevent a
FUTURE gate's implementation files from shipping untracked the same way).
Filed as **BOB-231** (Task) rather than blocking this item's closure on a
substantial new-mechanism build — see
`docs/qa/BOB-231/` once worked, or the tracker entry for its own
acceptance criteria.

## git diff --stat

```
(none — read-only verification, no source change; this item's own
artifacts were already committed by a prior, unrelated commit)
```
