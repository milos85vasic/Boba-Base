# BOB-115 Evidence — Pre-Fix RED Transcript

**Revision:** 1
**Last modified:** 2026-08-18T19:37:41Z
**Item:** BOB-115 — Fix workable-items validate over-scoping to Updated-events (BOB-010 id=64 pattern)
**Constitution:** §11.4.5 / §11.4.69 / §11.4.115 / §11.4.226 (closure-evidence-at-closure + RED→GREEN + §1.1 mutation)

`workable-items validate` against the real, unmodified live DB — the BOB-010 id=64 false blocker, captured BEFORE the fix landed.

```text
validate: 1 violation(s):
  - BOB-010: closure evidence_path does not resolve (well-formed path, but nothing exists there) — history id=64, event=Updated, on=2026-08-10: "scripts/docs_chain.sh" (§11.4.5/§11.4.69/§11.4.123/§11.4.226 — a closure's captured proof must be producible on demand)
VALIDATE_EXIT=1

```
