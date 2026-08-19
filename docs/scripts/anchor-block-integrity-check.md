# scripts/anchor_block_integrity_check.sh — mechanical §11.4.227(B) anchor-block-integrity gate

**Revision:** 1
**Last modified:** 2026-08-19T00:00:00Z
**Status:** active
**Item:** BOB-105 (§11.4.238 followup — mechanical §11.4.227(B) anchor-block-integrity check)

## Overview

`scripts/anchor_block_integrity_check.sh` mechanically enforces
§11.4.227(B) — the rule that propagation-class gates count anchor
BLOCK-STARTS across a declared lockstep mirror set, never bare
literals. It resolves four defect classes that a >=1-literal
presence-gate cannot see:

1. **BLIND-EXTRACTOR** — zero block-starts extracted from a listed
   file (§11.4.201(6) false-null guard).
2. **DUPLICATE-OR-COLLISION** — the same anchor id `§11.4.NNN` heads
   more than one block-start in a single file. A duplicate is usually
   a cut-and-paste mistake; a *collision* is §11.4.54's forbidden
   case — two different mandates minted under the same anchor number.
   Both fail with the same finding class; the block hashes tell them
   apart at review.
3. **LOCKSTEP-DIVERGENCE** — the same anchor's block has different
   content-hashes across the mirror set (§11.4.157 lockstep broken).
4. **LOCKSTEP-GAP** — the same anchor appears in some mirrors but not
   others (a mirror is missing the anchor entirely).

Sub-anchor prefix-match protection is built in: `§11.4.10.A` is a
distinct id from `§11.4.10`, captured whole. Mid-body citations like
`§11.4.115(F)` are excluded by construction (the block-start regex
never accepts them at line start).

## Configuration is DATA (§11.4.35)

The checker carries **no** project-specific literal. It reads its
mirror-set + block-start regex from a config file resolved in this
order:

1. `--config <path>` argument
2. `$ANCHOR_INTEGRITY_CONFIG` env var
3. `scripts/anchor_block_integrity_check.conf` (default)

The default config declares `constitution/CLAUDE.md`, `AGENTS.md`,
`QWEN.md`, `GEMINI.md` as the byte-identical mirror set and
`Constitution.md` as the canonical variant (excluded from mirror-hash
equality per §11.4.227(B) canonical-vs-mirror layer variance).

## Usage

```bash
# Run against the default mirror set:
scripts/anchor_block_integrity_check.sh

# Run against an alternate config (used by the challenge harness):
scripts/anchor_block_integrity_check.sh --config /path/to/other.conf

# Verbose (per-file block-start count):
scripts/anchor_block_integrity_check.sh --verbose
```

Exit codes:
- `0` — every invariant holds; PASS emitted to stdout.
- `1` — one or more findings; each on stderr as `FAIL: <class>: <detail>`.
- `2` — configuration/environment error (missing config, unreadable
  file). Distinct from finding-level FAIL per §11.4.201(4)
  conservative-safe default.

## Anti-bluff — §11.4.107(10) self-validation

The checker ships with `challenges/scripts/anchor_block_integrity_challenge.sh`,
which runs it against five fixtures under
`challenges/fixtures/anchor_block_integrity/`:

| fixture                  | expected rc | expected finding class |
| ------------------------ | ----------- | ---------------------- |
| `golden-good`            | 0           | (none)                 |
| `negative-control`       | 0           | (none — mid-body citations) |
| `golden-bad-duplicated`  | 1           | `DUPLICATE-OR-COLLISION` |
| `golden-bad-diverged`    | 1           | `LOCKSTEP-DIVERGENCE`  |
| `golden-bad-collision`   | 1           | `DUPLICATE-OR-COLLISION` |

A checker that PASSes a golden-bad fixture, or FAILs `golden-good`
or `negative-control`, is itself the bluff (§11.4.107(10)) and the
harness exits 1.

## Findings from the first real run (2026-08-19)

The first run against the actual `constitution/` mirror set reported
**176 findings**, dominated by two classes:

- **LOCKSTEP-GAP** on the majority of §11.4.5..§11.4.99 range —
  anchors that carry a `### §11.4.NNN` block-start in one mirror
  (typically `CLAUDE.md` or `AGENTS.md`) but no matching block-start
  in one or more of the other three mirrors. Per-mirror asymmetry is
  the mechanism §11.4.227(B) predicts: a >=1-literal presence-gate
  reads GREEN on each mirror in isolation while the mirror set as a
  whole is uneven.
- **LOCKSTEP-DIVERGENCE** on `§11.4.69`, `§11.4.192`, `§11.4.193`,
  `§11.4.227` — the same anchor is block-started in every mirror
  but the block body differs, so the four mirrors are not
  byte-identical for those anchors.

These findings are the §11.4.238 discovery-channel-escape signal
BOB-105 was minted to surface. Closure of individual findings is
constitution-submodule work outside this boba-side checker's scope;
this script's job is to make the class OBSERVABLE from a boba
pre-build gate per §11.4.226 (evidence-class-at-closure).

## Relationship to other anchors

- **§11.4.227(B)** — the rule this script mechanises.
- **§11.4.157** — content-hash lockstep across the mirror set.
- **§11.4.54** — anchor numbers never reused (collision detection).
- **§11.4.201(6)** — false-null guard on the extractor itself.
- **§11.4.107(10)** — golden-good + golden-bad + negative-control
  validation of the checker as an oracle.
- **§11.4.35** — consumer supplies mirror set + regex as DATA.
- **§11.4.6** — no guessing; every FAIL carries the resolved anchor
  id + file + hash prefix as captured evidence.

## Companion files

- `scripts/anchor_block_integrity_check.sh` — the checker itself.
- `scripts/anchor_block_integrity_check.conf` — the default config
  for boba's own constitution mirror set.
- `challenges/scripts/anchor_block_integrity_challenge.sh` — the
  §11.4.107(10) harness.
- `challenges/fixtures/anchor_block_integrity/` — the five fixtures.
