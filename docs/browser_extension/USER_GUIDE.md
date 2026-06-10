# BobaLink — User Guide

**Revision:** 1
**Last modified:** 2026-06-10T21:00:00Z
**Scope:** End-user guide for BobaLink, the Boba Project browser extension (`extension/`).
**Authority:** `docs/browser_extension/Status.md` (Rev 4) + `docs/browser_extension/IMPLEMENTATION_PLAN.md`.

> Accuracy note (§11.4.6): every statement below reflects the real extension
> source/config as of HEAD `2011810`. Capabilities still in progress are marked
> **(planned)** or **(in progress)** so nothing reads as shipped that is not.

---

## What BobaLink does

BobaLink is a cross-browser **Manifest V3** WebExtension (built with WXT +
TypeScript). It:

- **detects** magnet links and `.torrent` file URLs on the pages you visit;
- **parses** them (magnet `btih` infohash / `.torrent` → SHA-1 infohash) and
  **deduplicates** by infohash so the same torrent is never sent twice;
- **forwards** them to the **Boba merge service on `http://localhost:7187`**,
  which adds them to qBittorrent server-side.

The extension never talks to qBittorrent directly — it only knows about the Boba
merge service on port 7187. (`extension/wxt.config.ts` `host_permissions` =
`http://localhost:7187/*`; `extension/src/shared/constants.ts` `DEFAULT_URLS`.)

The end-to-end detect → send → torrent-appears-in-qBittorrent path against a
**live** backend is **(in progress)** — Phase 4 in the plan. The detection,
parsing, dedup, and UI layers are implemented and tested.

---

## Supported torrent sites

Detection works on **any page** via the generic `magnet:` and `.torrent` link
patterns. In addition, BobaLink ships a curated selector table
(`SITE_SELECTORS` in `extension/src/shared/constants.ts`) tuned for these hosts.
The content script's `matches` are derived from this table — BobaLink does **not**
request `<all_urls>`.

The curated table covers **24 entries** (one `generic` pattern set plus 23
site-specific hosts):

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

(That is 23 site-specific hosts plus the `generic` set — the project refers to
this as the **24 supported sites** table.)

---

## How detection works

- The content script scans the page for magnet links and `.torrent` URLs using
  the site selectors above plus the generic regex patterns
  (`MAGNET_REGEX`, `TORRENT_FILE_REGEX` in `constants.ts`).
- It watches the page for changes with a `MutationObserver` (500 ms debounce —
  `DEBOUNCE_DELAYS.MUTATION`) so links added by single-page-app navigation are
  picked up too.
- Each detected item is parsed to its infohash and **deduplicated by lowercase
  infohash**, so the same torrent appearing in several places on a page is sent
  once.

---

## The popup

Click the BobaLink toolbar icon to open the popup. It shows the torrents detected
on the current page and lets you send them to Boba:

- **Send** — send a single selected detected item to the Boba merge service.
- **Send All** — send every detected item on the current page (deduplicated).

The popup also surfaces a connection/status indicator (badge colours are defined
in `BADGE_COLORS`: healthy / degraded / error / scanning / detected).

> The live-backend round-trip these buttons perform is **(in progress)** —
> Phase 4. The popup, detected-list rendering, and Send / Send-All wiring are
> implemented and tested.

---

## Context-menu actions

Right-click a page (or a magnet link) to use BobaLink's context-menu items
(defined in `extension/src/background/index.ts`):

- **Send magnet to Boba** (`bobalink-send`) — send the right-clicked magnet link.
- **Send all on page** (`bobalink-send-all`) — send every detected torrent on
  the current page.
- **Send tab group** (`bobalink-send-group`) — scan **every tab in the current
  tab group**, deduplicate across the whole group, and send them as one batch.

The "Send tab group" batch path is wired (`MENU_SEND_GROUP` → deduped group
batch → a single `addMagnets` request). It is a Chrome-family feature (uses
`chrome.tabGroups`); on browsers without tab groups it degrades gracefully.

You can hide the context-menu items from **Options → UI → Show context-menu
items**.

---

## Keyboard shortcuts

Three shortcuts are declared in `extension/wxt.config.ts` (`commands`):

| Action | Windows / Linux | macOS |
|--------|------------------|-------|
| Send to Boba (`send-to-boba`) | `Ctrl+Shift+B` | `Command+Shift+B` |
| Scan page (`scan-page`) | `Ctrl+Shift+S` | `Command+Shift+S` |
| Open dashboard (`open-dashboard`) | `Ctrl+Shift+D` | `Command+Shift+D` |

These are *suggested* keys; your browser may let you remap them on its extension
shortcuts page (e.g. `chrome://extensions/shortcuts`). You can disable shortcut
handling from **Options → UI → Enable keyboard shortcuts**.

---

## The 7 options tabs

Open the options page (right-click the icon → Options, or your browser's
extension-details "Extension options"). It has **seven tabs**
(`extension/src/entrypoints/options/index.html` + `src/options/options.ts`,
`TAB_IDS`):

1. **Server** — server name, **Server URL** (default `http://localhost:7187`),
   authentication method (None / Username+Password cookie / API Key / Basic),
   the optional **Boba API token** + **Session passphrase** (see below),
   connection timeout (seconds), health-check interval (minutes), and "Verify
   HTTPS certificates (HTTPS only)".
2. **Download Prefs** — default category, default save path, content layout
   (Original / Create subfolder / No subfolder), pause-after-add, skip hash
   check, automatic torrent management.
3. **Queue** — enable the offline queue for failed sends, max queue size
   (default 50), max history items (default 100).
4. **Notifications** — show notifications, play a sound on completion, auto-send
   detected torrents (no confirmation).
5. **Detection** — automatically scan pages, auto-scan delay (ms), highlight
   detected torrents, highlight style (Badge / Border / Glow).
6. **UI** — show context-menu items, enable keyboard shortcuts.
7. **Security** — explains the delegate-by-default model and offers an
   "Enable debug logging" toggle.

---

## The optional Boba API token + session passphrase

BobaLink follows a **delegate-by-default** security model: in the normal
localhost deployment it stores **no decryptable secret at all** — it just posts
magnets/URLs to the local merge service, which already owns the qBittorrent and
tracker credentials.

The **only** optional secret is a **Boba API token**, which is needed *only if*
your Boba backend sets the `BOBA_API_TOKEN` environment variable (the backend
token gate is open by default and enforced only when that variable is set).

When you supply a token on the **Server** tab, BobaLink encrypts it **only under
a session passphrase you type** (AES-GCM-256 via PBKDF2 — `ENCRYPTION` in
`constants.ts`):

- The passphrase is held in `chrome.storage.session` only and is **never
  persisted** to disk.
- There is **no fixed/embedded encryption key and no empty-passphrase path** —
  if you enter a token but no passphrase, the token is **not stored** and a
  notice tells you to add a passphrase (`src/options/options.ts`).
- The plaintext token and the passphrase are never logged.

When the token is present and unlocked, the Phase-4 client sends it as either an
`Authorization: Bearer <token>` or `X-Boba-Token: <token>` header
(`BOBA_TOKEN_HEADERS`). Full decrypt-and-send wiring is landed and tested; the
end-to-end against a live token-gated backend is **(in progress)**.

---

## Least-privilege permissions — what BobaLink asks for and why

BobaLink requests only what it needs (`extension/wxt.config.ts`):

| Permission | Why it is requested |
|------------|---------------------|
| `storage` | persist your settings, detected items, the offline queue, and history |
| `alarms` | keep the service worker alive and run periodic health checks |
| `notifications` | tell you when a send succeeds/fails |
| `activeTab` | act on the page you explicitly invoke BobaLink on |
| `contextMenus` | provide the right-click "Send …" actions |
| `tabGroups` | read which group the clicked tab belongs to, for "Send tab group" |
| `host_permissions: http://localhost:7187/*` | talk to the local Boba merge service — nothing else |

### What BobaLink deliberately does **not** request

- **`tabs`** — the tab-group batcher reads only `tab.id`, which per the Chrome
  docs needs no `tabs` permission. BobaLink never reads tab URLs/titles/favicons.
- **`scripting`** — not requested.
- **`cookies`** — not requested; BobaLink never touches your cookies.
- **`<all_urls>`** — the content script's match patterns are derived from the
  curated `SITE_SELECTORS` table, not a blanket all-sites grant.

Its content security policy is tight: `script-src 'self'` (no `unsafe-inline` /
`unsafe-eval`), and `connect-src` scoped to `http://localhost:7187`
(`content_security_policy` in `wxt.config.ts`).

---

## Internationalization & accessibility

- BobaLink ships UI message catalogs for **English (`en`)**, **Russian (`ru`)**,
  **German (`de`)**, and **French (`fr`)** (`src/public/_locales/{en,ru,de,fr}`,
  packaged into the build). Chrome/Firefox auto-select by the browser UI language,
  falling back to English. More locales are **(planned)** (the plan targets 8).
- The popup and options UI carry ARIA roles, accessible names, and
  tablist/tabpanel wiring, validated by an accessibility test suite. Deeper WCAG
  work (contrast/focus/full keyboard coverage) and theme-switch evidence are
  **(in progress)**.

---

## Current status at a glance

Phases 1–3 (foundation, detection/parsing, the content/background/popup/options
shell) plus the WXT build wiring are **PASS**. Backend integration (Phase 4),
tab-group batch polish (Phase 5), i18n/a11y/themes (Phase 6), the full
security/credentials suite (Phase 7), full multi-type test coverage (Phase 8),
and distribution (Phase 9) are **in progress**. See
`docs/browser_extension/Status.md` for the authoritative per-phase state.
