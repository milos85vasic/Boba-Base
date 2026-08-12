# Session Resumption — 2026-08-12 tmux Restart Verification

**Revision:** 1
**Last modified:** 2026-08-12T22:55:00Z
**Status:** live handoff — pick up here after fresh tmux + fresh Claude Code

## What just happened

Operator asked: "restart tmux and verify"

Claude executed `tmx kill-server` from INSIDE the previous
`tmx-boba-6117.scope`. That killed every tmx server (including the one
hosting the previous Claude Code process) — so the previous conversation
ended abruptly at that moment BY DESIGN. This file exists so the fresh
session can pick up cleanly.

## Everything that shipped before the restart (verified GREEN)

**vasic-digital/tmux** (github + gitlab, ff-only):
- `6f9eaeb` `release(tmux v1.0.41)`: TMX-083 systemd-oomd victim-avoidance
- `92ef3a0` `merge`: integrate remote v1.0.41 + renumber TMX-083 to v1.0.42
- `b29b9e1` `fix(tmx.safe)`: parity — same ManagedOOMPreference=avoid on the fallback wrapper

**HelixDevelopment/qa** (origin):
- `50f9ccf` `feat(banks)`: boba-tmux-session-hardening — 5 test cases / 12 steps
- Merged origin/main (HXC-239/243/267/270/278) → `4fbf29c`

**milos85vasic/Boba-Base** (github + origin + upstream, ff-only):
- `bdb2490` `feat(qa)`: §11.4.238 coverage-escape audit + first challenge
- `058ecda` `chore(submodule)`: bump helixqa pointer + wire the symlink
- `276a055` `feat(challenge)`: oomctl witness + opt-in bounded chaos
- `08e870e` `feat(scripts)`: §11.4.234 commit-push-all.sh

## Verify the restart worked (run these AFTER reopening the fresh session)

```bash
# 1. confirm we are inside a v1.0.42 scope with the fix applied
scope=$(cat /proc/self/cgroup | awk -F/ '/tmx-/ {print $NF; exit}')
echo "my scope: $scope"
systemctl --user show "$scope" -p ManagedOOMPreference --value
# EXPECT: avoid

# 2. run the full challenge suite
cd /run/media/milosvasic/DATA4TB/Projects/boba
bash challenges/scripts/tmux_survives_oomd_pressure_challenge.sh
# EXPECT: Total: PASS=4 FAIL=0

# 3. optional chaos — bounded memory spike, verifies tmux survives real pressure
TMUX_OOMD_STRESS=1 bash challenges/scripts/tmux_survives_oomd_pressure_challenge.sh
# EXPECT: Total: PASS=5 FAIL=0 (all pre-stress tmx-*.scope units survived intact)
```

## Verify by reading — how you know THIS session is the post-restart one

- `tmx-boba-6117.scope` was the OLD session (its scope + pid `6117` are gone)
- A fresh `tmx new -s boba` will spawn `tmx-boba-<newpid>.scope` — different PID
- The new scope carries `ManagedOOMPreference=avoid` from birth (no post-hoc hardening needed)

## If anything looks wrong

- The `MEM_LIMIT=infinity` / `TasksMax=infinity` v1.0.39 fixes are still in place too — those are orthogonal to this one, both must hold.
- If `ManagedOOMPreference` reads `none` on a fresh scope, the wrapper on your PATH is not the v1.0.42 one — check `type tmx` and `head -50 $(type -p tmx) | grep ManagedOOM`.
- If oomctl reports `user-1000.slice` NOT monitored, systemd-oomd was stopped/masked — restart it with `sudo systemctl start systemd-oomd`.

## Task tracker state before the restart

All 9 tasks completed. See the previous conversation transcript if
Claude Code preserves it via `--resume <session-id>`.
