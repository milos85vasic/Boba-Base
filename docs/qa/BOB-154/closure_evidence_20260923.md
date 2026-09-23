# BOB-154 closure evidence — 2026-09-23 (staleness-corrected closure)

## Finding
Real fix commit `4768b36 "fix(BOB-153,BOB-154): the Go profile now builds,
and the test stack is not the stack we ship"` already landed — tracker
status never advanced.

## Independent verification (coordinator, from clean shell, 2026-09-23)
```
$ .venv/bin/pip show starlette | grep Version
Version: 1.6.0
$ podman exec qbittorrent-proxy pip show starlette | grep Version
Version: 1.6.0
```
Host venv and production container now run the IDENTICAL starlette
version (1.6.0 == 1.6.0).

```
$ bash scripts/pre_build/check_cm_runtime_deps_parity.sh
compared: 42 container package(s) against 146 host package(s); host-only dev tooling ignored by design
control needle: seen (findings 0 -> 1)
PASS: CM-RUNTIME-DEPS-PARITY — test stack and production agree (42 packages + interpreter; 0 declared divergence(s))
```
Live gate confirms full parity, control-needle-proven (not a blind zero).

## Status
Fixed. Closed by coordinator after independent re-verification.
