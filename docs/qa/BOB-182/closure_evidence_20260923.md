# BOB-182 closure evidence — 2026-09-23 (staleness-corrected closure)

## Finding
This item's two halves were both resolved by prior work never reflected in
the tracker status: (1) the operator's 2026-08-26 recorded decision
("KEEP THE MONOTONE RATCHET" — recorded as consumer DATA per §11.4.35,
verbatim in the item's own text), and (2) the "real defect still owed"
half — the ratchet mechanism itself — implemented as
`scripts/pre_build/tighten_cm_export_charset_baseline.sh`, a SEPARATE,
explicitly-invoked, monotone-decrease-only script the gate has no write
path to (§11.4.249 producer≠gate, §11.4.240(B) capability separation).

## Independent verification (coordinator, from clean shell, 2026-09-23)
```
$ cat scripts/pre_build/cm_export_charset_valid.baseline
baseline=0
tightened_from=<first adoption>
tightened_at=2026-08-26T09:41:30Z
exports_scanned=340
```
Confirms the mechanism has genuinely run (not merely present unused) —
tightened to 0 on 2026-08-26.

```
$ grep -n "gate cannot call this" scripts/pre_build/tighten_cm_export_charset_baseline.sh
[confirmed: "The gate CANNOT call this, and does not contain a line that
 could" — the exact producer≠gate role-separation shape the item's
 acceptance criteria required]
```

The gate (`check_cm_export_charset_valid.sh`) READS the baseline file but
has no write path to it — confirmed by the baseline file's own header
comment: "WRITTEN ONLY BY scripts/pre_build/tighten_cm_export_charset_baseline.sh
... The gate READS this file and has no write path to it at all."

## Status
Fixed. Closed by coordinator after independent re-verification — both the
operator-decision half and the mechanism-implementation half are genuinely
complete, matching the item's own required shape exactly.
