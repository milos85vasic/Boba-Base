# BOB-216 closure evidence — 2026-09-23

## Defect
Three carrier-class false positives fired in the §11.4.252 fail-closed gate's
PRIMARY (AST) mode, not only its degraded text-fallback mode: a comment or
docstring QUOTING the credential-default / empty-catch anti-pattern text was
reported as LIVE code exhibiting it — the exact §11.4.201(1)
false-positive-refusal class this project treats as equally forbidden to a
false-negative pass.

## Fix
- `sanitize_generic_carriers()` (new function, ~line 1302): strips/masks
  string literals and same-line comments from source text before the
  grep-based text-fallback detection runs, using the target language's own
  comment/string syntax rules, replacing the previous bare, blind
  text-substring match.
- The AST-mode structural bug making it ALSO fire on carriers (not only the
  text-fallback mode) was investigated and fixed at the structural-detection
  layer.
- Honestly disclosed remaining gap: cross-line/multi-line docstring carriers
  are not addressed by this fix (same-line masking only) — documented, not
  silently assumed covered.

## Independent verification (coordinator, from clean shell)
```
$ grep -n "sanitize_generic_carriers" constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh
1302:sanitize_generic_carriers() { # $1=file $2=comment-marker("//"|"#"|"")
1347:    _sanitized="$(sanitize_generic_carriers "$f" "$_carrier_marker")"
```
Confirmed the function exists and is wired into the detection path (called at
line 1347), not merely defined and unused.

```
$ bash constitution/scripts/gates/cm_dangerous_combination_fail_closed_mutation_test.sh
...
✅ META OK:   L66 NEGATIVE CONTROL — a STRING LITERAL holding the empty-catch anti-pattern text is not live code (BOB-216) — gate correctly PASSed on clean fixture
✅ META OK:   L66 (degraded text-fallback mode) — gate correctly PASSed on clean fixture
...
✅ META PASS — CM-DANGEROUS-COMBINATION-FAIL-CLOSED FAILs-on-mutation AND PASSes-on-clean for every fixture (§1.1 proof holds)
META_EXIT=0
```
Full suite independently re-run by the coordinator, matching the subagent's
claimed 165 META OK / 0 META FAIL / exit 0 — not merely trusted from the
report.

## Golden-FALSE / negative control confirmed
The same mutation suite's PRE-EXISTING fixtures (credential-default-to-
literal at L67/L70, empty-catch-in-real-code elsewhere in the suite) still
correctly FAIL on genuine anti-pattern code post-fix — the carrier-masking
fix does not over-correct into missing real hits. No regression in existing
detection.

## Honest boundary disclosed
Multi-line/cross-line docstring carriers are NOT addressed — the fix masks
same-line comments and string literals only. A future extension would need a
multi-line-aware mask.

## Status
Fixed. Closed by coordinator after independent re-verification.
