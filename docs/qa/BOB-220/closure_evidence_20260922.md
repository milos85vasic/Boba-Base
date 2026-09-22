# BOB-220 closure evidence — 2026-09-22

## Fix

Root-caused: `/usr/bin/chmod` on this host is uutils-coreutils (a Rust
reimplementation), not GNU. Measured: `chmod 755 dir` AND `chmod 0755 dir`
(both under 5 characters) LEAVE a directory's setgid bit set; only the
fully-zero-padded 5-character `chmod 00755 dir` form (or explicit `g-s`)
actually clears it. Files are unaffected either way (the kernel already
clears setuid/setgid on chown(2) before this chmod runs).

`scripts/ownership_repair.sh` (`flush_batch()`): changed
`_mode="$(printf '%o' "${_mode}")"` to `_mode="$(printf '%05o' "${_mode}")"`,
with an in-source comment recording the measured chmod quirk. BOB-207's
uid-only-selection fix does NOT make this moot — a foreign-uid-owned setgid
directory is still selected for repair and still hits this code path.

## RED/GREEN evidence (real end-to-end repair run, real foreign uid via `podman unshare chown 1:1`)

Pre-fix: mode stays `2755` after repair. Post-fix: mode becomes `0755`.

## Independently re-verified this session

```
$ bash tests/unit/test_ownership_repair_setgid_strip.sh
  PASS: control: the pre-fix shape (bare '%o') reproduces the reported no-op — 2755 survives under this identical harness, proving Case 1 is discriminating
RESULT: 2 passed, 0 failed, 0 skipped
```

Plus the full `tests/unit/test_ownership_repair.sh` (146/146).

See `docs/qa/BOB-208/closure_evidence_20260922.md` for the combined
`git diff --stat`.
