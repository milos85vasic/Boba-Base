# BOB-210 closure evidence — 2026-09-22

## Fix (documentation-only, behavior unchanged and explicitly permitted by the item)

`docker` is not installed on this host (confirmed again this session:
`command -v docker` empty), so the docker branch of `detect_rootless()`
could not be validated against a real rootless daemon — the same
constraint the original author faced. The existing carrier-trap tests
already treat "ambiguous non-matching docker output → confident rootful →
refuse" as the CORRECT, desired security behavior, and the item explicitly
forbids weakening that. So the fix corrects the CLAIM to match the CODE
rather than the reverse.

`scripts/ownership_precondition.sh` header block (~lines 333-370) rewritten
to: (a) remove the unqualified false claim ("an unverified reading can never
manufacture a refusal" — now quoted only as an explicitly-refuted historical
citation, not asserted), (b) precisely state the "fail toward unknown"
property covers only command-level failures/empty output, NOT a successful
non-empty read that simply lacks the `name=rootless` marker, (c) honestly
record that the docker branch's whole convention remains unvalidated against
a real docker install (§11.4.21-style tracked gap) rather than overclaiming
in either direction.

No behavioral code was touched — only comments.

## Independently re-verified this session

```
$ bash tests/unit/test_ownership_rootless_detection.sh
  PASS: sandbox: declared location left empty (no probe residue)
RESULT: 19 passed, 0 failed
```

(the full pre-existing 19-case polarity matrix, unchanged and still green —
confirms no behavioral code was touched)

```
$ bash tests/unit/test_ownership_precondition_docker_premise.sh
  PASS: control: git HEAD's pre-fix header asserts the claim with NO nearby refutation, reproducing the reported defect — Case 1 is discriminating
RESULT: 4 passed, 0 failed, 0 skipped
```

(new test asserting the false claim is gone/refuted-in-context, the measured
behavior it was wrong about is still real via an independent shimmed-docker
run, the honest replacement claim is present, and a control run against the
git-HEAD pre-fix header reproduces the original unqualified claim)

See `docs/qa/BOB-208/closure_evidence_20260922.md` for the combined
`git diff --stat`.

## Residual honest gap (NOT closed by this fix, recorded not silenced)

The docker branch's whole convention remains genuinely unmeasured against a
real rootless docker daemon on this host — this fix corrects the
documentation to state that honestly, it does not close the underlying
measurement gap (which needs a rootless docker install this host does not
have, per §11.4.21 operator-gated).
