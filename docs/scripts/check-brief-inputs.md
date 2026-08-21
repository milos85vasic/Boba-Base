# `scripts/hooks/check-brief-inputs.sh` — pre-dispatch input existence check

**Revision:** 1
**Last modified:** 2026-08-21T19:55:00Z
**Purpose:** §11.4.201(6) / §11.4.252 fail-closed check that every input a task
brief declares actually exists and is non-empty BEFORE a subagent is dispatched
against it.
**Last verified:** 2026-08-21

---

## Overview

A task brief names its source materials. If one of those files is missing when
the subagent starts, the agent does not stop — it proceeds against what it can
read and produces confident output grounded in less evidence than the brief
promised. That is the §11.4.201(6) FALSE-NULL at the dispatch layer: absent
input and empty input are indistinguishable from "nothing to say here".

MEASURED, the case this guard exists for: the forensic brief
`.superpowers/sdd/task-phase1a-brief.md` still exists, but the scratchpad
session directory holding its inputs is **entirely gone**. Run against that
brief today, this guard separates the 6 genuinely-missing files (naming each)
from the 2 that are present, and exits 1 — reproducing exactly what should have
blocked that dispatch.

## Prerequisites

- A readable brief file, or an explicit `--file` list. No network, no runtime.

## Usage

    bash scripts/hooks/check-brief-inputs.sh --brief <path-to-brief>
    bash scripts/hooks/check-brief-inputs.sh --file <p1> --file <p2>
    bash scripts/hooks/check-brief-inputs.sh --self-test

Exit status: `0` when every declared input exists and is non-empty; `1`
otherwise, with a per-path report naming each missing file and the remediation
("respawn the producer").

## Edge cases

- **Present but EMPTY is a failure, not a pass.** A zero-byte file is the
  clearest form of the false-null this guard exists to catch.
- **Path shorthand.** Briefs in this repo abbreviate long paths with `…`; the
  extractor handles that convention rather than silently skipping such lines —
  a skipped line would be a false-null of its own.
- **A brief with no `## Source materials` section** yields nothing to check;
  that is reported honestly rather than counted as a pass.

## Internal behaviour

Fails CLOSED (§11.4.252): when an input's status cannot be resolved, the guard
refuses rather than proceeding, and prints the resolved evidence for every
refusal (§11.4.201(5)) so a false positive is diagnosable in one step.

**Paired §1.1 mutation (verified):** neutering the existence/non-empty checks
makes the self-test FAIL and makes the real scan report "OK — all 8 present"
against the forensic brief — the exact fabricate-on-absent-evidence failure mode
this guard prevents. Restored, sha256-identical, both green.

## Known gap — stated rather than implied

This is **conductor-run tooling, not an automatic PreToolUse hook**. A brief's
required-input list lives in free-form prose that the Agent tool's structured
input does not expose, so an automatic prompt-scraping gate would itself be an
unproven pattern-match (§11.4.201(7)(a)). Its seam is therefore the dispatch
procedure — a habit backed by a runnable check — and that limitation is tracked
in **BOB-162** rather than papered over.

## Related

- `tests/hooks/test_check_brief_inputs.sh` — 15 real-invocation assertions
- `scripts/hooks/unattributed-commit-guard.sh` — sibling hygiene guard
