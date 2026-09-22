# BOB-149 closure evidence — 2026-09-22

## Finding

BOB-149 ("Managed-plugin count diverges 43/42/48 across constitution,
CLAUDE.md and the README badge") is already resolved in the current working
tree — fixed by prior commits `60729c9` and `9e443d0` ("fix(constitution,docs):
... refresh stale README/TESTING badges") before this session started. The
tracker entry (`docs/Issues.md`, Status: Queued) is stale relative to the
codebase.

Independently re-verified this session by a dedicated subagent. Zero file
edits were made (`git diff --stat` on every relevant file is empty).

## Verification

Real count, control-needle verified against `install-plugin.sh`'s
`PLUGINS=()` array (extraction validated by confirming known members
`"academictorrents"`, `"rutracker"`, `"yts"` all present before trusting the
count): **43 entries**.

Current state of the three previously-divergent locations:
- `.specify/memory/constitution.md:632` — "every managed plugin (43" — already correct.
- `CLAUDE.md:265` — "**43 search-plugin engines** ... <!-- CM-PLUGIN-COUNT: curated -->" — already correct. (The "42" the bug cites survives only as historical narrative at CLAUDE.md:260 documenting the bug itself, not a live claim.)
- `README.md:30` — badge reads `plugins-43-blue` (not 48); README.md:224 prose says "the 43 plugin engines" — already correct.

Remaining hits for the old wrong numbers ("42 managed plugin", "plugins-48")
are all intentional: the gate scripts' own "why this exists" commentary
(`scripts/pre_build/check_cm_plugin_count.sh`), the constitution's historical
Sync Impact Report entry describing drift as of when it was authored, the bug
report itself (`docs/Issues.md`), and golden-bad test fixtures that
deliberately embed the wrong numbers to prove the gates catch them
(`tests/unit/test_compute_badges_carrier_match.sh`,
`tests/pre_build/test_check_cm_plugin_count.sh`). None of these are live,
currently-wrong documentation claims.

## Verification commands run (both PASS, exit 0)

```
$ bash scripts/pre_build/check_cm_plugin_count.sh -v
  derived (control-needle proven):
    curated    43   (install-plugin.sh PLUGINS=() — the canonical managed roster)
    bootstrap  12   (setup.sh PLUGINS=() — one-time-setup subset)
    engines    43   (distinct engine modules on disk)
    toplevel   35   (plugins/*.py — engines PLUS utility modules)
    recursive  68   (plugins/**/*.py — also counts per-dir variants)

    ok  CLAUDE.md: curated = 43
    ok  CLAUDE.md: engines = 43
    ok  CLAUDE.md: bootstrap = 12
    ok  CLAUDE.md: toplevel = 35
    ok  CLAUDE.md: recursive = 68
    ok  docs/features/Status.md: curated = 43
    ok  docs/features/Status.md: engines = 43
    ok  docs/features/Status.md: toplevel = 35
PASS: CM-PLUGIN-COUNT — 8 documented count(s) match their derivation
EXIT: 0

$ bash scripts/compute-badges.sh --check
compute-badges.sh --check: README badges are in sync with live counts
EXIT: 0
```

## git diff --stat

```
$ git diff --stat README.md CLAUDE.md .specify/memory/constitution.md docs/features/Status.md
(empty — no output, zero changes)
```
