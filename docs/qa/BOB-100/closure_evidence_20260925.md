# BOB-100 — Bump submodules/jackett — Closure Evidence

**Date:** 2026-09-25
**Status:** Fixed (→ Fixed.md)

## Context

BOB-100 (backfilled from GOVERNANCE_AUDIT_2026-08-08_ROUND2.md RD2-39) asked to
bump `submodules/jackett` "one commit" to track upstream `Jackett/Jackett`.
That framing was already stale by the time this closure ran: the pin had
drifted to **165 tagged releases** behind upstream `main`, not one commit.

This closure was triggered by the operator's separate mid-session mandate
("make sure our projects uses and targets the latest Jackett version and
that is fully and properly incorporated") — a dedicated subagent
(`docs/qa/BOB-JACKETT-LATEST/investigation_20260925.md`) verified the
*running* `lscr.io/linuxserver/jackett:latest` container and the Go API
client have no hardcoded version dependency and needed no code change. That
investigation did not touch `submodules/jackett` (a separate,
build-disconnected reference submodule) — this closure covers that gap.

## Verification that the submodule is build-disconnected (safe to bump)

```
$ grep -rln "submodules/jackett" --include="*.yml" --include="Dockerfile*" --include="*.sh" .
scripts/codegraph_validate.sh
scripts/deploy-remote.sh
tests/pre_build/test_check_gitignore_swallow.sh
```

- `scripts/codegraph_validate.sh` only asserts the submodule's paths are
  EXCLUDED from the CodeGraph index (§11.4.79 third-party exclusion) — no
  dependency on submodule content or commit.
- `scripts/deploy-remote.sh` only `--exclude`s the path from an rsync.
- `tests/pre_build/test_check_gitignore_swallow.sh` uses the path string as
  a synthetic fixture directory name — unrelated to the real submodule.
- No `docker-compose.yml` service, Dockerfile, or build script references
  `submodules/jackett` (confirmed via the same grep). The real Jackett
  container comes from `lscr.io/linuxserver/jackett:latest` (auto-updating,
  see BOB-JACKETT-LATEST investigation) — `submodules/jackett` is a pure
  reference/upstream-tracking checkout, not a build input.

## Fix applied

```
$ cd submodules/jackett && git fetch --all --tags --prune
 * [new tag]             v0.24.2631         -> v0.24.2631
 * [new tag]             v0.24.2644         -> v0.24.2644
 * [new tag]             v0.24.2651         -> v0.24.2651
 * [new tag]             v0.24.2663         -> v0.24.2663
 * [new tag]             v0.24.2668         -> v0.24.2668

$ git describe --tags   # before
v0.24.2503-1-g8529ce4f2

$ git checkout v0.24.2668
HEAD is now at cf228beea Revert "crabpt: drop redundant default: true from cats"

$ git describe --tags   # after
v0.24.2668
$ git log -1 --format='%H %s'
cf228beea7574389da01d7b6a00805e6a9ec77ea Revert "crabpt: drop redundant default: true from cats"
```

Pointer bumped from `8529ce4f2` (v0.24.2503) to `cf228beea` (v0.24.2668) —
matches the same absolute-latest release the BOB-JACKETT-LATEST
investigation identified via live GitHub release data (§11.4.99).

## No hardcoded commit-hash dependents

```
$ grep -n "8529ce4f2\|submodules/jackett" scripts/codegraph_validate.sh \
    scripts/deploy-remote.sh tests/pre_build/test_check_gitignore_swallow.sh
```
Zero references to the old commit hash `8529ce4f2` anywhere in the
repository — only path-string references, confirmed above.

## Classification

Project-specific (§11.4.17) — a submodule-pointer bump; no universal
constitution change.
