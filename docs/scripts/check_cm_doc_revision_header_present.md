# check_cm_doc_revision_header_present.sh

**Revision:** 1
**Last modified:** 2026-09-26T14:00:00Z

## Overview

Gate `CM-DOC-REVISION-HEADER-PRESENT` (pre-build invariant 62, BOB-242).
Enforces the §11.4.44 revision header on every script guide under
`docs/scripts/`.

## Why this exists

The constitution named this gate but only one unrelated ledger file was ever
checked. BOB-223 registered it as gate debt; this is the implementation for the
scope BOB-242 names. Wider §11.4.44 scope (other `docs/` trees) is not claimed.

## Rule

Within the first 15 lines of each guide:

```
**Revision:** <positive integer>
**Last modified:** YYYY-MM-DDTHH:MM[:SS]Z
```

The timestamp must be ISO 8601 in UTC (a trailing `Z`); an offset such as
`+0300` is refused.

## Usage

```bash
bash scripts/pre_build/check_cm_doc_revision_header_present.sh .
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | every guide has a valid header |
| 1 | at least one guide is missing a field or has a malformed one (each is named) |
| 2 | harness error: bad arguments, not a git repo, or zero guides enumerated |

## Adoption

Measured 2026-09-26: 1 of 45 guides failed (`tunnel-keepalive.md` used an offset
timestamp). It was corrected in the same change, so the gate is a hard floor
with no baseline.

## Related scripts

- `tests/pre_build/test_check_cm_doc_revision_header_present.sh` — 12 arms.
- `scripts/pre_build/check_cm_script_docs_sync.sh` — the §11.4.18 guide-existence
  and freshness gate.

## Last verified

2026-09-26 — real tree: `OK: all 45 guides under docs/scripts/ carry a §11.4.44
revision header` (before these two guides were added); test suite 12 passed.
