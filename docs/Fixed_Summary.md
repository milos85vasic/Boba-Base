# Fixed_Summary

Closed workable items (current_location = Fixed), regenerated from the SQLite single-source-of-truth (§11.4.53).

## Counts by Type × Status

| Type | Status | Count |
|---|---|---|
| Bug | Fixed (→ Fixed.md) | 11 |
| Feature | Implemented (→ Fixed.md) | 14 |
| Task | Completed (→ Fixed.md) | 6 |
| Task | Fixed (→ Fixed.md) | 2 |
| **TOTAL** | | **33** |

## Items

| ATM ID | Type | Status | Severity | Description |
|---|---|---|---|---|
| BOB-001 | Bug | Fixed (→ Fixed.md) | — | start.sh BSD-sed incompatibility aborted the boot |
| BOB-002 | Bug | Fixed (→ Fixed.md) | — | start.sh `podman unshare` incompatible with macOS remote podman |
| BOB-003 | Bug | Fixed (→ Fixed.md) | — | macOS tunnel port detection broken (ports never forwarded) |
| BOB-004 | Task | Completed (→ Fixed.md) | — | Private-tracker credentials stored securely + verified working |
| BOB-005 | Task | Fixed (→ Fixed.md) | — | Public-tracker plugins all raised an unhandled exception (systemic) |
| BOB-006 | Feature | Implemented (→ Fixed.md) | — | NNMClub username/password login wired |
| BOB-007 | Task | Completed (→ Fixed.md) | — | RuTor documented as public (no-auth) |
| BOB-011 | Feature | Implemented (→ Fixed.md) | — | DOCX export support added |
| BOB-012 | Task | Completed (→ Fixed.md) | — | Export-sync gate expanded to all docs (§11.4.65) |
| BOB-013 | Bug | Fixed (→ Fixed.md) | — | torrentkitty `_parse_size` reported 0 for every KB/MB/GB/TB size |
| BOB-014 | Bug | Fixed (→ Fixed.md) | — | Go `generateID()` collided under burst (UnixNano-only) |
| BOB-016 | Task | Fixed (→ Fixed.md) | — | Jackett plugin crashed (`Pool(0)`) when zero indexers are configured |
| BOB-017 | Bug | Fixed (→ Fixed.md) | — | NNMClub plugin self-heal crashed on invalid ICON |
| BOB-018 | Task | Completed (→ Fixed.md) | — | Jackett server image updated to latest |
| BOB-019 | Task | Completed (→ Fixed.md) | — | Jackett added as a reference submodule (latest release) |
| BOB-020 | Task | Completed (→ Fixed.md) | — | CodeGraph initialized + wired (§11.4.78/79/80) |
| BOB-021 | Bug | Fixed (→ Fixed.md) | — | env_loader flaky test: KEY2 leak across test ordering |
| BOB-022 | Bug | Fixed (→ Fixed.md) | — | AsyncMock warning in search deep-coverage tests |
| BOB-023 | Feature | Implemented (→ Fixed.md) | — | gamestorrents plugin deep-coverage tests |
| BOB-024 | Bug | Fixed (→ Fixed.md) | — | gamestorrents `_parse_size` B-substring bug fixed |
| BOB-025 | Feature | Implemented (→ Fixed.md) | — | eztv.py deep-coverage tests (54 tests) |
| BOB-026 | Feature | Implemented (→ Fixed.md) | — | piratebay.py deep-coverage tests + import-order bug documented |
| BOB-027 | Feature | Implemented (→ Fixed.md) | — | solidtorrents.py deep-coverage tests (37 tests) |
| BOB-028 | Feature | Implemented (→ Fixed.md) | — | limetorrents.py deep-coverage tests (52 tests) |
| BOB-029 | Feature | Implemented (→ Fixed.md) | — | torlock.py deep-coverage tests (55 tests) |
| BOB-030 | Feature | Implemented (→ Fixed.md) | — | nyaa.py deep-coverage tests + missing import re bug documented |
| BOB-031 | Feature | Implemented (→ Fixed.md) | — | kickass.py deep-coverage tests + comma-size gap documented |
| BOB-032 | Feature | Implemented (→ Fixed.md) | — | anilibra.py deep-coverage tests (49 tests) |
| BOB-033 | Bug | Fixed (→ Fixed.md) | — | kickass.py crash guards added (BOB-015 defense-in-depth) |
| BOB-034 | Feature | Implemented (→ Fixed.md) | — | torrentgalaxy.py + yts.py deeper coverage (80 new tests) |
