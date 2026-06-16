# QA Evidence — search + auth fixes verified on nezha (2026-06-16)

**Revision:** 1
**Last modified:** 2026-06-16T00:00:00Z

Real end-to-end verification on the live distributed-boot production stack
(`nezha.local`, podman). Anti-bluff §11.4 / §11.4.107 / §11.4.69 — assertions are
on user-observable outcomes (result counts, real titles, per-tracker status),
NOT status codes.

## 1. Private-tracker cookie auth (operator-supplied browser cookies)

Operator complaint: rutracker/nnmclub never authenticated. Fix: `NNMCLUB_COOKIES`
(existing) + the new `RUTRACKER_COOKIES` injection (commit `2fc29fc`), cookies
extracted from the operator's browser export by `scripts/extract-tracker-cookies.sh`
(only the tracker's own-domain cookies, §11.4.10).

| Tracker | query | status | total | sample real title |
|---|---|---|---|---|
| rutracker | `the matrix` | completed | **50** | "Матрица / The Matrix (Энди/Ларри Вачовски)" |
| nnmclub | `the matrix` | completed | **50** | "The Matrix OST (1999)", "Matrix Resurrections (2021)" |

Both were auth-failing every query before (rutracker `no_cookie`/CAPTCHA,
nnmclub Cloudflare Turnstile). Container env confirmed carrying both cookie vars
(`phpbb2mysql_4_sid`=1, `bb_session`=1).

## 2. Multi-word query URL-encoding crash (the "search broken / crashing a lot")

Root cause (FACT): ~17 nova3 plugins interpolated the RAW query into a request
URL; a literal space crashed urllib (`URL can't contain control characters`).
Single-word worked, multi-word silently lost the plugin. Fix: per-plugin
URL-encoding (commits `dbd3858` 7 maintained + `da7d709` 10 adopted/limetorrents)
+ honesty classifier `plugin_bad_query_encoding` (`33d90f2`).

Scoped multi-word search (`the matrix`) of the 10 adopted plugins — search_id
`6a3da978-d2d4-4b2d-bb6b-a1dfb5d8c43f`, **total=592**:

| plugin | status | results |
|---|---|---|
| glotorrents | success | 173 |
| torrentdownload | success | 249 |
| torrentproject | success | 68 |
| snowfl | success | 40 |
| limetorrents | success | 36 |
| torrentscsv | success | 25 |
| rockbox | success | 1 |
| linuxtracker | empty | 0 (no error — no match for this query) |
| pirateiro | empty | 0 (no error) |
| yourbittorrent | error | 0 — `deadline_timeout` (slow, NOT an encoding crash) |

**`STILL bad_query_encoding/crashed: NONE`** — the encoding-crash storm is
eliminated. (Earlier maintained-7 run: bitsearch 60, torrentgalaxy 150, nyaa 5.)
Full-fleet `the matrix` previously returned 1135–1705 results.

## 3. auth/status now reflects cookies (commit `9c2f8dc`)

`/auth/status` previously showed red/unauthenticated chips for rutracker/nnmclub
despite working searches (it only read `_tracker_sessions`, populated after a
search). Now reflects the `*_COOKIES` env so the dashboard shows them green.

_Captured 2026-06-16 against nezha.local; unit coverage: 54 multiword tests +
auth-status cookie-reflection test, all with §1.1 negation proofs._
