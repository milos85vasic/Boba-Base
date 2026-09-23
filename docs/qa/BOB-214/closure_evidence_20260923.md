# BOB-214 closure evidence — 2026-09-23

## Defect
`DANGER_ROOTS` in `scripts/pre_build_verification.sh` never included the boba
repository root itself — top-level files (13 first-party shell scripts
including `start.sh`, the project's sole sanctioned container-control entry
point, plus `webui-bridge.py`, a live HTTP service on port 7188) were
invisible to the §11.4.252 fail-closed gate. The gate, unmodified, reports a
REAL hit when pointed directly at `webui-bridge.py`: a `except Exception:
return False` in `_is_root_liveness_probe()` silently swallows a malformed
`self.path` parse failure.

## Fix
1. `constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh`
   gained a `--max-depth <N>` flag (+ `DANGEROUS_COMBO_MAX_DEPTH` env
   override), non-negative-integer validated (§11.4.201 — real condition
   asserted, not silently coerced).
2. `scripts/pre_build_verification.sh`'s `DANGER_ROOTS` gained `.` (repo
   root), scanned at `--max-depth 1` so it covers ONLY files directly at
   root — no redundant re-walk of the already-listed subdirectories, and no
   descent into `constitution/`, `submodules/`, `node_modules/`, `.git/`
   (both the depth-1 bound and the gate's existing default exclude list keep
   it out).
3. `webui-bridge.py`'s `_is_root_liveness_probe()` genuine finding fixed: the
   bare `except Exception: return False` now logs the diagnosable anomaly
   before returning, mirroring the file's own existing
   `[WebUI-Bridge] Upload error: {e}` print-diagnostic convention.

## Independent verification (coordinator, from clean shell)

### Source spot-check
```
$ grep -n "max-depth\|MAX_DEPTH\|DANGEROUS_COMBO_MAX_DEPTH" constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh
[confirmed --max-depth flag + validation present]
$ git diff scripts/pre_build_verification.sh
[confirmed DANGER_ROOTS=(. download-proxy/src plugins scripts qBitTorrent-go frontend/src cmd/boba-ctl),
 max-depth 1 applied ONLY to "." entry via _dr_extra_args]
```

### Independently-reproduced RED (pre-fix) → GREEN (post-fix), from a fresh
copy of each historical revision (not trusting the subagent's own report):
```
$ git show HEAD:webui-bridge.py > pre/webui-bridge.py   # pre-fix, from git history
$ cp webui-bridge.py post/webui-bridge.py               # post-fix, working tree

$ bash constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh --root pre --max-depth 1 > pre_out.txt 2>&1
$ echo "PRE EXIT=$?"
PRE EXIT=1
# (line: "FAIL — silent default return (exception handler returns a trivial
#  literal with no re-raise/log) at .../pre/webui-bridge.py:550")

$ bash constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh --root post --max-depth 1 > post_out.txt 2>&1
$ echo "POST EXIT=$?"
POST EXIT=0
```
Note: an initial attempt piped both invocations through `| tail -15`, which
silently reported `tail`'s exit code (always 0) instead of the gate's —
caught and corrected before trusting the result; re-run without the pipe
gives the genuine PRE=1 / POST=0 split above.

### Live root-scan re-run against the real (fixed) tree
```
$ bash constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh --root . --max-depth 1 --quiet
✅ CM-DANGEROUS-COMBINATION-FAIL-CLOSED: PASS — no swallowed-exception, silent-default-return or credential-default-to-literal anti-patterns found (§11.4.252)
EXIT=0
```
Confirms no OTHER root-level first-party file introduces a new finding once
in scope.

### Advisory-only confirmed (invariant 39/56 does not newly block builds)
```
[39/56] CM-DANGEROUS-COMBINATION-FAIL-CLOSED: fail-open scan over first-party source (§11.4.252, ADVISORY)
```
Pre-existing framing (comment above the invariant, unmodified by this fix)
confirms widening scope only reports more, never newly blocks.

### Mutation suite (full re-run, independently)
```
✅ META OK:   L71 NEGATIVE CONTROL — a violation inside .git/ stays excluded by the default exclude list (BOB-214) — gate correctly PASSed on clean fixture
✅ META OK:   L72 NEGATIVE CONTROL — a nested-only violation is invisible at --max-depth 1 (BOB-214, intended narrowing) — gate correctly PASSed on clean fixture
✅ META OK:   L73 a ROOT-LEVEL violation is still caught at --max-depth 1 (BOB-214) — gate correctly FAILed on the mutation (rc=1)
✅ META OK:   L74 --max-depth with a non-numeric value exits 2 (argument error) (BOB-214)
✅ META PASS ... META_EXIT=0
```

## Status
Fixed. Closed by coordinator after independent re-verification — including a
from-scratch reproduction of the RED→GREEN cycle, distinct from the
subagent's own report.
