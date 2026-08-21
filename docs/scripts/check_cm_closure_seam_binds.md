# scripts/pre_build/check_cm_closure_seam_binds.sh — CM-CLOSURE-SEAM-BINDS gate

**Revision:** 1
**Last modified:** 2026-08-21T16:00:00Z
**Status:** active
**Item:** BOB-136 (closure seam does not bind)

## Purpose

Make the **closure seam** bind mechanically. The gate reconciles what the
repository's own git history says happened against what the workable-items
tracker says the state is, and reports — or, at the commit seam, **refuses**
— when the two contradict each other.

## The defect it closes (BOB-136)

Nothing in this repo ever linked a commit back to its tracker row:

| existing check | compares |
|---|---|
| `workable-items validate` | the DB against **its own** invariants |
| `workable-items diff` | the DB against **the Markdown** |
| `docs-sync-commit-seam.sh` CHECKS 1–3 | the DB against **the Markdown** |
| `docs_chain verify` | the Markdown against **its exports** |

Every one of those compares the tracker to *itself*. All four are green
while a row says `Queued` and git says the work landed weeks ago. Closure
therefore depended on a human remembering, and demonstrably did not happen
— a 2026-08-20 sweep found `BOB-076`, whose commit message literally says
`closes BOB-076`, still `Queued`, and a 2026-08-21 sweep found 20 more.

A status field that does not move when work lands stops being evidence and
becomes decoration, and every downstream reader of status silently degrades:
release gates, the "is this owed?" question, and the §11.4.55 reopen counts
used to rank the most fragile work. §11.4.227: an item's done state is its
**seam** landing, not its **text** landing. This gate is that seam.

## What it asserts — and deliberately does not

The gate never decides "this item is finished". It asserts the far narrower,
mechanically decidable proposition that a specific *status literal is false*:

| class | condition |
|---|---|
| `CONTRADICTION` | a message says it CLOSES/FIXES/RESOLVES `<id>`, yet `<id>` is non-terminal |
| `UNRECONCILED` | a **work-type** commit declares `<id>`, yet `<id>` is exactly `Queued` — which asserts *no work has started* |
| `UNTRACKED-ID` | a commit declares `<id>` and `<id>` has no row at all |

Remediation for `UNRECONCILED` is `In progress` **or** a close; the gate does
not presume which. Statuses that already tell the truth about landed work —
`In progress`, `Ready for testing`, `In testing`, `Reopened`,
`Operator-blocked`, and every terminal `... (→ Fixed.md)` — are never flagged
by `UNRECONCILED`. That scoping is what keeps it from firing on a healthy
tree (§11.4.201(1)).

## Carrier controls (§11.4.201(7)(a) — match structure, not substring)

A gate that flags correctly-tracked work is exactly as broken as one that
misses stale rows: it gets switched off within a week. Links are therefore
extracted **structurally** — conventional-commit scope token, bare-id subject
prefix, closure-keyword adjacency — never by "the message contains the
string". Four carrier classes are excluded by construction, each with a
fixture in the meta-test:

| id | carrier | example |
|---|---|---|
| c1 | filing verb | `docs(tracker): file BOB-149` — filing an item is not doing it |
| c2 | path component | `docs/qa/BOB-117/closure-evidence.md` |
| c3 | quoted text | a work commit quoting `"closes BOB-076"`, or an indented / `>`-quoted pasted ticket |
| c4 | non-work type | `docs(BOB-141): ...`, `chore`, `ci` |

Live proof of c1: `BOB-146` and `BOB-149` were both *filed* on 2026-08-21 and
the sweep reports neither.

Both real in-repo spellings are handled: compact runs
(`closes BOB-081/083/089/117`, `docs(BOB-124/125/126)`) and suffixed scope
tokens (`BOB-111-followup`, `BOB-122-fallout`). A needle exercising only the
plain spelling would certify a blind query.

## Usage

```bash
scripts/pre_build/check_cm_closure_seam_binds.sh                  # sweep all history
scripts/pre_build/check_cm_closure_seam_binds.sh --report-only    # audit, never exit 1
scripts/pre_build/check_cm_closure_seam_binds.sh --message-file F # COMMIT-SEAM mode
scripts/pre_build/check_cm_closure_seam_binds.sh --message "TEXT" # COMMIT-SEAM mode
scripts/pre_build/check_cm_closure_seam_binds.sh --self-test      # §11.4.107(10)
```

Options: `--repo DIR` `--db PATH` `--prefix P` `--rev-range R` `-v`

## Internal behaviour

* **CHECK A — closure seam.** Extracts structural commit↔item links, joins
  them against the tracker (read-only; the gate never writes to the DB) and
  classifies as above.
* **CHECK B — flagless-diff callers.** BOB-136 acceptance (b). Sweep mode
  only. `workable-items diff --db X` *without* `--issues`/`--fixed` opens
  zero Markdown files and still prints `DB and Markdown are in sync` — a
  §11.4.201(6) **false-null**. Until the shared engine refuses that
  invocation, no caller here may use it. Scanned over tracked executable
  files only: docs and this gate's own header legitimately quote the
  flagless form, and matching those would be the exact carrier mistake.
* **Control needle (§11.4.201(7)(b)).** A zero-finding verdict is worthless
  if the extractor is blind — a blind query and a clean tree return the
  identical quiet zero. Before reporting, the gate runs a synthetic message
  carrying the *same load-bearing features* as the real query (scope form,
  compact run, closure keyword) and aborts with exit 2 if fewer than 4/4
  known links are seen.

## Commit-seam mode

Evaluates **only** the ids the pending message declares. It is monotone by
construction: it can refuse the commit about to create fresh drift, and is
structurally incapable of blocking on the pre-existing backlog. That is why
it needs no baseline/ratchet file — a file which would itself rot (§11.4.215).

Wired via `scripts/hooks/docs-sync-commit-seam.sh` **CHECK 5**, which
`scripts/commit-push-all.sh` invokes with `--message "$MSG"`. CHECK 5 is
placed deliberately *before* the hook's "no docs-chain source staged" early
exit: CHECKS 1–4 all trigger on a staged tracker file, but a commit landing a
pure **code** fix stages no tracker file at all — and that is precisely the
commit whose row fails to move. Running it after the early exit would make it
structurally unable to see the defect it exists for (§11.4.196(F)).
Backward-compatible: without `--message`, CHECK 5 does not run.

## Exit codes

| code | meaning |
|---|---|
| 0 | PASS, or `--report-only`, or an honest §11.4.3 SKIP |
| 1 | FAIL — findings, each named on stderr with its remediation |
| 2 | ERROR — usage, missing repo, or a failed control needle |

An absent DB or `sqlite3` is a loud SKIP-with-reason exiting 0: an unreadable
tracker is not evidence of drift, and refusing on it would be the
§11.4.201(1) false positive this gate exists to avoid. CHECK B still runs in
that case — sequencing it behind the tracker check was a false-null caught by
this gate's own meta-test (fixture `bad-6`).

## Honest boundary (§11.4.6)

The gate can only see work that **declares its id**. Work landing under a
message carrying no id at all is invisible to it — that is BOB-136's second
defect verbatim, and `BOB-146` is a live instance: its fix landed under
`fix(fail-open): triage all 36 §11.4.252 hits...`, which names no item. The
gate does not claim to prevent all drift.

It also proves only that a status literal is false — never that an item is
finished. Closure evidence remains §11.4.115(F) / §11.4.146(D3) territory,
and terminal-side integrity (an evidence path that does not resolve) is
already covered by `workable-items validate` (HXC-217).

## Related

* `tests/pre_build/test_check_cm_closure_seam_binds.sh` — §1.1 paired-mutation
  meta-test, 29 hermetic checks (golden-bad, golden-good, 5 carrier controls,
  commit-seam polarity).
* `scripts/hooks/docs-sync-commit-seam.sh` — CHECK 5 wiring.
* `scripts/commit-push-all.sh` — passes `--message "$MSG"` at stage 5a.
