# Fixed_Summary

Closed workable items (current_location = Fixed), regenerated from the SQLite single-source-of-truth (§11.4.53).

## Counts by Type × Status

| Type | Status | Count |
|---|---|---|
| Bug | Fixed (→ Fixed.md) | 6 |
| Feature | Implemented (→ Fixed.md) | 2 |
| Task | Completed (→ Fixed.md) | 7 |
| Task | Fixed (→ Fixed.md) | 2 |
| **TOTAL** | | **17** |

## Items

| ATM ID | Type | Status | Severity | Description |
|---|---|---|---|---|
| BOB-001 | Bug | Fixed (→ Fixed.md) | — | start.sh BSD-sed incompatibility aborted the boot |
| BOB-002 | Bug | Fixed (→ Fixed.md) | — | start.sh `podman unshare` incompatible with macOS remote podman |
| BOB-003 | Bug | Fixed (→ Fixed.md) | — | macOS tunnel port detection broken (ports never forwarded) |
| BOB-004 | Task | Completed (→ Fixed.md) | — | Private-tracker credentials stored securely + verified working |
| BOB-005 | Task | Fixed (→ Fixed.md) | — | Public-tracker plugins all raised an unhandled exception (systemic) |
| BOB-006 | Feature | Implemented (→ Fixed.md) | — | NNMClub username/password login wired — NNMClub now uses the operator's `NNMCLUB_USERNAME`/`NNMCLUB_PASSWORD` (in . |
| BOB-007 | Task | Completed (→ Fixed.md) | — | RuTor documented as public (no-auth) — RuTor is a public tracker with no login endpoint; `RUTOR_USERNAME/PASSWORD` are |
| BOB-010 | Task | Completed (→ Fixed.md) | — | Workable-items SQLite DB integrated + pre-build gate wired (§11.4.93/§11.4.95) |
| BOB-011 | Feature | Implemented (→ Fixed.md) | — | DOCX export support added — `generate_markdown_exports. |
| BOB-012 | Task | Completed (→ Fixed.md) | — | Export-sync gate expanded to all docs (§11.4.65) |
| BOB-013 | Bug | Fixed (→ Fixed.md) | — | torrentkitty `_parse_size` reported 0 for every KB/MB/GB/TB size |
| BOB-014 | Bug | Fixed (→ Fixed.md) | — | Go `generateID()` collided under burst (UnixNano-only) |
| BOB-016 | Task | Fixed (→ Fixed.md) | — | Jackett plugin crashed (`Pool(0)`) when zero indexers are configured |
| BOB-017 | Bug | Fixed (→ Fixed.md) | — | NNMClub plugin self-heal crashed on invalid ICON |
| BOB-018 | Task | Completed (→ Fixed.md) | — | Jackett server image updated to latest |
| BOB-019 | Task | Completed (→ Fixed.md) | — | Jackett added as a reference submodule (latest release) |
| BOB-020 | Task | Completed (→ Fixed.md) | — | CodeGraph initialized + wired (§11.4.78/79/80) |
