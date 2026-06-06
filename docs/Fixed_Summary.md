# Fixed Summary — Closed Items

**Revision:** 3
**Last modified:** 2026-06-06T18:30:00Z
**Ticket prefix:** `BOB`

Closed workable items only (full detail in [`Fixed.md`](Fixed.md)). Most-recent first.

| BOB ID | Status | Type | Commit | One-line description |
|--------|--------|------|--------|----------------------|
| BOB-005 | Fixed | Bug | a8916c0 | Public-tracker search restored: framework modules at nova3 root + PySocks (49→909 results, 0→14 trackers) |
| BOB-016 | Fixed | Bug | (pending) | Jackett plugin no longer crashes with Pool(0) when zero indexers are configured |
| BOB-001 | Fixed | Bug | c5cbd40 | Portable sed_inplace replaces GNU sed -i that aborted the macOS boot |
| BOB-002 | Fixed | Bug | c5cbd40 | podman unshare guarded so plugin install no longer aborts on macOS |
| BOB-003 | Fixed | Bug | c5cbd40 | macOS tunnel now detects the real podman SSH port and forwards container ports |
| BOB-004 | Completed | Task | (.env) | Tracker credentials stored 0600/gitignored and proven working (49 live IPTorrents results) |
| BOB-013 | Fixed | Bug | 14bc5c4 | torrentkitty size parsing fixed so KB/MB/GB/TB no longer collapse to zero |
| BOB-014 | Fixed | Bug | d46ea57 | Go generateID uses an atomic counter to avoid same-nanosecond collisions |
