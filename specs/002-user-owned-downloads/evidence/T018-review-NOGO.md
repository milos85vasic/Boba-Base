# T018 independent review — NO-GO, and a correction to my own evidence

**Reviewer**: independent agent on the Fable model · **Date**: 2026-08-21
**Verdict**: **NO-GO** — 2 IMPORTANT, 3 MINOR, 1 NIT

## Honest note on the review substrate (§11.4.6)

The review model pin was honoured: it ran on **Fable**. The effort pin was **not** settable
— the Agent-tool dispatch path exposes a `model` parameter but **no `effort` parameter**, so
the §11.4.182 label reads `(T11/002-user-owned-downloads - claude4 - fable - ?)` with an
honest `?`. Claiming `xhigh` would have been a bluff about the tooling. The Workflow tool's
`agent()` does accept `effort`; a re-review through that path remains available and is not
claimed as done.

## IMPORTANT-1 — I published an evidence claim that does not reproduce

This is the finding that matters most, and it is against **my own work**.

`T033-precondition-and-backlog.md` pastes, as captured proof:

```
mode=600 owner=milosvasic(1000)  config/boba.db
BACKUP OK (81920 bytes)
mode still 600
```

The reviewer re-checked and found:

```
$ stat -c '%a %u:%g %n' config/boba.db
666 1000:1000 config/boba.db      # world-READABLE and world-WRITABLE
```

I re-verified independently. **The reviewer is right**: 666, and all **262 of 262** items
under `config/` were world-writable.

### Was the original measurement false?

No — and that distinction is the actual lesson. `stat` really did return 600 when I ran it.
What was wrong was the **claim I attached to it**. "mode still 600" reads as a durable
property; it was a **snapshot of a value that changes at runtime**.

The mechanism is `start.sh:363`, inside `create_directories()`:

```bash
podman unshare chmod -R a+rw config/ 2>/dev/null || true
```

That runs on **every** start — including the `./start.sh --recreate` this feature's own T014
mandates. So between my measurement and the review, a start re-widened the tree.

### Why this is a finding against THIS change set, not just a pre-existing bug

1. The feature brings `boba.db` into a declared "protected" scope and ships FR-013/FR-015
   plus pasted evidence asserting the credential store is and stays 600. On the live system
   it was 666 — a **worse access posture than the ownership defect it replaced**. The
   ownership defect made the file unreadable to its owner; this made it writable by anyone.
2. **Nothing the feature ships enforces the invariant.** The precondition checks OWNERSHIP
   only, never mode. The gate never inspects mode. And `preserve_mode: true` in the repair
   restores the file's *current* bits after chown — so it would have **locked in 666**,
   not restored 600. The invariant existed in prose and in a unit fixture, and nowhere that
   touches the real system.

Not BLOCKING only because the DB is AES-256-GCM encrypted and `.env` (holding the master
key) is correctly 600 — so this is not immediate key disclosure. It is still a
world-writable credential store.

### The deeper finding: the workaround outlived its cause

`git log -S` traces that chmod to commit **00f1fa6 (2026-04-14)**, subject line *"Fix
start.sh config/ permissions for podman unshare"*. It was added as a **workaround for
exactly the defect feature 002 fixes**: container writes landed at host uid 100999, the
operator could not access `config/`, so everything was blanket-widened.

With `PUID=0` the operator now OWNS every file under `config/`, so the widening buys
**nothing** and costs a world-writable credential store. Fixing a root cause without
retiring its workarounds leaves the workaround as pure liability — it was compensating for a
problem that no longer exists.

### Action taken and in flight

- Live file secured immediately: `chmod 600 config/boba.db`, verified, and `boba-jackett`
  confirmed still healthy at 600 (it runs as container uid 0 = host uid 1000 = the owner).
- A one-off chmod is NOT the fix — the next start would re-widen it. The fix must live in
  the path that widens. Handed to the agent that currently owns `start.sh`, with the
  requirement that it prove the result with a real `--recreate` and a post-run `stat`, and
  add a regression check so it cannot silently return.

## IMPORTANT-2 — an unconditional claim that is only conditionally true

`docker-compose.yml` asserts, above each `PUID=0`: *"This grants NO host privilege: 'root'
inside a rootless container IS the unprivileged host user."*

True under **rootless** podman. **False** under rootful docker with no userns-remap, where
container uid 0 is real host root — under which `PUID=0` would write to the bind-mounted
`config/` and the download tree as host uid 0, strictly worse than the original `PUID=1000`.

And rootlessness is **not enforced**: `start.sh` falls back to `CONTAINER_RUNTIME="docker"`
with no rootless assertion, and the ownership gate checks that `PUID=0` is present while
having zero knowledge of the runtime. The comment states a conditional as an unconditional
fact, and nothing at the seam verifies the condition that makes it true. Remediation in
flight.

## MINOR-1 — the gate is blind to locally-built linuxserver-derived images (PROVEN)

The gate derives "linuxserver" from the `image:` key, and its header claims this covers "a
linuxserver service added LATER". A service built from a Dockerfile with
`FROM lscr.io/linuxserver/...` has **no** `image:` key. The reviewer constructed that case
and the gate **PASSED it undetected** — a `PUID=1000` there would map to host 101910 and go
unreported. The gate's self-described completeness overstates its coverage. Remediation in
flight.

## MINOR-2 — the gate's own header states it is unwired, while it is wired

`check_cm_ownership_invariants.sh` still carries a `REGISTRATION STATUS` block saying "NOT
YET WIRED ... §11.4.196(F) configured-vs-in-use gap". It runs as invariant `[33/44]`.
Doc-vs-code drift inside a gate whose entire purpose is honesty. Remediation in flight.

## MINOR-3 — the repair's scope fence has no test

`ownership_repair.sh` fences scope with `chown -h` and non-following `find`. Reading the
code, that is correct. But the suite has **no symlink case at all**. For a destructive tool
whose most dangerous property is out-of-scope reach, that property has no paired test
proving it — one refactor away from being untrue. Remediation in flight.

## NIT-1 — invariant 33 prints after 44

Cosmetic ordering only; slot 33 verified genuinely free, and the denominator mismatch is
already tracked as BOB-150. No action.

## What the reviewer tried to break and could not

Recorded because a GO is only credible when you know what was attacked:

- **The RED-test reconciliation — the highest-risk call — was judged LEGITIMATE.** The
  original hardcoded `PUID=1000` asserted an *unfixable image property*, so it would have
  stayed red forever including after the fix (the §11.4.201(1) refuse-on-a-healthy-system
  shape). Reading the value from compose makes it track the configuration this feature
  changes. Textbook §11.4.120 reconcile-not-fake-pass.
- **The gate meta-test genuinely has teeth**: 19/19 re-run; the revert mutation FAILs naming
  both services; every golden-FALSE guard (carrier comments, `acme/mylinuxserverfork`
  substring, `reg.example:5000/linuxserver/...`) correctly PASSes; the real compose is
  byte-identical after the run.
- **Two evidence claims spot-checked and reproduced exactly**: compose `sha256 ef8e810a…`
  to the full digest, and 0 wrongly-owned across the 6459-item download root.
- **The repair's destructive-tool safety** read clean: NUL-terminated `find` handles tabs and
  newlines in paths, `chown -h --` guards dash-prefixed paths, marker written only on full
  success with traps that exit without it, record-before-mutate. No scope escape found by
  reading — which is exactly why MINOR-3 (no test) matters.

## The gate did its job

This is the argument for the review step existing. Every finding above was in a change set
that passed its own tests, its own gate, and its author's review — and a world-writable
credential store was live on the operator's machine the whole time.
