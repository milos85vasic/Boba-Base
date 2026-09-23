# BOB-213 closure evidence — 2026-09-23

## Defect
`constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh`'s default
extension list omitted `sh`/`bash` entirely — 198 tracked `.sh` files
project-wide, including 71 of 74 source files in the `scripts/` DANGER_ROOT
directly, were invisible to the §11.4.252 fail-closed gate.

## Fix
- `DANGEROUS_COMBO_EXT` default extended: `... php rb sh bash` (line 603).
- Shell-native credential-default-to-literal detector added (parameter
  expansion `${TOKEN:-literal}` shape), matching the existing Python/JS/Go
  detectors' semantics. The shell try/catch-block counterpart (shape A) is
  explicitly, honestly declined — shell has no fixed block syntax to key on
  for that shape; documented in-source (lines 480-489) rather than silently
  assumed covered, per §11.4.6.

## Independent verification (coordinator, from clean shell)
```
$ grep -n "DANGEROUS_COMBO_EXT" constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh
603:exts="${DANGEROUS_COMBO_EXT:-py go rs c cc cpp h hpp java cs js ts jsx tsx php rb sh bash}"
```
Confirmed `sh bash` present in the default list.

```
$ bash constitution/scripts/gates/cm_dangerous_combination_fail_closed_mutation_test.sh
...
✅ META OK:   L67 shell credential silently defaulted to a literal via parameter expansion (BOB-213) — gate correctly FAILed on the mutation (rc=1)
✅ META OK:   L67 (degraded text-fallback mode) — gate correctly FAILed on the mutation (rc=1)
✅ META OK:   L68 NEGATIVE CONTROL — shell credential fallback to ANOTHER VARIABLE is legitimate (BOB-213) — gate correctly PASSed on clean fixture
✅ META OK:   L69 NEGATIVE CONTROL — shell credential fallback to COMMAND SUBSTITUTION is legitimate (BOB-213) — gate correctly PASSed on clean fixture
✅ META OK:   L70 pre-existing credential-default-to-literal shape, now DISCOVERABLE in a .sh file (BOB-213 extension-list fix) — gate correctly FAILed on the mutation (rc=1)
...
✅ META PASS — CM-DANGEROUS-COMBINATION-FAIL-CLOSED FAILs-on-mutation AND PASSes-on-clean for every fixture (§1.1 proof holds)
META_EXIT=0
```
Full suite re-run independently by the coordinator (not trusted from the
subagent's report alone) — 165 META OK, 0 META FAIL, exit 0.

## Honest boundary disclosed
No shell-native counterpart for the try/catch-block swallowed-exception shape
(shape A) — shell has no decidable block syntax to key on for this, same
reasoning the gate already applies to declining unreliable cross-statement
heuristics elsewhere. Documented in-source, not silently assumed covered.

## Status
Fixed. Closed by coordinator after independent re-verification.
