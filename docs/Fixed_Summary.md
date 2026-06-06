# Fixed Summary — Closed Items

**Revision:** 4
**Last modified:** 2026-06-06T19:00:00Z
**Ticket prefix:** `BOB`

Closed workable items only (full detail in [`Fixed.md`](Fixed.md)). Most-recent first.

| BOB ID | Status | Type | Commit | One-line description |
|--------|--------|------|--------|----------------------|
| BOB-005 | Fixed | Bug | a8916c0 | Public-tracker search restored: framework modules at nova3 root + PySocks (49→909 results, 0→14 trackers) |
| BOB-016 | Fixed | Bug | fa6fb4f | Jackett plugin no longer crashes with Pool(0) when zero indexers are configured |
| BOB-006 | Implemented | Feature | a94f269 | NNMClub username/password→cookie login wired so the provided creds are used |
| BOB-017 | Fixed | Bug | a94f269 | NNMClub plugin self-heal no longer crashes on the invalid embedded ICON |
| BOB-007 | Completed | Task | 2d80f03 | RuTor documented as a public no-auth tracker; its .env creds are not consumed |
| BOB-011 | Implemented | Feature | 2d80f03 | DOCX export added to the markdown export pipeline (pandoc), with a test |
| BOB-018 | Completed | Task | 2d80f03 | Jackett server image pulled to latest; plugin confirmed at upstream parity |
| BOB-001 | Fixed | Bug | c5cbd40 | Portable sed_inplace replaces GNU sed -i that aborted the macOS boot |
| BOB-002 | Fixed | Bug | c5cbd40 | podman unshare guarded so plugin install no longer aborts on macOS |
| BOB-003 | Fixed | Bug | c5cbd40 | macOS tunnel now detects the real podman SSH port and forwards container ports |
| BOB-004 | Completed | Task | (.env) | Tracker credentials stored 0600/gitignored and proven working (49 live IPTorrents results) |
| BOB-013 | Fixed | Bug | 14bc5c4 | torrentkitty size parsing fixed so KB/MB/GB/TB no longer collapse to zero |
| BOB-014 | Fixed | Bug | d46ea57 | Go generateID uses an atomic counter to avoid same-nanosecond collisions |
