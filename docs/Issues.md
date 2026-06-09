# Issues — Open Workable Items

**Revision:** 5
**Last modified:** 2026-06-09T20:00:00Z
**Ticket prefix:** `BOB` (operator-mandated, 2026-06-06)
**Scope:** Open/active items only. Closed items migrate to [`Fixed.md`](Fixed.md).

> Tracking: this file + [`Issues_Summary.md`](Issues_Summary.md) are authoritative for open work.
> The SQLite single-source-of-truth + `docs_chain` engine (BOB-010) is complete.

---

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

