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

## §1. [BOB-015] Remaining public-tracker failures are external / non-deterministic

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

## §3. [BOB-008] RuTracker automated login blocked by CAPTCHA

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

## §5. [BOB-009] Containers submodule (§11.4.76) not integrated

**Status:** Queued
**Type:** Task
**Created:** 2026-06-06

`.gitmodules` lists only `constitution`. The constitution mandates consuming
`vasic-digital/containers` for container orchestration; the project uses
`docker-compose.yml` + `start.sh` instead. **Resolution direction:** add the
submodule + boot via its `pkg/boot`/`pkg/compose`/`pkg/health`, or record a
justified deviation.

## §6. [BOB-010] Workable-items SQLite DB + docs_chain + procedure docs not set up

**Status:** Queued
**Type:** Task
**Created:** 2026-06-06

The constitution-grade tracking system (SQLite single-source-of-truth per
§11.4.93/§11.4.95, `docs_chain` engine per §11.4.106, 5 procedure docs per
§11.4.63, per-domain Status/Status_Summary docs per §11.4.45/§11.4.56) is not
present. This Markdown tracker (Issues/Fixed + summaries, BOB prefix) is the
interim. The Go `workable-items` tool is scaffolded in the constitution
submodule (`constitution/scripts/workable-items/`) but not integrated.

## §8. [BOB-012] Many docs lack HTML/PDF exports; no export-sync gate (§11.4.65)

**Status:** Queued
**Type:** Task
**Created:** 2026-06-06

`docs/` is ~65% export-covered; `docs/CONTINUATION.md` and ~24
`docs/research/**` files lack HTML/PDF siblings, and no pre-build gate/hook
enforces export sync. **Resolution direction:** regenerate all exports + add a
`CM-MARKDOWN-EXPORT-SYNC`-class gate.
