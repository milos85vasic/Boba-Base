# Tracker Discovery Sweep — Findings (§11.4.118)

**Revision:** 1
**Last modified:** 2026-06-16T00:00:00Z
**Status:** active
**Scope:** Boba merge-search tracker fleet — discovery-pressure sweep per §11.4.118
**Authority:** captured-evidence FACT from 3 sequential full-fleet nezha searches (29 enabled trackers each)

---

## Why this document exists (honest provenance — §11.4.6)

The §11.4.118 tracker discovery sweep ran on the **live nezha stack** (3 sequential
full-fleet searches, 29 enabled trackers each) but **could not write its findings
doc at the time because the host disk was full**. This document persists those
captured findings verbatim-faithfully. No embellishment: every line below is either
captured-evidence FACT or is explicitly labelled investigate / verify / known per
§11.4.6.

## Queries executed (captured FACT)

| # | Query        | Charset     | Outcome   | Merged results | Notes |
|---|--------------|-------------|-----------|----------------|-------|
| 1 | `ubuntu`     | ASCII       | completed | 435  | baseline |
| 2 | `the matrix` | multi-word  | completed | 1217 | **ZERO** `plugin_bad_query_encoding` — prior multi-word fix holds |
| 3 | `Война`      | Cyrillic    | completed | 1272 | exposes the P0 UTF-8 encoding bug |

## Categorization (captured FACT)

- **WORKING:** 12–14 trackers
- **EMPTY-no-error:** 1 tracker
- **FAILING:** 16 trackers (15 of them share one bug)

## HEADLINE — P0 UTF-8 encoding crash (captured stderr FACT)

15 plugins crash on the Cyrillic query. The query is not UTF-8-encoded into the
request URL. Captured stderr (example: `snowfl`):

```json
{"__error__": "'ascii' codec can't encode characters in position 48-52: ordinal not in range(128)"}
```

### Affected plugins (15)

`bitsearch`, `glotorrents`, `linuxtracker`, `nyaa`, `pirateiro`, `rockbox`,
`snowfl`, `tokyotoshokan`, `torlock`, `torrentdownload`, `torrentgalaxy`,
`torrentproject`, `torrentscsv`, `yourbittorrent`, `yts`.

**Fix (in progress, separate commit):** `urllib` `quote` / `quote_plus` of the
query before URL assembly.

## Per-tracker status matrix (captured FACT)

Legend — status across the 3 queries: `OK` = completed with results · `crash`
= ascii-codec crash on Cyrillic · `timeout` = deadline_timeout · `403` =
upstream HTTP 403 · `empty` = completed, zero results, no error.

| Tracker          | `ubuntu` (ASCII) | `the matrix` (multi-word) | `Война` (Cyrillic) | error_type                 | category        | fixable                   |
|------------------|------------------|---------------------------|--------------------|----------------------------|-----------------|---------------------------|
| bitsearch        | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| glotorrents      | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| linuxtracker     | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| nyaa             | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| pirateiro        | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| rockbox          | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| snowfl           | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| tokyotoshokan    | timeout          | OK                        | crash              | ascii-codec + deadline     | FAILING (P0)    | yes (UTF-8) / verify slow |
| torlock          | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| torrentdownload  | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| torrentgalaxy    | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| torrentproject   | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| torrentscsv      | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| yourbittorrent   | timeout          | OK                        | crash              | ascii-codec + deadline     | FAILING (P0)    | yes (UTF-8) / verify slow |
| yts              | OK               | OK                        | crash              | ascii-codec encode         | FAILING (P0)    | yes (UTF-8)               |
| kickass          | 403              | 403                       | 403                | upstream_http_403 (CF)     | FAILING (known) | no (upstream)             |
| gamestorrents    | empty            | empty                     | empty              | none                       | EMPTY-no-error  | undetermined              |

Trackers not listed above (the remaining 12 of the 29 enabled) completed all
three queries with results and are categorized **WORKING** (no captured error).

## Other captured findings

- **kickass** — `upstream_http_403` on all 3 queries. Cloudflare block. KNOWN /
  upstream, not a code defect.
- **tokyotoshokan + yourbittorrent** — additionally `deadline_timeout` on the
  ASCII query. Slow upstreams, not a code defect (distinct from the P0 crash).
- **gamestorrents** — EMPTY-no-error on all 3 queries. **Undetermined** (§11.4.6):
  niche-no-match vs silent parse-fail — not proven either way.

## Prioritized next-issues

| Priority  | Item | Status |
|-----------|------|--------|
| **P0**    | UTF-8 encoding crash in 15 plugins (ascii-codec on Cyrillic) | being fixed (`urllib quote/quote_plus`, separate commit) |
| **P1**    | gamestorrents 0-results on all queries | investigate (niche-no-match vs silent parse-fail) |
| **P2**    | tokyotoshokan / yourbittorrent slow-upstream timeouts | verify (slow upstream, not code) |
| **KNOWN** | kickass 403 (Cloudflare) | upstream, no code fix |

## Honest coverage note (§11.4.6)

- Only the **29 enabled** trackers were probed in this sweep.
- **14 DEAD_PUBLIC_TRACKERS were NOT re-tested** — they require
  `ENABLE_DEAD_TRACKERS=1` to participate. Their state is unknown from this sweep.
- The **15-crash verdict is captured-evidence FACT** (reproduced on the Cyrillic
  query with captured stderr).
- **gamestorrents (P1)** and the **slow-upstream timeouts (P2)** are
  *investigate / verify* items, **not proven** root causes.
