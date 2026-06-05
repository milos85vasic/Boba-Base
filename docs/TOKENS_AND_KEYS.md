# Tokens, API Keys & Environment Variables

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

Single source of truth for every credential, token, and API key the
platform consumes. **Mandatory** rows fail the service at boot if
unset; **Optional** rows gate specific features and degrade silently.

Every value is read from either:

1. `./.env` (gitignored — project-local)
2. `~/.qbit.env` (user-level fallback)
3. Shell environment (highest priority)
4. `docker-compose.yml` defaults (lowest)

Loading order is defined in `.specify/memory/constitution.md` §III.

---

## 1. qBittorrent WebUI (built in)

| Variable | Default | Required | Where to get it |
|---|---|---|---|
| `WEBUI_USERNAME` | `admin` | No | Hardcoded default per [constitution III](../.specify/memory/constitution.md). |
| `WEBUI_PASSWORD` | `admin` | No | Same. Change in qBittorrent WebUI → Options → Web UI. |

**Portal:** [http://localhost:7186/](http://localhost:7186/)
**Change password:** qBittorrent WebUI → Options → Web UI → Authentication → Password.

---

## 2. Private tracker credentials

Each of these unlocks exactly one tracker in the merge search. None of
them are mandatory — the service simply skips the tracker if the
variable is unset.

### 2.1 RuTracker (`rutracker`)

| Variable | Required | Notes |
|---|---|---|
| `RUTRACKER_USERNAME` | **Mandatory for RuTracker** | Forum username. |
| `RUTRACKER_PASSWORD` | **Mandatory for RuTracker** | Account password. |

**Register:** [https://rutracker.org/forum/register.php](https://rutracker.org/forum/register.php)
**CAPTCHA refresh:** `GET /api/v1/auth/rutracker/captcha` (the dashboard surfaces this from the tracker chip — see [`SECURITY.md`](SECURITY.md)).

### 2.2 Kinozal (`kinozal`)

| Variable | Required | Fallback |
|---|---|---|
| `KINOZAL_USERNAME` | **Mandatory for Kinozal** | Falls back to `IPTORRENTS_USERNAME` if unset (shared-account rigs). |
| `KINOZAL_PASSWORD` | **Mandatory for Kinozal** | Falls back to `IPTORRENTS_PASSWORD`. |

**Register:** [https://kinozal.tv/signup.php](https://kinozal.tv/signup.php) (may require invite).

### 2.3 NNM-Club (`nnmclub`)

| Variable | Required | Notes |
|---|---|---|
| `NNMCLUB_COOKIES` | **Mandatory for NNM-Club** | Full `phpbb2mysql_*` cookie string; copy from browser devtools after login. |

**Register:** [https://nnmclub.to/forum/ucp.php?mode=register](https://nnmclub.to/forum/ucp.php?mode=register)
**How to extract cookies:** sign in → DevTools → Application → Cookies → copy all `phpbb2mysql_*` entries into one `name=value; name2=value2` string.

### 2.4 IPTorrents (`iptorrents`)

| Variable | Required | Notes |
|---|---|---|
| `IPTORRENTS_USERNAME` | **Mandatory for IPTorrents** | Ratio-sensitive — see [constitution VIII](../.specify/memory/constitution.md). |
| `IPTORRENTS_PASSWORD` | **Mandatory for IPTorrents** | |

**Register:** [https://iptorrents.com/](https://iptorrents.com/) (invite-only; apply via [iptorrents.ooooo.io](https://iptorrents.ooooo.io/) or similar).
**Freeleech safety net:** automated downloads are restricted to `&free=on` results by the platform (constitution VIII).

---

## 3. Public tracker API keys (optional)

The 40+ public-tracker engines ship without authentication. A handful
can use an API key for rate-limit uplift:

| Variable | Used by | Required | Register |
|---|---|---|---|
| `JACKETT_API_KEY` | `plugins/jackett.py` | **Auto-discovered** — `start.sh` extracts it from Jackett's config automatically. Manual override optional. | [https://github.com/Jackett/Jackett#installation](https://github.com/Jackett/Jackett#installation) → Admin → Jackett API Key |
| `JACKETT_URL` | `plugins/jackett.py` | Optional (default `http://localhost:9117`) | Your Jackett host |
| `TORRENTSCSV_API_KEY` | `plugins/torrentscsv.py` | Optional | [https://torrents-csv.com/](https://torrents-csv.com/) (no auth typically) |

---

## 4. Metadata enrichment APIs (optional)

The merge service decorates results with poster/year/genre when these
keys are present. Unset = no enrichment, service runs normally.

| Variable | Required | Register | Purpose |
|---|---|---|---|
| `TMDB_API_KEY` | Optional | [https://www.themoviedb.org/signup](https://www.themoviedb.org/signup) → Settings → API → Request API Key (v3 auth) | Movie / TV posters + metadata |
| `TVDB_API_KEY` | Optional | [https://thetvdb.com/api-information](https://thetvdb.com/api-information) → Subscribe | TV series metadata |
| `MUSICBRAINZ_USER_AGENT` | Optional (default `qbittorrent-fixed/0.1 (milos85vasic@)`) | [https://musicbrainz.org/doc/MusicBrainz_API](https://musicbrainz.org/doc/MusicBrainz_API) — free, requires UA only | Music album lookup |
| `ANIDB_CLIENT` | Optional | [https://anidb.net/software/add](https://anidb.net/software/add) (register a client) | Anime metadata |
| `OPENLIBRARY_USER_AGENT` | Optional | [https://openlibrary.org/dev/docs/api/](https://openlibrary.org/dev/docs/api/) — free, UA only | eBook / audiobook metadata |

---

## 5. Security scanner tokens (opt-in CI / local scans)

`./scripts/scan.sh` skips scanners whose tokens are missing. None of
these are mandatory for the platform to function.

| Variable | Required | Register |
|---|---|---|
| `SNYK_TOKEN` | Optional | [https://app.snyk.io/](https://app.snyk.io/) → Account Settings → Auth Token |
| `SONAR_TOKEN` | Optional | [https://sonarcloud.io/account/security/](https://sonarcloud.io/account/security/) or your SonarQube instance |
| `SONAR_HOST_URL` | Optional | Default `http://localhost:9000` (the compose profile runs SonarQube there) |
| `GITLEAKS_LICENSE` | Optional | [https://gitleaks.io/](https://gitleaks.io/) for commercial use; the OSS scan runs without it |

---

## 6. Observability endpoints (opt-in compose profile)

Start with `$COMPOSE_CMD -f docker-compose.yml -f docker-compose.quality.yml --profile observability up -d`.

| Variable | Default | Required |
|---|---|---|
| `GRAFANA_USER` | `admin` | Optional |
| `GRAFANA_PASSWORD` | `admin` | Optional (change for anything beyond localhost) |
| `PROMETHEUS_PORT` | `9090` | Optional |
| `GRAFANA_PORT` | `3000` | Optional |

**Portals (after compose up):**
- Prometheus: [http://localhost:9090/](http://localhost:9090/)
- Grafana: [http://localhost:3000/](http://localhost:3000/)

---

## 7. Orchestrator tuning (optional — Phase 3)

All have safe defaults; tune for your workload.

| Variable | Default | Purpose |
|---|---|---|
| `ALLOWED_ORIGINS` | `*` (with startup warning) | CORS whitelist. Comma-separated. **Set this in production** to avoid the wildcard warning. |
| `MAX_CONCURRENT_TRACKERS` | `5` | Semaphore cap on tracker fan-out. |
| `MAX_ACTIVE_SEARCHES` | `256` | TTLCache maxsize for in-flight searches. |
| `ACTIVE_SEARCH_TTL_SECONDS` | `3600` | Per-search metadata retention. |
| `PENDING_CAPTCHAS_MAX` | `1024` | CAPTCHA session TTLCache maxsize. |
| `PENDING_CAPTCHAS_TTL_SECONDS` | `900` | CAPTCHA session lifetime. |
| `HOOK_LOG_MAXLEN` | `500` | Deque cap for hook-execution logs. |
| `MERGE_SERVICE_HOST` | `0.0.0.0` | Bind interface for the merge service. |
| `MERGE_SERVICE_PORT` | `7187` | HTTP port. |
| `MERGE_SERVICE_URL` | `http://localhost:7187` | Where the download-proxy (and the injected theme bridge) find the merge service. Embedded verbatim into `/__qbit_theme__/bootstrap.js`. |
| `PROXY_PORT` | `7186` | Download proxy port. |
| `BRIDGE_PORT` | `7188` | WebUI bridge port. |
| `THEME_STATE_PATH` | `/config/merge-service/theme.json` | JSON file the merge service uses to persist the active palette + mode (see `docs/CROSS_APP_THEME_PLAN.md`). |
| `DISABLE_THEME_INJECTION` | *(unset)* | Escape hatch for the cross-app theme bridge. Set to `1` to make the download proxy stop injecting `/__qbit_theme__/*` into qBittorrent's HTML responses and stop rewriting CSP. Useful if a qBittorrent upgrade ever breaks the bridge and you need to fall back to the untouched WebUI. |

---

## 8. Data directory

| Variable | Default | Required | Notes |
|---|---|---|---|
| `QBITTORRENT_DATA_DIR` | `/mnt/DATA` | No | Where qBittorrent stores torrents + incomplete + finished subdirs. Must be writable by `PUID`/`PGID`. |
| `PUID` | `1000` | No | Container user ID. |
| `PGID` | `1000` | No | Container group ID. |

---

## Quick-start matrix

Minimum-viable `.env` for *public-tracker-only* deployment:

```bash
# No credentials required — service runs out of the box.
QBITTORRENT_DATA_DIR=/mnt/DATA
```

Minimum-viable `.env` for *private-tracker* deployment:

```bash
# Pick the trackers you have accounts on.
RUTRACKER_USERNAME=your-user
RUTRACKER_PASSWORD=your-password

KINOZAL_USERNAME=your-user
KINOZAL_PASSWORD=your-password

NNMCLUB_COOKIES="phpbb2mysql_data=...; phpbb2mysql_sid=..."

IPTORRENTS_USERNAME=your-user
IPTORRENTS_PASSWORD=your-password

QBITTORRENT_DATA_DIR=/mnt/DATA
```

Minimum-viable `.env` for *CI / scanner uplift*:

```bash
SNYK_TOKEN=your-token
SONAR_TOKEN=your-token
SONAR_HOST_URL=https://sonarcloud.io
ALLOWED_ORIGINS=https://qbit.example.com
```

---

## Verification

After editing `.env`, restart the stack and probe auth:

```bash
./stop.sh && ./start.sh
curl -s http://localhost:7187/api/v1/auth/status | python3 -m json.tool
```

Every tracker with `has_session: true` is live; anything with
`has_session: false` either has wrong credentials or the tracker's
login flow changed. For rutracker + iptorrents you can then trigger
CAPTCHA refresh from the dashboard chip.

---

## Related

- [`SECURITY.md`](SECURITY.md) — threat model and credential storage.
- [`SCANNING.md`](SCANNING.md) — scanner config that uses §5 tokens.
- [`OBSERVABILITY.md`](OBSERVABILITY.md) — §6 endpoints.
- [`USER_MANUAL.md`](USER_MANUAL.md) — walk-through per tracker.
- [`.specify/memory/constitution.md`](../.specify/memory/constitution.md) — legal binding of the above.
