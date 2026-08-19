# boba user@1000 out-of-scope watchdog (BOB-116 / BOB-120 / BOB-123)

**Revision:** 1
**Last modified:** 2026-08-19T02:00:00Z
**Class:** operator-run system-slice service — captures forensics on user@1000 SIGKILL
**Anchors:** §11.4.4 four-layer, §11.4.108 runtime-signature, §11.4.115 RED-first,
§11.4.6 anti-guessing, §11.4.10 credentials, §11.4.128 recording, §11.4.201
guard-real-condition, §11.4.161 rootless (no; system-slice by intent), §6.U
(operator runs `su`, agent never invokes it).

## Purpose

4 forced-logout incidents (BOB-116 / BOB-120 / BOB-123 + the 2026-07-07 one)
share this mechanism: `user@1000.service` is SIGKILLed → cascade kill of every
child process → GDM greeter respawns → operator perceives sudden logout.

Every in-scope monitor (user systemd timer, user cron, rootless podman
container) DIES IN THE SAME CASCADE and cannot preserve forensics — it is
architecturally incapable of observing the kill of the scope it runs in.

**This watchdog is the ONLY mechanism that can attribute the SIGKILL** because
it lives in `system.slice` (a peer of `user.slice`), so it survives the kill of
`user@1000.service` and captures the surrounding journal + cgroup + audit +
process-tree state DURABLY.

## What gets installed

| Path | Purpose |
|---|---|
| `/usr/local/bin/boba-user1000-watchdog` | The monitor script (bash) |
| `/etc/systemd/system/boba-user1000-watchdog.service` | Systemd unit — `Slice=system.slice`, runs as root, restart on failure |
| `/var/log/boba-watchdog/YYYY-MM-DDTHH-MM-SSZ/` | Per-incident evidence dir, chmod 700 |

## How it works

1. On boot, systemd starts the service in `system.slice` as root.
2. The script runs a pre-flight (§11.4.201): verifies uid=0 AND its own cgroup
   is NOT under `/user.slice/` — if it is, REFUSES to run (would defeat the
   purpose).
3. Enters a `journalctl -f -u user@1000.service` loop.
4. On matching the exact pattern from all 4 incidents (`Main process exited,
   code=killed, status=9/KILL`) it triggers `capture_forensics` immediately.
5. Captures: journal window (`PRE_KILL_WINDOW_SEC` before + `POST_KILL_WINDOW_SEC` after),
   cgroup state (memory + PSI + pids), full process tree, kernel audit log
   (if Path-1 audit rules installed), uptime + last, loginctl show-user.
6. Rotates evidence dirs to keep the last `RETAIN_LAST_N` (default 20).
7. Keeps tailing — captures every subsequent incident too.

## Tunables (environment)

- `BOBA_WATCHDOG_ROOT`       — evidence root (default `/var/log/boba-watchdog`)
- `BOBA_WATCHDOG_RETAIN`     — retain last N incident dirs (default 20)
- `BOBA_WATCHDOG_PRE_SEC`    — pre-kill journal window (default 60)
- `BOBA_WATCHDOG_POST_SEC`   — post-kill journal window (default 15)

Set via drop-in `/etc/systemd/system/boba-user1000-watchdog.service.d/env.conf`
with `[Service]` + `Environment="BOBA_WATCHDOG_ROOT=/path"`.

## Install / uninstall

Per §6.U + §11.4.109, no agent tool invokes `su`/`sudo`. Install and uninstall
scripts print `su -c '…'` commands you copy/paste at your terminal:

```bash
bash scripts/system-slice-watchdog/install.sh    # prints commands to run
bash scripts/system-slice-watchdog/uninstall.sh  # prints commands to run
```

## Anti-bluff verification (§11.4.108 + §11.4.115)

Run the challenge WITHOUT root — verifies structural correctness:

```bash
bash challenges/scripts/user1000-watchdog-challenge.sh              # GREEN mode
POLARITY_MODE=red bash challenges/scripts/user1000-watchdog-challenge.sh  # golden-bad polarity
```

The challenge asserts:

1. All source files exist + parseable (`bash -n`, systemd unit shape)
2. All installer scripts are executable
3. **Load-bearing**: service declares `Slice=system.slice` (not `user.slice`)
4. Watchdog pre-flight refuses to run in user.slice
5. Evidence root is durable (`/var/log`, not tmpfs)
6. Journal trigger matches the exact BOB-116/BOB-120/BOB-123 signature
7. Rotation implemented (bounded disk)
8. Resource limits set (`MemoryMax`, `CPUQuota`, `TasksMax`)

## After an incident

The forensics are in `/var/log/boba-watchdog/<timestamp>/`:

```
state.log         — uptime, last, loginctl, meminfo, PSI, cgroup snapshot
journal-pre.log   — journal for PRE_KILL_WINDOW_SEC before kill
journal-post.log  — journal captured POST_KILL_WINDOW_SEC after kill
proctree.log      — full ps auxf + top-20-by-RSS
audit.log        — kernel audit logs (requires Path-1 sudo audit rules)
```

## Compose with Path 1 (kernel audit rules)

For **initiator attribution** (PID + UID + cmdline of the SIGKILL sender), run
the audit-rule install from `docs/incidents/2026-08-19-sudo-audit-rules-for-operator.md`
BEFORE the next incident. The watchdog captures the audit log entries; without
the rules, `audit.log` will say "(ausearch failed — audit rules may not be installed)".

## Honest boundaries (§11.4.6)

- The watchdog DIAGNOSES; it does NOT prevent the kill.
- It DOES survive the kill (proven by system-slice deployment).
- It CANNOT observe events pre-kill that happen outside `user@1000.service`'s
  journal — e.g. a mutter/gnome-shell segfault would be in the user's journal
  which may already be flushed by the time the watchdog captures.
- The watchdog runs as root (needed to survive user@1000 kill + read all
  journals); it is bounded by `MemoryMax=200M` and `CPUQuota=15%` per §12.6.
- No credentials are logged (§11.4.10). Cookies-file loader is NOT invoked here.
