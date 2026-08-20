# BOB-076 closure evidence

**Item:** BOB-076 (RD2-09) — submodules/jackett fork 1 commit behind upstream (informational)
**Type:** Task · **Closed as:** Completed (→ Fixed.md) per §11.4.33
**Closed:** 2026-08-20

## Why this was still Queued

The substantive work was ALREADY DONE and the tracker row was never reconciled — the same drift
class as BOB-117, found in the same §11.4.238 sweep.

    $ git log -1 --format='%h %ad %s' --date=short 99a486e
    99a486e 2026-08-15 chore(jackett,BOB-076): bump submodules/jackett v0.24.2353 -> v0.24.2406

That commit's own message states: "closes BOB-076 (RD2-09 submodule 1-commit-behind was
informational; now 6-releases-ahead)". The pin it set — 09ecfadea — is the SHA checked out today.

## Current drift is inert (measured, not assumed)

    $ git submodule status -- submodules/jackett
     09ecfadea8c4755afe852f78b2de7b7be5ebb1e4 submodules/jackett (v0.24.2406)
    $ git rev-list --count 09ecfadea..origin/master
    25
    $ git merge-base --is-ancestor 09ecfadea origin/master && echo YES
    YES

The 25 new commits are third-party indexer-definition churn (24 files: tracker .yml definitions,
one indexer's own captcha-login support, one updater housekeeping edit). No core-engine, WebUI-auth
or security-boundary code.

## Zero runtime linkage — checked, not assumed

    docker-compose.yml:  jackett uses image lscr.io/linuxserver/jackett:latest, AUTO_UPDATE=true
    scripts/deploy-remote.sh:37   --exclude='submodules/jackett'
    scripts/codegraph_validate.sh:110  third-party EXCLUDED (§11.4.79)

The live :9117 service runs the prebuilt LinuxServer image and self-updates. `submodules/jackett`
is a vendored reference checkout that is never built, never copied into a container, and is
excluded from deployment and CodeGraph indexing. Bumping or not bumping changes nothing at runtime.

## Decision

NO further pin change. Advancing it today would be tidiness, not a justified fix (§11.4.124
investigate-before-change). The item is closed because its stated concern was resolved by 99a486e;
the residual drift is routine third-party content with no relevance to this repo.

## Honest boundary (§11.4.6)

This closes the TRACKER ROW to match reality. It does not assert the vendored checkout is current —
it is deliberately 25 commits behind, and that is recorded here rather than hidden.
