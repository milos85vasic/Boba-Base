# BOB-082 — Closure Evidence

**Date:** 2026-09-25
**Status:** Completed (→ Fixed.md)

## Item's actual scope (per its own NOTE, narrower than the title)

> NOTE: BOB-064..067 have been created 2026-08-10 as Task/Queued (the four
> Lava P1..P4 items); the closed-as-Implemented status flip (citing
> per-finding implementing commits) remains owed under this item.

So the item's real remaining work is NOT item creation (already done
2026-08-10) — it is verifying/completing the closure of whichever of the
four legs are actually finished, with evidence.

## Verification of current state (2026-09-25)

```
$ sqlite3 docs/workable_items.db "SELECT atm_id, status, title FROM items WHERE atm_id IN ('BOB-064','BOB-065','BOB-066','BOB-067');"
BOB-064|Completed (→ Fixed.md)|Lava P1: Durable remote execution (systemd-linger helper)
BOB-065|Queued|Lava P2: Egress diagnosis and VPN-host SOCKS routing (containers pkg/egress)
BOB-066|In progress|Lava P3: BOBA_UPSTREAM_PROXY in download-proxy + qBitTorrent-go + Jackett + compose env-forward
BOB-067|Completed (→ Fixed.md)|Lava P4: Jackett cookie-login hardening + behaviorally-equivalent HelixQA fake
```

**BOB-064 (P1) and BOB-067 (P4) are already closed with full, rich
evidence** (`docs/Fixed.md`) citing the exact implementing commits/files
(`scripts/lib/durable-run.sh`, `qBitTorrent-go/internal/jackett/client.go`),
regression challenges (`challenges/scripts/durable_run_helper_challenge.sh`,
`challenges/scripts/jackett_cookie_login_hardening_challenge.sh`,
`challenges/scripts/helixqa_jackett_fake_behavioral_equivalence_challenge.sh`),
§11.4.115 RED/GREEN polarity proofs, §1.1 paired-mutation rehearsals, and
live equivalence captures — both entries explicitly state "Closes
RD2-15/GA-05 (P1/P4 leg of the four Lava-porting items BOB-064..067)".

Note on closure vocabulary: the item's own text says "closed as
Implemented" — per §11.4.33's closed-set mapping, `Task`-type items close
as `Completed`, not `Implemented` (`Implemented` is reserved for
`Feature`-type items). BOB-064/067 are Type=Task and correctly closed as
`Completed (→ Fixed.md)`. The item's loose wording does not indicate a
defect — the substance (evidence-cited closure) is satisfied.

**BOB-065 (P2) and BOB-066 (P3) are genuinely NOT finished** — Queued and
In progress respectively. This is NOT a gap in BOB-082's scope: BOB-082
asks to close legs that ARE done with evidence, not to prematurely close
unfinished work (doing so would itself be a §11.4 PASS-bluff). The
remaining two legs are correctly tracked and progressed under their own
items (BOB-065, BOB-066), outside BOB-082.

## GA-05 finding re-verified as resolved

The item's own reproduction step:
```
$ grep -in lava\|BOB-06[4-7] docs/Issues.md docs/Fixed.md
```
now returns many hits across both files (BOB-064/067 in Fixed.md with full
evidence; BOB-065/066 in Issues.md, actively tracked) — the zero-hit state
GA-05 originally measured (2026-08-08, before the items existed) no longer
holds.

## Disposition

BOB-082's literal scope — item creation (done 2026-08-10) + evidence-cited
closure of the finished legs (done, verified above) — is complete. The two
still-open legs are correctly out of scope for this item and continue
under BOB-065/BOB-066.

## Classification

Project-specific (§11.4.17) — workable-item bookkeeping; no constitution
change.
