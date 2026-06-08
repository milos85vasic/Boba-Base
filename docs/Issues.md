# Issues — Open Workable Items

**Revision:** 4
**Last modified:** 2026-06-06T19:00:00Z
**Ticket prefix:** `BOB` (operator-mandated, 2026-06-06)
**Scope:** Open/active items only. Closed items migrate to [`Fixed.md`](Fixed.md).

> Tracking interim: this is the Markdown tracker. The full constitution-grade
> SQLite single-source-of-truth + `docs_chain` engine + procedure docs are
> themselves tracked below as **BOB-010** (not yet built). Until then this
> file + [`Issues_Summary.md`](Issues_Summary.md) are authoritative for open work.

---

## BOB-015 — Remaining public-tracker failures are external / non-deterministic

**Status:** Queued
**Type:** Bug
**Severity:** Low
**Created:** 2026-06-06

systematic-debugging FINDING (determinism test): the residual per-tracker
failures are **external/non-deterministic** (site availability + network from
this host), NOT code root causes. Two consecutive identical live searches:
run A = 909 results / 14 success / 10 error; run B = **1422 results / 19
success / 5 error**; `nyaa, piratebay, snowfl, torlock` flipped error→success
with **zero** success→error flips. The orchestrator already isolates per-tracker
failures (other trackers succeed), so impact is bounded.

Residual (external-triggered): `kickass` (timeout), `tokyotoshokan` (SSL EOF;
also crashes ungracefully on empty response — minor missing guard), `yts`
(intermittent). The deterministic `jackett` crash within this set was split out
and FIXED as **BOB-016**. RuTracker CAPTCHA is **BOB-008**.
**Resolution direction:** low priority; optionally add empty-response guards to
the crash-prone plugins (defense-in-depth) — upstream sites' availability is
outside our control.

## BOB-008 — RuTracker automated login blocked by CAPTCHA

**Status:** Operator-blocked
**Type:** Bug
**Created:** 2026-06-06
**Operator-Block-Details:** WHAT — RuTracker login with stored creds returns
no session cookie (CAPTCHA wall). WHY — automated user/pass login is
CAPTCHA-gated; self-resolution exhausted (creds correct + wired, login
attempted, `auth=True`). UNBLOCK — operator completes the CAPTCHA flow at
`/api/v1/auth/rutracker/captcha` + `/login`, or pastes a fresh `bb_session`
cookie via `/auth/rutracker/cookie-login`. WHO — operator.

**Evidence:** live search per-tracker stat `rutracker status=error auth=True
error="login returned no session cookie — likely CAPTCHA"`.

## BOB-009 — Containers submodule integrated with Go wrapper

**Status:** In progress
**Type:** Task
**Created:** 2026-06-06

Submodule added; `cmd/boba-ctl/` Go binary wraps `pkg/compose` + `pkg/runtime`
with `up`/`down`/`status`/`health`/`list` subcommands. Remaining work: wire
`boba-ctl up` into `start.sh` as opt-in replacement for raw `podman compose up`,
add HelixQA test bank for boba-ctl operations. See `docs/Issues.md` for pending
sub-items.
