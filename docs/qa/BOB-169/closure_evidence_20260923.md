# BOB-169 closure evidence — 2026-09-23 (staleness-corrected closure)

## Finding
This item's own `round4_GO.md` (2026-08-25) recorded two items "still
owed": (1) bulk regeneration of the 301 charset-less exports — "mechanism
present, correctly sequenced... run not performed, needs a quiescent
tree"; (2) BOB-182's operator ratchet-adoption decision, needed "before
first enforcement". Both were resolved by later, subsequent work
(commits `094ef87`/`e2d498a` "docs(BOB-169,BOB-188): regenerate every
export charset-clean" + BOB-182's 2026-08-26 recorded operator decision),
but the tracker status was never advanced to reflect it.

## Independent verification (coordinator, from clean shell, 2026-09-23)
```
$ bash scripts/pre_build/check_cm_export_charset_valid.sh
  generated exports scanned ......... 410
  declaring a charset ............... 410
  MISSING a charset ................. 0   (ratchet baseline 0)
PASS: CM-EXPORT-CHARSET-VALID — 0 charset-less exports, at baseline (no regression, ratchet current)
```
All 410 exports (more than the original 334-file corpus — new docs added
since carry charsets from birth) declare a charset, zero missing.

```
$ head -3 docs/BOBA_DATABASE.html
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
```
The originally-cited fragment example now begins with a proper DOCTYPE +
head (charset inside), confirmed standalone-document output.

## Status
Fixed. Closed by coordinator after independent re-verification that the
"still owed" bulk-regeneration + ratchet-adoption gaps are both resolved.
