# DEAD_PUBLIC_TRACKERS recovery re-check — 2026-06-16

**Revision:** 1
**Last modified:** 2026-06-16T00:00:00Z

Read-only HTTP probe of all 14 `DEAD_PUBLIC_TRACKERS`
(`download-proxy/src/merge_service/search.py:482`) with the plugin Firefox UA,
sequential + gentle, following redirects, grepping bodies for real listing markup
vs Cloudflare/JS gates. §11.4.118 discovery; §11.4.6 honest (a live 200 proves
reachability, NOT that the plugin parser still extracts fields).

**Counts: RECOVERED 4 · GATED 5 · STILL-DEAD 5.**

## RECOVERED — candidates to re-enable (real torrent markup, no gate)

| tracker | URL | evidence |
|---|---|---|
| audiobookbay | http://theaudiobookbay.se/ | 200, real `/abss/...` rows (audiobook-only niche, live) |
| bitru | https://bitru.org | 200, real `details.php?id=...` rows |
| therarbg | https://therarbg.com | 200, real `/post-detail/<id>/...` rows (~139 KB result page) |
| solidtorrents | 301 → bitsearch.eu (via bitsearch.to) | rebrand serves 40 real `magnet:` links/search — needs base-URL update + parser rewrite (different site) |

## GATED — Cloudflare/JS, unusable from a urllib plugin (§11.4.112, keep disabled)

bt4g (403 "Just a moment…"), btsow (200 "Loading…" JS shell), extratorrent (403 CF),
eztv (root 200 at eztvx.to but search path 403 CF), one337x (403 CF).

## STILL-DEAD

ali213 (200 but Chinese single-game portal, no torrent rows), pctorrent (DNS fail),
torrentfunk (timeout), xfsub (timeout), yihua (DNS fail).

## Re-enabling path (§11.4.122 — OPERATOR-REVIEWED, not done here)

Re-enabling any tracker is a separate operator-reviewed change. A live 200 proves
reachability only — each RECOVERED candidate's plugin parser MUST be re-validated
against current live markup first (solidtorrents→bitsearch is the clearest case
where the domain works but the parser needs a rewrite). Recommended per-candidate:
operator selects → TDD (RED scraping the live site → fix parser → GREEN) → drop from
`DEAD_PUBLIC_TRACKERS` in the same reviewed commit. NOT performed autonomously.

_Captured 2026-06-16 against the live tracker domains._
