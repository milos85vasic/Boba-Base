# BOB-199 closure evidence — 2026-09-23

## Defect / operator decision
Operator decision (2026-08-26, §11.4.66): flag a narrow `contextlib.suppress`
ONLY when combined with an irreversible capability (delete/truncate/kill) —
idiomatic narrow tolerances stay quiet.

## Fix
`classify_suppress`'s AST-mode machinery gained `IRREVERSIBLE_ATTRS`
(remove/unlink/rmtree/truncate/kill/killpg), `call_is_irreversible()`, and
`body_has_irreversible_call()` walking a narrow suppress's `with`-block. A
`# guardrails:allow <reason>` waiver silences a genuine hit; a marker with
no reason is honestly reported MALFORMED, never silently honored.
Root-caused and fixed a self-discovered over-broad first attempt that
flagged Python's own documented stdlib idiom (`suppress(FileNotFoundError):
os.remove(...)`) — excluded specifically for the
`{FileNotFoundError, FileExistsError}` + remove/unlink/rmtree combination;
`kill`/`killpg`/`truncate` remain unconditionally flagged (no equivalent
"already gone" idiom exists for them).

## search.py claim investigated and refuted
The tracker's claim that 5 sites in `download-proxy/src/merge_service/search.py`
need a BOB-199 exemption was independently re-verified as factually
incorrect: all 5 sites use `suppress(Exception)` (the BROAD form), never in
scope for this narrow+irreversible extension. `search.py` left completely
untouched (confirmed via `git diff --stat` returning empty).

## Independent verification (coordinator, from clean shell)
```
$ bash constitution/scripts/gates/cm_dangerous_combination_fail_closed_mutation_test.sh
[full 179-fixture suite, including L75-L79 BOB-199 fixtures]
✅ META PASS — ... META_EXIT=0
```
Confirmed the honestly-disclosed gap holds: L75/L77/L79's degraded
text-fallback mode assertion is "gate correctly PASSed on clean fixture"
(narrow+irreversible detection is AST-mode only, documented not silent).

Confirmed `search.py` genuinely untouched:
```
$ git diff --stat download-proxy/src/merge_service/search.py
(empty)
```

## Status
Fixed. Closed by coordinator after independent re-verification.
