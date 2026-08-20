# BOB-117 closure evidence

**Item:** BOB-117 — rutracker login diag still uses forbidden §11.4.6 'likely' vocabulary + wrong error_type
**Type:** Bug · **Closed as:** Fixed (→ Fixed.md) per §11.4.33 type-aware closure vocabulary
**Closed:** 2026-08-20 · **Verified by:** controller, independently of the reporting subagent (§11.4.262)

## Why this was still Queued

The source fix landed in an earlier session but the tracker row was never reconciled — the DB
still read `Status=Queued` while the defect was fixed AND covered by a permanent guard. That is
tracker drift, not an open defect. Discovered during a §11.4.238 out-of-band sweep.

## Evidence chain (§11.4.146(D3): registry row → guard → verdict → class-matched evidence)

### 1. The fix is present in source

    $ grep -n 'upstream_captcha' download-proxy/src/merge_service/search.py | head -5
    1299:                        "error_type": "upstream_captcha",
    1353:                        "error_type": "upstream_captcha",
    1371:                        "error_type": "upstream_captcha",
    1674:                        "error_type": "upstream_captcha",

### 2. The forbidden hedged classification is gone

    $ grep -nE 'no session cookie.*likely' download-proxy/src/merge_service/search.py
    (no match — ABSENT)

### 3. Control needle — the absence above is real, not a blind grep (§11.4.201(7)(b))

    $ grep -c '_search_rutracker' download-proxy/src/merge_service/search.py
    3

A blind instrument and a genuinely-clean file both return a quiet zero. The needle proves the
search reaches this file, so the zero in step 2 is evidence rather than silence.

### 4. A permanent regression guard locks it in (§11.4.135)

    tests/unit/merge_service/test_search_deep_coverage.py:1030
        assert "likely" not in diag.get("error", "").lower()

The guard asserts on the emitted diagnostic, so re-introducing the hedge fails the suite.

### 5. Guard verdict: GREEN

    $ .venv/bin/python -m pytest tests/unit/merge_service/test_search_deep_coverage.py \
        -k "rutracker" -q --import-mode=importlib
    ...............                                                          [100%]
    15 passed, 72 deselected in 4.05s

## Honest boundary (§11.4.6)

A §11.4.115 RED demonstration (re-introduce the hedge, observe the guard FAIL) was NOT performed
here: `download-proxy/src/**` is owned by a concurrently-running agent (BOB-111), and mutating it
would violate §11.4.84 working-tree quiescence. The guard's assertion is structurally load-bearing
(it reads the emitted `error` string), but the RED flip is stated as NOT captured rather than
implied. Anyone re-running this can produce it once that file is quiescent.
