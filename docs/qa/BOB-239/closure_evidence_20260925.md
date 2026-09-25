# BOB-239 — Closure Evidence

**Date:** 2026-09-25
**Status:** Completed (→ Fixed.md)

## Fix applied

All 30 identified pre-existing items corrected via
`workable-items update --status "Completed (→ Fixed.md)" --location Fixed`:
BOB-005, BOB-015, BOB-016, BOB-042 through BOB-058 (17 consecutive),
BOB-059, BOB-141, BOB-150, BOB-161, BOB-168, BOB-182, BOB-192, BOB-199,
BOB-228, BOB-232.

## Verification

```
$ sqlite3 docs/workable_items.db "SELECT COUNT(*) FROM items WHERE current_location='Fixed' AND ((type='Task' AND status NOT LIKE 'Completed%' AND status NOT LIKE 'Obsolete%') OR (type='Bug' AND status NOT LIKE 'Fixed%' AND status NOT LIKE 'Obsolete%') OR (type='Feature' AND status NOT LIKE 'Implemented%' AND status NOT LIKE 'Obsolete%'));"
0
```

Zero remaining §11.4.33 closure-vocabulary violations across the whole DB.

## Acceptance criterion 2 (mechanical prevention) — see BOB-240

The item's acceptance criterion 2/3 (extend `workable-items close`/`update`
to validate the status word against Type, and extend `validate` to catch
this class) is genuinely separate implementation work on the constitution
submodule's Go CLI — split out as its own tracked item (BOB-240) rather
than bundled into this bookkeeping-correction closure, so the correction
work (done, verified) is not blocked on the harder mechanical-fix work
(not yet done).

## Classification

Project-specific (§11.4.17) — workable-item bookkeeping correction.
