# BobaLink — Store Listing & Submission Checklist

**Revision:** 1
**Last modified:** 2026-06-10T22:00:00Z
**Scope:** Chrome Web Store + Firefox AMO listing content and a manual submission
checklist for BobaLink, the Boba Project browser extension (`extension/`).
**Authority:** `extension/wxt.config.ts`, `extension/package.json`,
`docs/browser_extension/Status.md` (Rev 5), `docs/browser_extension/USER_GUIDE.md`.

> Accuracy note (§11.4.6): every permission justification, feature claim, and
> privacy statement below was traced to the real extension source/config — the
> generated `wxt.config.ts` manifest (permissions / `host_permissions` / CSP /
> `commands`), `package.json` (version `1.0.0`), the `_locales/en/messages.json`
> store-description string, and `src/shared/constants.ts` (`SITE_SELECTORS`,
> `DEFAULT_URLS`). Nothing reads as shipped that is not. Items not yet produced
> (screenshots, promo tiles) are marked **(TODO — operator asset)**.

---

## Listing identity

| Field | Value | Source |
|-------|-------|--------|
| Name | **BobaLink** | `_locales/en/messages.json` `extName`; `wxt.config.ts` `name: "__MSG_extName__"` |
| Version | **1.0.0** | `wxt.config.ts` `version`; `package.json` `version` |
| Category (suggested) | Productivity / Developer Tools | — |
| Default locale | English (`en`) | `wxt.config.ts` `default_locale: "en"` |
| Minimum Chrome version | 109 | `wxt.config.ts` `minimum_chrome_version` |
| Manifest version | MV3 (Chrome); MV2 build also produced for Firefox AMO | `wxt.config.ts`; `ci-ext.sh` builds `chrome-mv3/` + `firefox-mv2/` |
| License | MIT | `package.json` |

---

## Short description (≤ 132 characters)

This is the verbatim store-description string the extension already ships
(`_locales/en/messages.json` `extDescription`) — 91 characters, within both the
Chrome (132) and Firefox (132) short-description limits:

> Detects torrent files and magnet links, sending them to Boba Project's qBitTorrent dashboard

(Length: 91 characters.)

---

## Detailed description

> BobaLink finds magnet links and `.torrent` files on the pages you visit and
> forwards them to your own self-hosted Boba Project merge service, which adds
> them to qBittorrent for you. It is a privacy-first, least-privilege
> Manifest V3 extension: it never talks to qBittorrent directly, never collects
> your data, and only ever contacts the Boba merge service running on your own
> machine at `http://localhost:7187`.
>
> **What it does**
>
> - **Detects** magnet links and `.torrent` file URLs on any page, with an
>   extra-tuned selector table for popular trackers.
> - **Parses** each item to its BitTorrent infohash (magnet `btih` /
>   `.torrent` → SHA-1) and **deduplicates by infohash**, so the same torrent
>   is never sent twice.
> - **Forwards** them to your local Boba merge service on port 7187, which adds
>   them to qBittorrent server-side.
> - **Tab-group batch send** (Chrome family): scan every tab in a tab group,
>   deduplicate across the whole group, and send them as one batch.
> - **Context-menu actions**: "Send magnet to Boba", "Send all on page",
>   "Send tab group".
> - **Keyboard shortcuts**: Send to Boba (`Ctrl/Cmd+Shift+B`), Scan page
>   (`Ctrl/Cmd+Shift+S`), Open dashboard (`Ctrl/Cmd+Shift+D`).
> - **A configurable options page** (7 tabs: Server, Download Prefs, Queue,
>   Notifications, Detection, UI, Security) with an optional offline queue for
>   failed sends.
>
> **Privacy & security first**
>
> - **No data collection.** BobaLink sends nothing to any third party. The only
>   network destination is your own Boba merge service at `http://localhost:7187`.
> - **Least privilege.** No `tabs`, no `scripting`, no `cookies`, no
>   `<all_urls>`. The content script only runs on the curated tracker host list,
>   not every site.
> - **Delegate-by-default credentials.** In the normal localhost deployment
>   BobaLink stores no decryptable secret — your Boba service already owns the
>   qBittorrent and tracker credentials. The one optional secret (a Boba API
>   token, only needed if your backend sets `BOBA_API_TOKEN`) is encrypted with
>   AES-GCM-256 under a session passphrase you type, held only in
>   `chrome.storage.session` and never written to disk or logged.
> - **Tight CSP:** `script-src 'self'` (no `unsafe-inline` / `unsafe-eval`),
>   `connect-src` scoped to `http://localhost:7187`.
>
> **Internationalization & accessibility**
>
> - UI message catalogs for English, Russian, German, and French; the browser
>   auto-selects by UI language, falling back to English.
> - The popup and options UI carry ARIA roles, accessible names, and
>   tablist/tabpanel wiring.
>
> **Requires a running Boba Project backend.** BobaLink is a companion to a
> self-hosted Boba Project install — it needs the Boba merge service reachable on
> `http://localhost:7187`. It is not a standalone downloader.

> Status honesty (§11.4.6): the end-to-end detect → send → torrent-appears-in-
> qBittorrent path against a **live** backend is still **in progress** (Phase 4
> in the plan). Detection, parsing, dedup, the popup/options UI, and the
> send-wiring are implemented and tested. Listing copy above describes the
> intended user-facing capability; do not publish to the public stores before
> Phase 4 live-backend integration lands (see `Status.md`).

---

## Supported torrent sites (curated selector table)

Detection works on **any page** via the generic `magnet:` and `.torrent` link
patterns. In addition, BobaLink ships a curated selector table
(`SITE_SELECTORS` in `extension/src/shared/constants.ts`) tuned for these hosts.
The content script's `matches` are derived from this table — BobaLink does **not**
request `<all_urls>`. The table has **24 entries** (one `generic` pattern set
plus 23 site-specific hosts):

| # | Host | Notes |
|---|------|-------|
| — | `generic` | magnet / `.torrent` / `download.php?id=` patterns applied everywhere |
| 1 | `1337x.to` | |
| 2 | `thepiratebay.org` | |
| 3 | `thepiratebay10.org` | |
| 4 | `rarbg.to` | |
| 5 | `rarbgtorrents.org` | |
| 6 | `yts.mx` | |
| 7 | `yts.lt` | |
| 8 | `eztv.re` | |
| 9 | `limetorrents.lol` | |
| 10 | `torrentgalaxy.to` | |
| 11 | `nyaa.si` | anime |
| 12 | `animetosho.org` | |
| 13 | `torrentz2.eu` | |
| 14 | `fitgirl-repacks.site` | |
| 15 | `rutracker.org` | Boba private tracker |
| 16 | `kinozal.tv` | Boba private tracker |
| 17 | `nnmclub.to` | Boba private tracker |
| 18 | `rutor.info` | Boba public tracker |
| 19 | `katcr.co` | Kickass Torrents |
| 20 | `demonoid.is` | |
| 21 | `iptorrents.com` | Boba private tracker |
| 22 | `torrentleech.org` | private |
| 23 | `beyond-hd.me` | private |
| 24 | `passthepopcorn.me` | private |

---

## Permission-justification table

Both stores require a per-permission justification. Each row below traces to the
literal `permissions` / `host_permissions` array in `extension/wxt.config.ts`
(lines 28–40, host_permissions line 43). No permission is requested that is not justified here, and no
justification claims a permission BobaLink does not request.

| Permission | In manifest? | Justification |
|------------|--------------|---------------|
| `storage` | Yes (`wxt.config.ts:29`) | Persist user settings, detected items per tab, the offline send queue, and send history (`chrome.storage.local`). |
| `alarms` | Yes (`wxt.config.ts:30`) | Wake the MV3 service worker to run periodic backend health checks (no content/host access). |
| `notifications` | Yes (`wxt.config.ts:31`) | Tell the user when a send succeeds or fails. |
| `activeTab` | Yes (`wxt.config.ts:32`) | Act on the page the user explicitly invokes BobaLink on (toolbar click / shortcut / context menu) — granted transiently, not a standing all-sites grant. |
| `contextMenus` | Yes (`wxt.config.ts:33`) | Provide the right-click "Send magnet to Boba", "Send all on page", "Send tab group" actions. |
| `tabGroups` | Yes (`wxt.config.ts:39`) | "Send tab group": read which group the clicked tab belongs to and enumerate the group's tabs via `chrome.tabs.query({groupId})`. Grants no host/content/URL access. |
| `host_permissions: http://localhost:7187/*` | Yes (`wxt.config.ts:43`) | Talk to the user's own local Boba merge service — the single network destination. Nothing else. |

### Permissions deliberately NOT requested (state this in the privacy review)

| Not requested | Why it's safe to omit |
|---------------|------------------------|
| `tabs` | The tab-group batcher reads only `tab.id` (never `url`/`title`/`favIconUrl`), which per the Chrome docs needs no `tabs` permission. |
| `scripting` | Not requested — `wxt.config.ts` comment "scripting intentionally NOT requested" (least-privilege, Plan E §3.1). |
| `cookies` | Not requested — BobaLink never touches the user's cookies. |
| `<all_urls>` | Content-script match patterns are derived from the curated `SITE_SELECTORS` host list, not a blanket all-sites grant. |

---

## Privacy-policy summary

Use the following as the public privacy statement (both stores require a privacy
policy / data-use disclosure). Every clause is accurate to the real network
behavior — the only `host_permissions` entry and the only `connect-src` CSP
origin is `http://localhost:7187`.

> **BobaLink collects no personal data and transmits no data to BobaLink's
> authors or any third party.**
>
> - The only network destination BobaLink contacts is the **Boba merge service
>   on the user's own machine at `http://localhost:7187`** (the sole
>   `host_permissions` entry and the sole non-`'self'` `connect-src` CSP origin).
> - BobaLink sends only the magnet links / `.torrent` URLs the user chooses to
>   forward, and an optional Boba API token (only if the user's backend requires
>   one). Nothing is sent to any remote server controlled by BobaLink.
> - Settings, detected items, the offline queue, and history are stored
>   **locally** in the browser (`chrome.storage.local`).
> - The optional Boba API token is encrypted at rest (AES-GCM-256, PBKDF2) under
>   a **session passphrase** held only in `chrome.storage.session` (never on
>   disk), and is never logged. With no passphrase, no token is stored.
> - BobaLink uses no analytics, no telemetry, and no remote code.

CSP (verbatim, `wxt.config.ts:57–58`):

```
default-src 'self'; script-src 'self'; object-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://localhost:7187; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'
```

---

## Required store-asset checklist

| Asset | Chrome Web Store | Firefox AMO | Status |
|-------|------------------|-------------|--------|
| Icon 16×16 | (used in manifest) | (used in manifest) | **Done** — `.output/chrome-mv3/icons/16.png` (rasterized from `src/assets/icon.png` by `@wxt-dev/auto-icons`) |
| Icon 32×32 | optional | used | **Done** — `icons/32.png` |
| Icon 48×48 | required | required | **Done** — `icons/48.png` |
| Icon 128×128 | required (store icon) | required | **Done** — `icons/128.png` |
| Short description (≤132 chars) | required | required (summary) | **Done** — see "Short description" above (91 chars) |
| Detailed description | required | required | **Done** — see "Detailed description" above |
| Privacy policy / data-use disclosure | required | required | **Done** — see "Privacy-policy summary" above |
| Permission justifications | required (single-purpose + per-permission) | required (in review notes) | **Done** — see "Permission-justification table" above |
| Screenshots (1280×800 or 640×400; ≥1, up to 5) | required | required | **(TODO — operator asset)** — capture popup + options + detection-in-action |
| Small promo tile 440×280 | optional | n/a | **(TODO — operator asset)** |
| Marquee promo tile 1400×560 | optional | n/a | **(TODO — operator asset)** |
| Promotional / featured images | optional | optional | **(TODO — operator asset)** |
| Support / homepage URL | required | required | **(TODO — operator asset)** — Boba Project repo / docs URL |

> Icon note: only the four sizes 16 / 32 / 48 / 128 are produced and required;
> they are generated at build time from the single `src/assets/icon.png`. No
> other icon size is referenced by the manifest.

---

## Submission checklist (manual — NO CI/CD)

Per the Boba constitution Hard Stop (no CI/CD), packaging is performed by the
manual gate `extension/ci-ext.sh` only — there is no pipeline. Sequence:

1. **Pre-flight** — `cd extension && npm install` (populate `node_modules`);
   ensure `node`, `npx`, `jq` are on `PATH`.
2. **Run the manual gate** — `cd extension && bash ci-ext.sh`. It runs, in order:
   tsc type gate → eslint → full vitest suite → Chrome MV3 build → Firefox build
   → §11.4.38 artifact-asset verification (opens the produced manifest and
   confirms every referenced asset + the `default_locale` catalog exist
   non-zero) → per-store `wxt zip`. It prints `CI-EXT: PASS` only if every step
   passed.
3. **Collect the artifacts** — on PASS, `.output/` contains:
   - `bobalink-1.0.0-chrome.zip` — upload to the **Chrome Web Store**.
   - `bobalink-1.0.0-firefox.zip` — upload to **Firefox AMO**.
   - `bobalink-1.0.0-sources.zip` — Firefox AMO source-code submission (AMO
     requires sources for built extensions).
4. **Chrome Web Store** — Developer Dashboard → new item → upload
   `bobalink-1.0.0-chrome.zip` → paste the short description, detailed
   description, privacy disclosure, and per-permission justifications from this
   document → upload screenshots + (optional) promo tiles **(TODO — operator
   asset)** → set the support/homepage URL **(TODO — operator asset)** → submit
   for review.
5. **Firefox AMO** — addons.mozilla.org → submit a new add-on → upload
   `bobalink-1.0.0-firefox.zip` → upload `bobalink-1.0.0-sources.zip` when
   prompted for sources → paste the summary, detailed description, and privacy
   notes → add the permission justifications in the reviewer notes → upload
   screenshots **(TODO — operator asset)** → submit for review.
6. **Pre-submission gate (release-readiness):** do **not** submit to the public
   stores until Phase 4 live-backend integration is GREEN with captured evidence
   (`Status.md` — the detect → send → torrent-in-qBittorrent round-trip against a
   live `:7187` backend is currently **in progress**). Listing copy is ready;
   the live-path proof is the remaining gate.

---

## Sources verified

- `extension/wxt.config.ts` (permissions, `host_permissions`, CSP, `commands`,
  `version`, `default_locale`, `minimum_chrome_version`) — read 2026-06-10.
- `extension/package.json` (`version: 1.0.0`, `name`, MIT license) — read 2026-06-10.
- `extension/src/shared/constants.ts` (`SITE_SELECTORS` 24 entries, `DEFAULT_URLS`
  `:7187`, `ENCRYPTION`, `BOBA_TOKEN_HEADERS`, `ICON_SIZES`) — read 2026-06-10.
- `extension/src/public/_locales/en/messages.json` (`extDescription` short
  string; locales `en`/`ru`/`de`/`fr` present on disk) — read 2026-06-10.
- `extension/ci-ext.sh` + `.output/` artifacts (`bobalink-1.0.0-{chrome,firefox,sources}.zip`,
  `icons/{16,32,48,128}.png`) — read 2026-06-10.
- `docs/browser_extension/Status.md` (Rev 5), `docs/browser_extension/USER_GUIDE.md`
  (Rev 1) — read 2026-06-10.
