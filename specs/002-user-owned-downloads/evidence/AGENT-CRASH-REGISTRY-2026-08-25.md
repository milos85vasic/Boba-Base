# Agent crash registry — weekly-quota kill, 2026-08-25

**Revision:** 1
**Last modified:** 2026-08-25T17:43:02Z

§11.4.147(e) — API-quota / rate-limit exhaustion is a FIRST-CLASS CRASH CLASS.
These three agents are `crashed`, **not** `complete`. Their work is OWED.
The §11.4.126 / §11.4.87 loop done-condition MUST NOT read satisfied while any
row below is non-`complete`.

## The real limit signal (§11.4.196(B), captured verbatim, never paraphrased)

```
Agent terminated early due to an API error: You've hit your weekly limit
· resets Aug 25, 5pm (Europe/Belgrade) · progress saved
```

**Reason-class: `weekly`** per the §11.4.196(B) closed set `{session | weekly | subscription}`.

Operational-again epoch: **2026-08-25 17:00 Europe/Belgrade**.
Clock at registry write: **2026-08-25 19:43:02 CEST / 17:43:02 UTC** — the stated
reset had ALREADY PASSED when this was written.

## A correction to the harness's own claim (§11.4.6)

The failure notice says `progress saved` and names an output file per agent.
**Those files do not exist.** The session tasks directory was recreated at 19:43
on resume and contains one unrelated file:

```
/tmp/.../7efc93d6-.../tasks/
  b9zpgf88o.output      (34 bytes, unrelated)
```

`find ... -name '*.output' -newermt '-6 hours'` returned **nothing**. So the
partial work is NOT recoverable from the advertised paths. What survives is
(a) each agent's last emitted line, recorded below, and (b) the agent transcript,
which is what `SendMessage`-resume actually replays. Trusting the "progress
saved" string without probing the path would have been the §11.4.201(6)
false-null — a comfortable claim with no artifact behind it.

## Registry

| Agent id | Purpose | State | Last emitted line (the only surviving progress marker) |
|---|---|---|---|
| `ae7d2d6fd0441814c` | BOB-169 export-charset review, round 4 | `crashed` → `respawned` 19:43 → **`complete`** 19:45 (GO) | "Round 4. Small scope — verifying the reflow and re-deriving the comment-only claim with my own instrument." |
| `a38255451c12d03e1` | BOB-174 round-2 remediation | `crashed` → `respawned` 19:50 | "Baselines: **33 / 73 / 261**. Now the mutation harness — every mutation re-run against the current file, in two scopes." |
| `ad1ca8f53c334d151` | BOB-164 F1 contrast-regression fix | `crashed` → `respawned` 19:50 | "Now the `styles.scss` fallback values, which must stay in sync with the token set." |

## Probe outcome — the quota window HAD reopened (measured, not assumed)

`ae7d2d6f` was resumed at 19:43 as the cheap discriminator and **ran to
completion**, returning a round-4 GO. That is the evidence the window
reopened; the other two were respawned only after it. Had the probe failed,
one dispatch would have been spent learning that fact instead of three.

Every respawn message carried the harness-correction above, instructing the
agent to RE-DERIVE its pre-kill measurements rather than assume they survived
— and stating that a differing re-measurement is itself a finding.

## Respawn discipline (§11.4.267 converge-on-evidence)

The three were NOT respawned simultaneously. The smallest-scope agent
(`ae7d2d6f`, a comment-reflow verification) was resumed FIRST as a cheap
discriminator on whether the quota window has genuinely reopened. The other two
are held until that probe reports. Respawning all three against an unverified
quota state would burn three dispatches to learn one fact.

No alias rebind was available: §11.4.196(A)/(C) native-first rebinding operates
at the multitrack-ruler layer; subagents dispatched from this session inherit
this session's auth, so the conductor cannot rebind them from inside the session.
That is a harness boundary, stated honestly, not a compliance claim.

## Work owed on respawn

**BOB-174 round-2** — MINOR-1 (`mkstemp(dir=)` unpinned: in-container `/config` is
a bind-mount while `/tmp` is overlay, so `os.replace` would raise `EXDEV` on every
hook write, and pytest's `tmp_path` is structurally blind to it), MINOR-2 (fsync
unpinned), MINOR-3 ("14 call sites" is 8), MINOR-4 (0644→0600 enumeration gap),
IMPORTANT-2 (evidence says "28 tests", actual 31; the stale-exports bullet is now
false). Baselines measured before the kill: **33 / 73 / 261**.

**BOB-164 F1** — the fix lightened `--color-text-secondary`, which
`dashboard.component.scss:545` uses as a *background* (`&.unknown { background:
var(--color-text-secondary); color: #ccc; }`), so a disabled hook's "No" renders
at **1.09:1** on darcula/dark. Plus F2 (66 palette×pair combos below 4.5:1),
F4 (scanner blind to axe `incomplete`), F5 (RED/GREEN measured on different
oracle versions), F6/F7/F8. Was mid-`styles.scss` fallback-value sync.
