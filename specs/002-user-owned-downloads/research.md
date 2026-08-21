# Phase 0 Research: Downloads Owned by the Person Who Started the System

**Feature**: 002-user-owned-downloads
**Date**: 2026-08-21
**Method**: every finding below was produced by running the command on this host and
reading the result. Nothing here is inferred from documentation alone.

---

## R1. Root cause — why files are not owned by the operator

**Decision**: The cause is the rootless user-namespace mapping combined with
`PUID=1000`, NOT the lifecycle manager.

**Evidence (measured 2026-08-21)**:

```
host user            : uid=1000(milosvasic) gid=1000
/etc/subuid          : milosvasic:100000:65536
compose PUID/PGID    : 1000 / 1000   (all services)
userns_mode          : absent from docker-compose.yml (0 occurrences)
```

Under rootless Podman the container's uid 0 maps to the host uid 1000, and container
uid *N* maps to `100000 + N - 1`. So `PUID=1000` places the application at host uid
**100999** — an identity with no host account, which is why it renders as
`UNKNOWN:UNKNOWN`.

Reproduced synthetically against the real image:

```
$ podman run --rm -e PUID=1000 -v $T:/downloads:Z \
    lscr.io/linuxserver/qbittorrent:latest \
    sh -c 'id abc; s6-setuidgid abc touch /downloads/as_app'
uid=1000(abc) gid=1000(users)
$ stat -c '%u (%U)' $T/as_app
100999 (UNKNOWN)          <-- the reported defect, reproduced
```

**Rationale**: This is the §11.4.199 exact-reproduction requirement — the synthetic
repro drives the same image, the same `PUID`, and the same s6 user the product uses,
and lands on the same uid the live system shows.

**A measurement error worth recording (§11.4.6)**: an earlier attempt used
`sh -c 'touch ...'` directly. That runs as the container's **root entrypoint**, not as
the `PUID` user, so both the test and its control produced host uid 1000 and the
experiment could not distinguish anything. It was discarded and re-run through
`s6-setuidgid abc`. Reporting the first result would have concluded, wrongly, that no
defect existed.

**Alternatives considered**: that the lifecycle manager was responsible — refuted, see
R2.

---

## R2. The requested mechanism does not cause the requested outcome

**Decision**: Session-scoped service management is a genuine improvement but is
**orthogonal** to file ownership. It is planned as US3 (P3), not as the fix.

**Evidence**:

- Rootless Podman already runs entirely as the operator's own account. Starting it
  from a session-scoped unit does not alter the user-namespace mapping.
- Session-scoped units for this system **already exist** and are **inactive**:
  `boba-stack.service`, `boba.target`, `boba-webui-bridge.service`,
  `boba-resource-pressure-check.{service,timer}` — all symlinks into
  `scripts/systemd/user/`.
- `start.sh` references systemd **0** times, so the documented start path and those
  units are entirely disconnected today.

**Rationale**: Adopting the mechanism alone would have left the defect exactly as it
is. Saying so is the load-bearing content of the spec.

---

## R3. Route A — map the container user to the host user (`userns_mode: keep-id`)

> **SUPERSEDED IN PART — see [R9](#r9-correction--route-a-was-wrong-it-supersedes-r3s-route-a-verdict-and-r5s-route-table).** The "VIABLE for `download-proxy`,
> `qbittorrent-proxy-go`, `boba-jackett`" verdict below was WRONG. It generalised an
> `alpine` result to three services that were never probed individually. The
> "BLOCKED for `qbittorrent` and `jackett`" half stands and was re-confirmed.

**Decision**: **VIABLE for `download-proxy`, `qbittorrent-proxy-go`, `boba-jackett`.
BLOCKED for `qbittorrent` and `jackett`.**

**Evidence**:

```
$ podman run --rm --userns=keep-id -v $T:/out:Z alpine sh -c 'id -u; touch /out/keepid'
1000
$ stat -c '%u (%U)' $T/keepid
1000 (milosvasic)                          <-- works

$ timeout 120 podman run --rm --userns=keep-id \
    lscr.io/linuxserver/qbittorrent:latest sh -c 'echo REACHED_ENTRYPOINT'
Terminated                                  <-- hangs, no output, twice
$ timeout 120 podman run --rm \
    lscr.io/linuxserver/qbittorrent:latest sh -c 'id -u; echo STARTED_OK'
0
STARTED_OK                                  <-- control: starts fine without keep-id
```

The linuxserver images boot as root to run their s6 init before dropping to `PUID`.
Under `keep-id` the container has no usable root, and the image hangs rather than
failing fast.

**Toolchain support confirmed**: `podman-compose` 1.5.0 translates the compose key:

```
/usr/lib/python3/site-packages/podman_compose.py:1208
    userns_mode = cnt.get("userns_mode")
    if userns_mode is not None:
        podman_args.extend(["--userns", userns_mode])
```

**A false null caught by a control needle (§11.4.201(6))**: the first check grepped
`$(command -v podman-compose)` and found **0** `userns` references — which would have
concluded "not supported". The same grep also found **0** `network_mode` references,
and `network_mode` demonstrably works, so the instrument was blind: that path is a
thin entrypoint, not the module. Re-run against the real module it returns 8
`network_mode` and 3 `userns` references. The needle is what turned a wrong "no" into
the right "yes".

---

## R4. Route B — let the application write as container-root (`PUID=0`)

**Decision**: **VIABLE for the linuxserver services, and it is the route for them.**

**Evidence**:

```
$ podman run --rm -e PUID=0 -e PGID=0 -v $T:/downloads:Z \
    lscr.io/linuxserver/qbittorrent:latest \
    sh -c 'id abc; s6-setuidgid abc touch /downloads/b_app'
uid=0(root) gid=0(root) groups=0(root),1000(users)
$ stat -c '%u (%U)' $T/b_app
1000 (milosvasic)                          <-- works
```

Setting `PUID=0` makes the s6 application user *become* uid 0, which the rootless
mapping resolves to the host operator. The image starts normally — no hang.

**Rationale**: "Root inside a rootless container" is not host root. The container's
uid 0 **is** the unprivileged host user 1000; it holds no host privilege it did not
already have. The security posture is unchanged, and §11.4.161 rootless operation is
preserved.

**Alternatives considered**:

- *Shared group + setgid + permissive umask*: leaves files owned by 100999 with group
  access. Does not satisfy FR-001/FR-002 (ownership), only approximates FR-003.
  Rejected.
- *Post-hoc chown on a timer*: is the current manual workaround, automated. Leaves a
  window where content is unmanageable, which FR-004d rejects. Rejected.
- *`podman unshare chown`*: correct for one-off repair, wrong as a steady state — it
  fixes files after the fact rather than preventing the defect. Retained as an
  implementation option for the FR-004 repair only.

---

## R5. Mixed-route consequence

> **SUPERSEDED IN PART — see [R9](#r9-correction--route-a-was-wrong-it-supersedes-r3s-route-a-verdict-and-r5s-route-table).** The three Route-A rows below were
> refuted by measurement at implementation time: those services already run as
> container uid 0 and already write host-uid-1000 files, so `keep-id` was both
> unnecessary and actively harmful. The two Route-B rows stand.

**Decision**: The fix is **per-service**, not global. Two services take Route B, three
take Route A.

| Service | Image | Route | Reason |
|---|---|---|---|
| `qbittorrent` | linuxserver | **B** (`PUID=0`) | keep-id hangs the image (R3) |
| `jackett` | linuxserver | **B** (`PUID=0`) | same |
| `download-proxy` | python:alpine | **A** (`keep-id`) | no s6, no root requirement |
| `qbittorrent-proxy-go` | built Go | **A** (`keep-id`) | same |
| `boba-jackett` | built Go | **A** (`keep-id`) | writes `config/boba.db` (FR-012) |

FR-016 requires every service that writes in-scope locations to be corrected; this
table is the completeness map for that requirement, including the optional-profile
service.

**Honest boundary (§11.4.6)**: Route A is confirmed for `alpine` and asserted for the
two Go images by the same mechanism. It is **not yet demonstrated** on the built Go
images specifically, because they are `scratch`/minimal builds whose behaviour under
`keep-id` was not exercised in this pass. Tasks MUST verify each service
individually rather than generalising from the alpine result.

---

## R6. Scope is wider than downloads

**Decision**: In-scope locations are the download tree **and** container-written
project paths.

**Evidence**:

```
config/            : 51 items owned by uid 100999
config/boba.db     : UNKNOWN:UNKNOWN, mode 600
tmp/               : uid 1000 (already correct)
download root      : uid 100999 (the root itself)
downloads content  : 6458 items at uid 1000, 1 at 100999
```

`docs/BOBA_DATABASE.md` §3 instructs the operator to back up `boba.db` and `.env`
together and warns that master-key loss is unrecoverable. At mode 600 under an
unresolvable owner, **that documented procedure cannot be performed**. This is what
widened the spec's scope (FR-012/013).

The 6458-vs-1 ratio is consistent with the operator reassigning ownership by hand
after each download — the reported toil, visible in the filesystem.

---

## R7. Repair semantics

**Decision**: blocking, resumable, once-successfully, unbounded — per the clarify
session.

- Marker written only after a fully successful pass, so an interrupted run resumes
  (FR-004a).
- Blocks all download-writing services until complete (FR-004d), which removes the
  repair-vs-active-download concurrency question by construction (FR-004g).
- No self-imposed time limit (FR-004f); progress output (FR-004e) is what keeps a long
  run distinguishable from a hang.
- Records what it changed before changing it (FR-004b) — the mitigation that makes the
  operator's accepted automatic-repair risk recoverable.

**Open for implementation (deferred from clarify, by design)**: the change-record's
location and format. Constraint: it must be readable by the operator and must not live
only inside a container. `docs/qa/` is for QA evidence and is the wrong home for an
operational log.

---

## R8. Constraints inherited from the project constitution

- **§11.4.161 / Principle IV**: rootless only. Both routes preserve this; neither adds
  a privileged or system-wide service.
- **Principle I**: `docker-compose.yml` is the contract — a change here MUST update
  the lifecycle scripts in the same change, and the health check must cover every
  served port (already enforced by invariant 44).
- **Principle XIII / §CONST-033**: no host power-state transitions; test resource use
  bounded to 30-40%.
- **Principle XII / §11.4.115**: the RED test must fail against the pre-fix state.
  R1's synthetic reproduction is exactly that RED and is already written.
- **§11.4.235**: applying a `docker-compose.yml` change requires `./start.sh
  --recreate`, not `--reload-python`. A restart does not re-read the compose file —
  this cost a false "fixed" earlier in the same session and MUST be in the tasks.

## R9. CORRECTION — Route A was wrong; it supersedes R3's Route-A verdict and R5's route table

**Status**: This section **supersedes** the Route-A half of [R3](#r3-route-a--map-the-container-user-to-the-host-user-userns_mode-keep-id)
and the three Route-A rows of [R5](#r5-mixed-route-consequence). R3 and R5 are left in
place unedited on purpose — what was believed, and why it was believed, is the whole
value of this record. Read them, then read this.

**Recorded**: 2026-08-21, at implementation time, from measurement on the live stack.

### What R3/R5 planned

A mixed route: Route B (`PUID=0`) for the two linuxserver.io services (`qbittorrent`,
`jackett`), and Route A (`userns_mode: keep-id`) for the other three
(`download-proxy`, `qbittorrent-proxy-go`, `boba-jackett`).

### What measurement showed

**Every service already runs as container uid 0:**

```
$ for s in qbittorrent jackett qbittorrent-proxy boba-jackett; do
    printf '%-22s ' "$s"; podman exec "$s" id -u; done
qbittorrent            0
jackett                0
qbittorrent-proxy      0
boba-jackett           0
```

`qBitTorrent-go/Dockerfile` contains **no `USER` directive** (0 occurrences), so that
service runs as root as well.

**A write probe — write a real file through the service, read the owner back FROM THE
HOST:**

```
download-proxy   -> host uid 1000 (milosvasic)     <-- already correct
boba-jackett     -> host uid 1000 (milosvasic)     <-- already correct
qbittorrent, via `s6-setuidgid abc` under PUID=1000
                 -> host uid 100999 (UNKNOWN)      <-- the defect
```

**The third line is the CONTROL NEEDLE (§11.4.201(6)/(7)).** A null or a clean reading
is not evidence until the instrument is proven able to see the defect through the same
path. It can: the same probe, same host, same image, reports the broken identity when
the broken configuration is present. That is what makes the two `1000` readings a real
result rather than a blind instrument.

**Control needle re-run after the fix landed (§11.4.6 — stated because it changes what
the reading means).** Re-running the probe against the *live* `qbittorrent` container
now returns host uid 1000, because `PUID=0` has already been applied and the container
recreated — `podman exec qbittorrent id abc` reports `uid=0(root)`. The live container
is therefore no longer a valid negative control. The control was reconstructed with a
throwaway `PUID=1000` container against the same image:

```
$ podman run --rm -e PUID=1000 -e PGID=1000 -v "$T":/downloads \
    lscr.io/linuxserver/qbittorrent:latest \
    sh -c 's6-setuidgid abc touch /downloads/prefix_control'
$ stat -c '%u (%U)' "$T"/prefix_control
stat: cannot statx '.../prefix_control': Permission denied     <-- as the operator
$ podman unshare stat -c 'in-ns uid %u' "$T"/prefix_control
in-ns uid 1000                                                 <-- = host 100000+1000-1
```

Note what the operator's own view of the defect actually is: not merely a strange
number, but `Permission denied` on a file in a directory they own.

### Why Route A was wrong

Under rootless Podman, **container uid 0 maps to the host operator (uid 1000)**. A
container that already runs as root is therefore *already* writing operator-owned
files — which is exactly what the write probe measured for `download-proxy` and
`boba-jackett`.

Applying `userns_mode: keep-id` to such a container would have:

1. **changed nothing beneficial** — the files were already landing at host uid 1000; and
2. **left the container with no usable root** — the identical failure R3 already
   measured on the linuxserver images, where `--userns=keep-id` made the container
   **hang with no output, twice**.

So Route A was not a no-op. It was a regression waiting to be applied to three
services that were already correct.

### Corrected decision

| Service | Image | Action taken | Basis |
|---|---|---|---|
| `qbittorrent` | linuxserver | **Changed** — `PUID=0` / `PGID=0` | R4; keep-id hangs the image (R3) |
| `jackett` | linuxserver | **Changed** — `PUID=0` / `PGID=0` | R4; same |
| `download-proxy` | python:alpine | **No change** — verified already writing as host uid 1000 | write probe above |
| `qbittorrent-proxy-go` | built Go | **No change** — runs as root, no `USER` directive | `podman exec id -u` = 0 |
| `boba-jackett` | built Go | **No change** — verified already writing as host uid 1000 | write probe above |

`userns_mode: keep-id` is applied to **no service in this stack**.

Tasks **T010 / T011 / T012** are therefore closed as **"no change required —
measured"**, not as "done". The distinction is load-bearing: "done" would imply an
edit was made and verified; "no change required — measured" states that the correct
state was found to already hold and names the measurement that established it.

### The lesson — and it is the project's own rule

R3 measured `--userns=keep-id` against a bare `alpine` image — which runs as root and
has no init — and generalised that single result to three services it had **not
individually probed**. R5 even flagged this in its own honest-boundary note ("Route A
is confirmed for `alpine` and asserted for the two Go images ... Tasks MUST verify
each service individually rather than generalising from the alpine result"). The
boundary was written down correctly and the route table was built anyway.

> **A measurement taken through a DIFFERENT path than the one you intend to gate is
> not evidence about that path.** (§11.4.201(7)(c) — the path is part of the
> instrument.)

`alpine` and `lscr.io/linuxserver/*` differ in precisely the property under test: the
presence of an s6 init that requires root before dropping privileges. Probing the
first told us nothing binding about the second, and nothing at all about the two Go
images, which were never probed under `keep-id` before being assigned to Route A.

The corrective practice is per-target probing: **one probe per service, through the
service's own path, with a control needle proving the probe can see the defect.**
That is what produced this correction, and it is what the tasks now require.

---
