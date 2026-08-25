# BOB-169 — export charset corruption: review **GO** (round 4)

**Revision:** 1
**Last modified:** 2026-08-25T17:50:00Z

Four review rounds on the §11.4.209 substrate, iterated to zero findings per §11.4.134.
**BOB-169 is NOT closable on this change** — see "Still owed" below.

## What was wrong

Three producers emitted HTML with no `<meta charset>`; weasyprint rendered PDFs
from those body fragments, fell back to a non-UTF-8 codec, and baked mojibake
into the PDF **text layer** — not a display artifact, corruption in the bytes.

`docs/CONTINUATION.pdf` — the §12.10 session-resumption document — carried
**336 corrupted lines** and regenerated corrupt on every run. Corpus-wide,
**301 of 334** exports carried no charset declaration while every export-sync
gate reported green.

## The three producers, now in lockstep

| Producer | Fix |
|---|---|
| `scripts/generate_markdown_exports.sh` | `--standalone` + charset-aware staleness + PDF staleness keyed on the HTML |
| `scripts/regenerate-continuation-exports.sh` | `--standalone` (the third producer, found only because the corpus scan was run) |
| docs_chain `derived.go:139` | already passed `--standalone` |

## Verified closed, by round

| Finding | Closure |
|---|---|
| R2-F1 (BLOCKING) — PDF staleness ignored the HTML, so a fixed HTML never re-rendered its PDF | `[[ ! -f "$pdf" \|\| "$md" -nt "$pdf" \|\| "$html" -nt "$pdf" ]]`. Reviewer re-ran the real-corpus shape on an unmodified copy: `BEFORE charset=0 pdf_moj=1` → `AFTER charset=1 pdf_moj=0`, plus an **idempotence control** it added and I had not run: a second consecutive run leaves the PDF md5 unchanged, so the clause heals without churning clean pairs |
| R2-F2 — gate renumbering | Re-derived a third time on a three-shape needled instrument: `sites=50 {bracket:41, run_const_gate:9}`, denominators `[50]`, 1..50 complete, zero duplicates, strictly increasing |
| R2-F3 — baseline honesty | Header states `BASELINE` is a CONSTANT, nothing lowers it, tightening is manual |
| R2-F5 / R3-F1 — my inserted paragraph severed a sentence | Reflowed; sentence reads whole; `bash -n` clean |

## Round-4 regression sweep (reviewer-executed)

| | |
|---|---|
| `test_export_pdf_charset_integrity.sh` | 2 passed, 0 failed |
| `test_cm_export_charset_valid.sh` | 6 passed, 0 failed |
| `CM-EXPORT-CHARSET-VALID` (invariant 50) | PASS at baseline 301, no regression |
| `docs/CONTINUATION` | charset **1**, mojibake **0** (was 336) |
| §11.4.263 / residue / staging | clean; `HEAD` still `dd9fcb5` |

## The comment-only claim — two needles, not one

I proved the reflow was comment-only by stripping full-line comments and blanks
from HEAD's copy and the working copy and diffing: 26 body lines each, exactly
one differing (`pandoc … -o` → `pandoc … --standalone -o`, the fix itself).
I ran ONE needle (`echo NEEDLE` → diff fires).

The reviewer ran **two**, and the second is the better instrument: it appended a
comment-only line and confirmed the body diff stays SILENT. One positive needle
proves an instrument is not dead; it does not prove it is aimed correctly. With
both, "comment-only" is a measured property rather than an inference.

## Still owed — stated so nothing reads as closed

**Acceptance (c)** — bulk regeneration of the 301 charset-less exports.
Mechanism present, correctly sequenced behind R2-F1, **run not performed**,
needs a quiescent tree.

**BOB-182** — the §11.4.224(E) ratchet-adoption decision. Filing it satisfies
the TRACKING obligation, not the DECISION obligation: the clause requires the
operator's answer recorded as consumer DATA *before first enforcement*, and
invariant 50 is already enforcing. The item stays OPEN. The interim is
deliberate and matches §11.4.201(8)'s own precedence for the §11.4.135 ratchet —
pinned at baseline it can only fire on regression, so enforcement today is
near-inert while the decision is owed.

## Carrier/blindness census for this item — five instances, three of them mine

1. `grep -qi 'charset'` in my own test matched `charset-fixture` and PASSED against a broken generator
2. my bracket-only renumber audit saw 41 of 50 labels
3. the reviewer's bracket-only scan, same blindness
4. the reviewer's name-requiring scan, which silently dropped invariants 1–4 and 11–15
5. mojibake counted inside quoted examples

Every one was caught by the same discipline: **refuse to report a zero until a
needle of the same shape as the query proves the instrument can see it.**

## What could not be analysed (reviewer's own statement, carried verbatim in substance)

- The full 50-invariant sweep — invariant 50 run in isolation, numbering audited statically; the other 49 gates' behaviour under the renumbered file unverified.
- The nine `run_const_gate` gate scripts themselves — only their labels.
- weasyprint's specific fallback codec — established non-UTF-8 and charset-driven, not identified.
- The python-markdown fallback branch — never executes on this host, unexercised by the guard.
- Rendering fidelity beyond the text layer.
- The tree was never quiescent across any round.
