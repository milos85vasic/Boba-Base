# GamesTorrents silent-zero + slow-upstream investigation

**Revision:** 1
**Last modified:** 2026-06-16T00:00:00Z
**Status:** investigation complete — recommendations; clear bugs being fixed, tuning/removal deferred to operator (§11.4.122).

Real probes: merge service `nezha:7187` `/api/v1/search/sync` (user path) + direct
`curl` from nezha. §11.4.6 FACT-only; §11.4.123 captured proof. Container FACT:
`PUBLIC_TRACKER_DEADLINE_SECONDS=15` (code default 60, clamp 5–120).

## 1. gamestorrents — PARSE-FAIL (site alive, regex matches zero) → BUG, fixing

Scoped `GTA` → empty/0/no-error/~1.2s. Direct `?s=GTA` → HTTP 200, `<title>Has
buscado GTA`, real GTA V result (`gta-v.jpg`, `59.03 GB`). Root cause: the plugin
parse regex anchors on `<article>`+`<h2>`+`<div class=size/date>` — the current
site has **0 `<article>`, 0 `<h2>`**; results moved to `<table class="table
metalion">` rows (`<td><a href>NAME</a></td><td>DATE</td><td>SIZE</td>…`). **Action:
fix-regex (article-card → table.metalion). NOT niche, NOT dead.**

## 2. Slow upstreams

| Tracker | Live | Returns? | TTFB/total | Merge verdict | Recommended action |
|---|---|---|---|---|---|
| tokyotoshokan | unstable (200/500) | YES (7) | 12.8–14.6s | success ~14.6s (borderline) | raise deadline (~25–30s) — operator tuning call |
| yourbittorrent | **522 origin-down** | NO | ~19.8s, 522 | deadline_timeout/0 | mark-dead candidate (re-probe; §11.4.122 operator) |
| torlock | alive 200 | YES (100) | 0.65–12.5s | success 100 | leave / raise deadline |

**Cross-cutting:** `PUBLIC_TRACKER_DEADLINE_SECONDS=15` is the dominant cause of the
tokyotoshokan + torlock timeouts (both return real results just above/around 15s).
Raising to ~25–30s recovers both at a modest full-fleet-latency cost; it does NOT
help yourbittorrent (origin 522). The 15s value was set deliberately (latency
trade-off) — raising it is an **operator tuning decision**, documented here, not
changed autonomously. yourbittorrent removal is **operator-reviewed (§11.4.122)**.

_Captured 2026-06-16 against nezha + the live tracker domains._
