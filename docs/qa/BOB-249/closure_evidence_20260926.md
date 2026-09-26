# BOB-249 closure evidence

**Revision:** 1
**Last modified:** 2026-09-26T15:08:22Z

**Command:** `for t in test_generate_markdown_exports_content_staleness test_export_staleness_oracle test_export_staleness_parser_edges test_compute_badges_export_scope test_workable_items_export_deterministic test_generate_markdown_exports_engine_parity; do nice -n 19 bash tests/unit/$t.sh 2>&1 | grep -oE '[0-9]+ passed, [0-9]+ failed' | tail -1; done | awk '{p+=$1; f+=$3} END{print p" passed, "f" failed"}'`
**Result Summary:** 77 passed, 0 failed
**Evidence Layer:** runtime
**Test Type:** integration

## What was reported

The pre-build invariant 30 (CM-BASH-UNIT-TESTS-EXECUTED) failed with "N tracked
file(s) mtime-moved while the bash suite ran": tracked export twins (.docx/.html/.pdf
beside .md) were rewritten during the sweep. Reproduced at the merge-base 120fd78 (15
files) and at main 88767fc (18 files), so it predates the zero-shortcomings audit feature.

## Root cause (measured, not inferred)

1. `git checkout` writes x.docx and x.html before x.md, so after a checkout hundreds of
   .md files are strictly newer (ns) than their own twins: 226 of 455 md newer than their
   .docx in a fresh clone.
2. `scripts/generate_markdown_exports.sh` decided staleness with `$md -nt $twin` (mtime),
   while the pre-build gate CM-MARKDOWN-EXPORT-SYNC used a content-history oracle.
3. `scripts/compute-badges.sh` ended every run by calling that generator with NO path
   argument, sweeping the whole real tree even when invoked on fixtures;
   `tests/unit/test_compute_badges_carrier_match.sh` did exactly that inside invariant 30's
   window (bisect with the trigger present: 42 twins rewritten, 91 files past the marker).
4. pandoc stamps the wall-clock time in docx docProps/core.xml, so every regeneration was
   byte-different. The Go export in scripts/workable-items-export.sh re-renders the four
   tracker documents on every run.

## Fix (commits afe5d1f a630935 74e5b6f e47346b 624a8d3 5f1c4bc 09aed1f 96767c7)

Staleness now uses the gate's oracle (extended to .docx, NUL-safe, full-history);
SOURCE_DATE_EPOCH pins make output byte-stable; compute-badges exports only the in-repo
files it modified; the generator installs atomically in the twin's directory, heals
structurally corrupt twins, fails loudly on an HTML-leg failure, and renders docs_chain-owned
files exactly as the engine does. Every change was written test-first (RED observed), and two
independent reviews (plus scoped re-reviews) approved the final code.

## Evidence

Re-runnable command above (sum of the regression tests guarding the root causes; identical
output on two consecutive runs, 77 passed, 0 failed, tree clean afterwards).

Fresh-checkout measurement (scratch clone, generator over all 456 in-scope .md files):
before the fix 310 twins rewritten (42 html, 42 pdf, 226 docx); after 0, with a control
needle (a real content edit still regenerates its 3 twins).

Full pre-build sweep, captured from the real run logs, on a quiet tree:

Baseline at merge-base 120fd78 (old constitution pin 25980c1):

```
  FAIL [1]: CM-BASH-UNIT-TESTS-EXECUTED: 15 tracked file(s) mtime-moved while the bash suite ran: README.docx README.html README.pdf docs/Fixed.docx docs/Fixed.html docs/Fixed.pdf docs/Fixed_Summary.d
  FAIL [2]: CM-GATE-LEDGER-RATCHET: exit 1 — ❌ CM-GATE-LEDGER-RATCHET: FAIL — see LEDGER-FAIL lines above; land the missing gate(s), register their deferral(s) against a tracked item, or (for va
  FAIL [3]: CM-GITIGNORE-SWALLOW-GUARD: exit 1 — a first-party source file is silently swallowed by .gitignore
=== Result: 52 passed, 3 failed ===
```

main at 88767fc before the fix:

```
CM-BASH-UNIT-TESTS-EXECUTED: 18 tracked file(s) mtime-moved while the bash suite ran
=== Result: 53 passed, 2 failed ===
```

main after the fix, first sweep (tracker re-exported once onto the stable-date scheme):

```
  PASS [31]: CM-BASH-UNIT-TESTS-EXECUTED: 84 bash unit/pre_build test(s) green (5 quarantined, 0 expected-red), no-trace verified across 5903 tracked paths (needle proven)
  FAIL [1]: CM-GATE-LEDGER-RATCHET: exit 1 — ❌ CM-GATE-LEDGER-RATCHET: FAIL — see LEDGER-FAIL lines above; land the missing gate(s), register their deferral(s) against a tracked item, or (for va
=== Result: 54 passed, 1 failed ===
```

main after the final code (commit 96767c7), second sweep:

```
  PASS [17]: CM-MARKDOWN-EXPORT-SYNC: all in-scope docs have fresh .html/.pdf siblings
  PASS [26]: docs_chain engine: verify --all in-sync (2 contexts checked)
  PASS [31]: CM-BASH-UNIT-TESTS-EXECUTED: 88 bash unit/pre_build test(s) green (5 quarantined, 0 expected-red), no-trace verified across 5908 tracked paths (needle proven)
  FAIL [1]: CM-GATE-LEDGER-RATCHET: exit 1 — ❌ CM-GATE-LEDGER-RATCHET: FAIL — see LEDGER-FAIL lines above; land the missing gate(s), register their deferral(s) against a tracked item, or (for va
=== Result: 54 passed, 1 failed ===
```

The tree was clean (0 modified files) after both post-fix sweeps; before the fix each
sweep left 14 to 18 rewritten twins.

## Honest boundary

- The remaining sweep failure is CM-GATE-LEDGER-RATCHET (BOB-237, unimplemented 414 vs
  baseline 403), unrelated and pre-existing.
- The sweep lines above are pasted from run logs; only the regression-test command is
  cheap enough to re-run as the machine-checkable part of this closure.
- Known limits tracked in BOB-250: an owned twin cannot converge after a whitespace-only
  commit; a quoted docs_chain node path containing a space is mis-parsed; the sha-tag oracle
  proposal for that residual case is not implemented.
