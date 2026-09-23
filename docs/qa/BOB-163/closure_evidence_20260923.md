# BOB-163 closure evidence — 2026-09-23 (staleness-corrected closure)

## Finding
This item was ALREADY FULLY IMPLEMENTED in a prior session (per in-source
comments citing "BOB-163" throughout `challenges/scripts/ddos_resilience_challenge.sh`,
landed by commit `76a1822` "docs(BOB-008,077,101,102,163,182,188,195): eight
operator decisions land as data, not prose") — the tracker status was never
advanced past "In progress" to reflect it.

## Operator decision (already recorded, 2026-08-26, §11.4.66)
"YES — 429 IS RESPONSIVE IF Retry-After IS WELL-FORMED." Assertion (c)
accepts 2xx OR a well-formed 429 (positive integer seconds or valid
HTTP-date, PARSED not merely present); DEGRADED remains connection
failure/timeout/5xx/malformed-429. Residual risk (a genuinely wedged
endpoint answering 429-with-valid-Retry-After would pass) explicitly
disclosed in-source, not hidden.

## Independent verification (coordinator, from clean shell, 2026-09-23)
```
$ bash challenges/scripts/ddos_resilience_challenge.sh --self-validate
...
PASS: self-validate — crash-resistance, rate-limit AND sibling-responsiveness
      detectors each distinguish their golden-good from their golden-bad
      fixture; the rate-limit detector does NOT fire on the
      advertises-but-never-enforces carrier; and the sibling detector holds
      the line against four 429s that DO carry a Retry-After header whose
      value is not well-formed, plus both polarities of the isolation
      decision and its empty-log fail-closed arm
      (§11.4.107(10) + §11.4.201(1)(6)(7)(a))
```
Confirmed EVERY fixture in the truth table classifies correctly:
`r429_valid_seconds` / `r429_valid_httpdate` -> responsive (per the operator
decision); `r429_missing` / `r429_garbage` / `r429_zero` / `r429_neg` /
`r429_baddate` -> degraded (the narrowing, not a blind acceptance of every
429). Producer≠oracle discipline (§11.4.249) confirmed in-source: the live
verdict path and `--self-validate`'s golden fixtures call the SAME parse
functions, so a mutation to the parse would break the self-test too.

## Still-open, correctly NOT covered by this closure
The item's own text notes a separate, still-open sub-question ("the detector
counts 429 only, not 503... decide when BOB-111 lands limiters on :7185 and
:7189") — BOB-111 remains "In progress" (not yet landed), so that
sub-decision is correctly not yet actionable and is NOT part of this
item's scope. This closure covers only BOB-163's own Retry-After-parsing
acceptance criterion, which is fully implemented and verified.

## Status
Fixed (already landed, tracker sync only). Closed by coordinator.
