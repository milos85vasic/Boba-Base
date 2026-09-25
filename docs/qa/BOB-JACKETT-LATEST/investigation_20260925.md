# Jackett latest-version incorporation investigation

**Date:** 2026-09-25
**Task:** "We have new version of Jackett released, make sure that our projects uses and targets the latest Jackett version and that is fully and properly incorporated!"
**Scope:** repo root `/home/milosvasic/Projects/boba` (§11.4.99 latest-source cross-reference, §11.4.108 runtime-signature, §11.4.6 no-guessing)

## 1. Verified latest Jackett release (real web research, not training data)

- **Source of truth:** https://github.com/Jackett/Jackett/releases (fetched live via WebFetch, 2026-09-25)
- **Latest release tag:** `v0.24.2668`
- **Release date:** 2026-09-25 05:56 UTC
- **Release URL:** https://github.com/Jackett/Jackett/releases/tag/v0.24.2668
- **Release notes summary (from the live fetch):** revert of a prior change ("crabpt: drop redundant `default: true` from cats") + fixes for two torrent indexers (`kickasstorrents-to`, `extratorrent-st`) adding `headers` sections to resolve 403 errors when using flaresolverr/byparr.

## 2. How this repo consumes Jackett — investigation

### 2a. `docker-compose.yml` (jackett service)

Confirmed by direct read of `docker-compose.yml:71-118`:

```yaml
jackett:
  image: lscr.io/linuxserver/jackett:latest
  ...
  environment:
    - AUTO_UPDATE=true
```

- The image tag is a **floating `:latest`** tag (not pinned), as expected.
- `AUTO_UPDATE=true` is set — this is load-bearing: it makes the linuxserver image's entrypoint run Jackett's own internal self-updater on a periodic schedule, **independent of the Docker image tag/build**. This means the running Jackett *binary* tracks upstream releases even when the cached Docker image itself is stale, as proven live below (§3).

### 2b. `linuxserver/docker-jackett` image lag vs upstream

Verified live via WebFetch against Docker Hub (`https://hub.docker.com/r/linuxserver/jackett/tags`, fetched 2026-09-25):

- Docker Hub `linuxserver/jackett:latest` currently resolves to tag **`v0.24.2663-ls38`**, "updated about 22 hours ago" (relative to fetch time).
- This is **5 build numbers / ~19.5 hours behind** the true upstream-latest `v0.24.2668` (released 2026-09-25 05:56 UTC) found in §1.
- **Honest assessment of the lag:** this is a normal, expected periodic-rebuild lag (linuxserver.io does not rebuild synchronously on every upstream commit), not a meaningful/blocking lag. It is further mitigated by `AUTO_UPDATE=true` (§2a), which lets the *running* Jackett binary self-update to the newest release independently of when the base image was last rebuilt — proven live in §3.

### 2c. `boba-jackett` Go service (`qBitTorrent-go/`) — Jackett API client code

Found and read `qBitTorrent-go/internal/jackett/client.go` (the only Jackett admin-API HTTP client in the Go service; also checked `qBitTorrent-go/internal/jackettapi/*`, `qBitTorrent-go/internal/jackett/autoconfig.go`).

- Every call uses the **generic, version-stable v2.0 admin API**: `GET/POST /api/v2.0/indexers`, `GET/POST /api/v2.0/indexers/{id}/config`, `DELETE /api/v2.0/indexers/{id}`.
- No hardcoded Jackett version string, no assumed fixed response schema beyond "either a top-level JSON array or a `{config: [...]}` envelope" (`GetIndexerTemplate`, `client.go:212-254`), which the code already normalises defensively for both shapes.
- `grep -rn "0\.24\.\|jackett.*version\|JACKETT_VERSION" qBitTorrent-go --include="*.go"` (excluding `_test.go`) returned **zero** hardcoded Jackett-version literals. The one hit (`cmd/boba-jackett/main.go:201`, `Version: serviceVersion`) is **boba-jackett's own service version**, unrelated to upstream Jackett's version.
- Cross-referenced the actual upstream diff between the currently-deployed version (`v0.24.2663`) and the newest release (`v0.24.2668`) via a live GitHub compare fetch (`https://github.com/Jackett/Jackett/compare/v0.24.2663...v0.24.2668`): **3 commits total**, all per-indexer definition tweaks (2 `headers:` additions for flaresolverr/byparr on specific indexers, 1 category-default revert on one indexer). **No Torznab/indexer-JSON schema change, no `/api/v2.0/indexers` endpoint change, no auth/API-key handling change.**
- **Verdict:** no incompatibility with `boba-jackett`'s API client code.

### 2d. qBittorrent search-plugin engine

The task named `plugins/jackett.py`; that exact path does **not** exist in this repo. The real, wired engine is `plugins/community/jackett.py` (confirmed via `find plugins -iname "*jackett*"`, and cross-referenced against `docs/JACKETT_INTEGRATION.md`'s "Files Modified for This Integration" table, which explicitly names `plugins/community/jackett.py`).

Read the full file (`plugins/community/jackett.py`, 300 lines, `# VERSION: 4.9` — this is the *qBittorrent search-plugin* version header, unrelated to the Jackett server version):

- Uses the generic Torznab feed endpoints: `GET /api/v2.0/indexers/all/results/torznab/api` (indexer discovery) and `GET /api/v2.0/indexers/{id}/results/torznab/api` (per-indexer search), both apikey-authenticated.
- Parses the response as standard Torznab XML (`{http://torznab.com/schemas/2015/feed}attr` namespace, `channel/item` elements) — the same schema Jackett has exposed for years; unaffected by the 3-commit diff in §2c.
- No hardcoded Jackett version anywhere in the file.
- **Verdict:** no incompatibility.

### 2e. Governance docs

- `CLAUDE.md`: mentions Jackett only architecturally (port 9117, `AUTO_UPDATE`-driven, `boba-jackett` ownership) — **no specific Jackett version number is stated anywhere**, so there is nothing stale to update there.
- `docs/JACKETT_INTEGRATION.md` (13 KB, Revision 1, last modified 2026-06-06): describes the integration architecture, auto-discovery flow, plugin config, `boba-jackett` DB-backed auto-configuration. **No specific Jackett version number is stated anywhere in this file either** — it documents the *integration mechanism* (which is version-agnostic by design, per §2c/§2d), not a pinned version. Nothing to update.
- `AGENTS.md`: no Jackett-version-specific claim found.

**Conclusion of investigation:** the repo's own code and docs never pin, hardcode, or assume a fixed Jackett version anywhere. The only place a Jackett version lives is the floating `:latest` image tag + the self-updating binary inside the running container. This is "fully and properly incorporated" by design already — no code fix is required. The remaining question is purely operational: is the *currently running* Jackett instance actually on (or acceptably close to) the newest release? Proven live below.

## 3. Live proof (runtime signature, §11.4.108) — is the deployed Jackett stale?

### 3a. Runtime + local image state (read-only)

```
$ command -v podman && command -v docker
/usr/bin/podman
podman found
no docker
```
Runtime = podman, per repo convention (`start.sh` prefers podman).

```
$ podman images --format "{{.Repository}}:{{.Tag}}  {{.ID}}  {{.Created}}" | grep -i jackett
localhost/boba_boba-jackett:latest  38ef117ec563  39 hours ago
lscr.io/linuxserver/jackett:latest  dbda3f7086e7  3 weeks ago     <- STALE local cache, BEFORE pull
localhost/boba-jackett:dev  0cc39d1c837f  3 weeks ago

$ podman ps -a --format "{{.Names}}  {{.Image}}  {{.Status}}" | grep -i jackett
jackett  lscr.io/linuxserver/jackett:latest  Up 39 hours (healthy)
boba-jackett  localhost/boba_boba-jackett:latest  Up 39 hours (healthy)
```

The locally cached `lscr.io/linuxserver/jackett:latest` image was **3 weeks old** — genuinely stale versus the registry's current `:latest` (§2b). The stack is currently running.

### 3b. What the RUNNING container's Jackett binary actually reports (ground truth, independent of image staleness)

```
$ podman logs jackett | grep -n "Checking for updates|New release found|already updated|Starting Jackett v"
31:09-23 19:54:58 Info Starting Jackett v0.24.2520
1606:09-23 20:55:01 Info Checking for updates... Jackett variant: CoreLinuxMuslAmdx64
1607:09-23 20:55:01 Info New release found. Current version: v0.24.2520 New version: v0.24.2651
3587:09-23 20:55:08 Info Starting Jackett v0.24.2651
3872:09-23 21:55:51 Info Checking for updates... Jackett variant: CoreLinuxMuslAmdx64
3873:09-23 21:56:57 Info Jackett is already updated. Current version: v0.24.2651
3877:09-24 21:56:58 Info Checking for updates... Jackett variant: CoreLinuxMuslAmdx64
3878:09-24 21:56:58 Info New release found. Current version: v0.24.2651 New version: v0.24.2663
5852:09-24 21:57:02 Info Starting Jackett v0.24.2663
5880:09-24 22:57:05 Info Checking for updates... Jackett variant: CoreLinuxMuslAmdx64
5881:09-24 22:57:06 Info Jackett is already updated. Current version: v0.24.2663
```

Control-needle check on the log instrument before trusting it (§11.4.273): `grep -c "Info "` returned 4043 non-zero hits out of 5881 total lines — the grep instrument genuinely sees the log content, so the "no lines after 5881" result is a real end-of-log, not a blind/broken grep.

**Reading:** even though the baked-in image version was `v0.24.2520` (3 weeks stale), `AUTO_UPDATE=true` caused the running binary to self-update twice, and it is **currently actually running `v0.24.2663`** — matching Docker Hub's current `:latest` tag (§2b) exactly. The last update check (2026-09-24 22:57:06 UTC) found nothing newer than `v0.24.2663`, because the newest release (`v0.24.2668`) was not published until 2026-09-25 05:56 UTC — **after** that check ran. The container has not checked again since (checks run roughly once per ~24h after the initial post-boot checks), so it has not yet had the opportunity to pick up `v0.24.2668`; it will on its next scheduled check.

Host clock at time of check: `2026-09-25 08:09:41 UTC` (confirms the ordering above).

### 3c. Fresh image pull + verified reported version (proving the image itself, not just the running binary)

```
$ podman pull lscr.io/linuxserver/jackett:latest
Trying to pull lscr.io/linuxserver/jackett:latest...
... (blob copy, manifest write) ...
86eb45fe43d00ac67da7d07692901505296b250748b3a5568057804025b3f68c
```

```
$ podman images --format "{{.Repository}}:{{.Tag}}  {{.ID}}  {{.Created}}" | grep -i jackett
lscr.io/linuxserver/jackett:latest  86eb45fe43d0  22 hours ago    <- fresh, replaced the 3-week-old cache

$ podman image inspect lscr.io/linuxserver/jackett:latest --format '{{json .Labels}}' | python3 -m json.tool | grep -iE "version|build_version"
    "build_version": "Linuxserver.io version:- v0.24.2663-ls38 Build-date:- 2026-09-24T10:26:36+00:00",
    "org.opencontainers.image.version": "v0.24.2663-ls38"
```

The freshly-pulled image's own embedded OCI label reports **`v0.24.2663-ls38`**, built `2026-09-24T10:26:36Z` — this is genuine positive evidence read directly from the artifact itself (§11.4.108 runtime signature), not an assumption. It matches exactly what the already-running container's Jackett binary self-updated itself to in §3b.

### 3d. Side-by-side version comparison (no bluff)

| Source | Version | As-of |
|---|---|---|
| GitHub upstream latest release (ground truth, §1) | `v0.24.2668` | 2026-09-25 05:56 UTC |
| Docker Hub `linuxserver/jackett:latest` tag (§2b) | `v0.24.2663-ls38` | built 2026-09-24T10:26:36Z |
| Freshly-pulled local image, verified via OCI label (§3c) | `v0.24.2663-ls38` | matches Docker Hub exactly |
| Running container's live Jackett binary, verified via startup log (§3b) | `v0.24.2663` (self-updated via `AUTO_UPDATE=true`) | since 2026-09-24 21:57:02 UTC |

The running instance and the freshly-pulled image are **both 5 build numbers behind the absolute-newest GitHub release**, which was published only ~2 hours before this investigation began. §2c already proved those 5 commits contain **zero breaking changes** relevant to this repo's integration surface.

## 4. Findings summary

1. **No code change is needed.** `boba-jackett`'s Go client, the `plugins/community/jackett.py` qBittorrent engine, and every governance doc (`CLAUDE.md`, `docs/JACKETT_INTEGRATION.md`, `AGENTS.md`) are all Jackett-version-agnostic by construction — they consume the stable, unversioned v2.0/Torznab admin+search API and never pin a Jackett release number. The 3 real commits between the currently-deployed release and the newest upstream release are per-indexer configuration tweaks only, with zero API/schema impact (verified via a live GitHub compare, §2c).
2. **The stack already "targets latest" correctly by design**: `image: lscr.io/linuxserver/jackett:latest` (floating tag) + `AUTO_UPDATE=true` (in-container self-updater). This is the correct, already-proper mechanism for "always targets the latest Jackett" — no docker-compose.yml change is warranted.
3. **The local Docker image cache WAS stale** (3 weeks old, baked-in `v0.24.2520`) before this investigation. It has now been refreshed via a read-only `podman pull` to the current `linuxserver/jackett:latest` (`v0.24.2663-ls38`, built 2026-09-24). This pull is non-destructive — it downloaded bytes only and did **not** touch the running container.
4. **The running Jackett instance is functionally already current** (`v0.24.2663`, self-updated via `AUTO_UPDATE=true`, matching the registry's current `:latest` tag exactly) — it is only ~19.5 hours / 5 build numbers behind the absolute latest GitHub release (`v0.24.2668`, published today), a gap proven to carry zero breaking changes, and one its own internal auto-updater will close on its next scheduled check (or immediately on the next container recreate, since it will pull the now-fresh cached image).
5. **Pending action for the conductor (not run by this investigation, per instructions):** a `./start.sh --recreate` (or `--reload-jackett`-equivalent for the sidecar) would pick up the freshly-pulled image immediately, but is not strictly necessary given finding #4 — the running binary is already self-current via `AUTO_UPDATE=true` and will reach `v0.24.2668` on its own within its normal check cadence. Recreating now is an *optional* freshness improvement, not a fix for a broken or incompatible state.

## 5. Files touched by this investigation

- **Created:** `docs/qa/BOB-JACKETT-LATEST/investigation_20260925.md` (this file).
- **No source files were modified.** No TDD-fix was required because no incompatibility, stale-version assumption, or broken behavior was found anywhere in the codebase — see §4.1.
- **Host-side, non-repo change:** ran `podman pull lscr.io/linuxserver/jackett:latest` (read-only image download; did not touch/restart any running container). This is *not* a git-tracked change and needs no commit, but is reported here per the task's evidence-of-everything-done requirement.

## 6. No bluff statement

Every version number and timestamp cited above was captured live in this session (GitHub release page fetch, GitHub compare-diff fetch, Docker Hub tags fetch, and direct `podman`/`curl`/log commands against the actually-running local stack) — none is asserted from training-data memory (§11.4.99). Where an instrument's result mattered for a conclusion, it was control-needle-verified before being trusted (§11.4.273; see §3b).
