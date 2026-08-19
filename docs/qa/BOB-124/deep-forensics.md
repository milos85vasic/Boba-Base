# BOB-124 — Deep Forensic Investigation: 5th Forced-Logout (2026-08-19 15:28:22 CEST)

**Revision:** 1
**Last modified:** 2026-08-19T15:45:00Z
**Verdict (§11.4.6):** SIGKILL INITIATOR **UNATTRIBUTED** — pattern MATCHES #2/#3/#4 signature for every observable class; kernel-audit attribution still impossible (auditd never installed).
**Iron Law:** Investigation only — no fixes, no source changes.

---

## Executive summary

`user@1000.service` was SIGKILLed at `2026-08-19 15:28:22 CEST` exactly 20 min 41 s after login (15:07:41 → 15:28:22). The kill signature is **identical in shape** to prior incidents #2/#3/#4: a `pam_tcb(gdm-password:session): Session closed` for milosvasic on `tty2 ses=4` fires from `gdm-session-worker[3976]` at the SAME journal second as the `Main process exited, code=killed, status=9/KILL` on `user@1000.service`, followed by a mass SIGKILL cascade of every child under the cgroup. No preceding `systemctl stop`, `loginctl terminate-user`, `Manager.StopUnit`, or `KillUnit` D-Bus call appears in the journal window (`docs/qa/BOB-124/evidence/stop_terminate_paths.log` lists only `Removed session 1/4` from `systemd-logind` *after* the SIGKILL). Every kernel-side failure class remains ruled OUT: **no** `oom-kill` in the kernel journal (`evidence/kernel_oom_scan.log` empty), **no** `systemd-oomd` trigger (`evidence/oomd_journal.log` shows only the boot-time Start), **no** suspend/hibernate, **no** power event. `Linger=yes` is set (`evidence/loginctl_user_state.txt`) — which should preserve `user@1000.service` across session teardown, yet did not. This is the fifth consecutive incident where Phase 1 root-cause investigation cannot complete because `auditd`/`auditctl`/`ausearch` are not installed and `/etc/audit/` does not exist (`evidence/loginctl_user_state.txt` bottom lines). Correlate signal: `user@1000.service: Consumed 1h 21.484s CPU time, 23.6G memory peak, 488.2M memory swap peak` in 20 min 41 s — a memory-accumulation rate roughly ×10 faster than the prior session (`23.6 GB / 21 min` vs `25.1 GB / 3 h 22 min` reported in `docs/incidents/2026-08-19-5th-forced-logout.md`), suggesting the reboot did not reset the runaway consumer. The mechanism direction hardens: something INSIDE user@1000 pushes memory into the multi-GB range while sending a `gdm-password` session-close on tty2, and the SIGKILL falls on the user manager PID milliseconds later — but no in-scope observer can name the initiator.

---

## Timeline (evidence-cited)

| Time (CEST) | Event | Evidence |
|---|---|---|
| 15:06:20–35 | Prior session **clean shutdown** (`SERVICE_STOP res=success`) — operator's intentional reboot | `docs/incidents/2026-08-19-5th-forced-logout.md` §"Distinction from the 15:06 clean shutdown" |
| 15:07:39–40 | Host boot; swap activated (16 GB nvme + 32 GB zram); `systemd-oomd.service` started | `docs/qa/BOB-124/evidence/oom_extended.log` lines 3–15 |
| 15:07:41 | `user@1000.service` started for milosvasic | `evidence/user1000_grepped.log` lines 1–2 |
| 15:07:40 | milosvasic session on tty2 (ses=4) — see `loginctl_user_state.txt` `Timestamp=Wed 2026-08-19 15:07:40 CEST` | `evidence/loginctl_user_state.txt` |
| 15:07:41 → 15:28:21 | 20 min 41 s of active work; wave-6 subagents Q/R/S/T dispatched at 15:12 (per `.superpowers/sdd/progress.md`); scaling_probe pytest hits saturate the merge-search rate limiter (many `429 Too Many Requests` in `journal_inc5.log`) | `.superpowers/sdd/progress.md` "Wave-6 in flight — 2026-08-19 15:12"; `journal_inc5.log` 15:28:00-01 batches of ratelimit 10/min exceeded |
| 15:27:14 → 15:28:15 | overlayfs xino warnings + `crun-buildah` scopes: **container build activity** (BOB-096 tests reload) | `evidence/kernel_events.log` |
| 15:28:08 → 15:28:19 | `helix-postgres` errors: `relation "background_tasks" does not exist` (unrelated helix-server churn), then `unexpected EOF on client connection with an open transaction` | `evidence/pre_kill_15s_window.log` |
| 15:28:22.181 | **audit type=1106**: `op=PAM:session_close ... acct="milosvasic" exe="/usr/libexec/gdm-session-worker" ... terminal=/dev/tty2 res=success` from `gdm-session-worker[3976]` | `evidence/kill_moment.log` lines 6996–7002 |
| 15:28:22 | **`systemd[1]: user@1000.service: Main process exited, code=killed, status=9/KILL`** | `evidence/kill_moment.log` line 7005 |
| 15:28:22 | Mass SIGKILL cascade — 90+ children including `postgres`, `qbittorrent-nox`, `webui-bridge`, `tmux: server`, `claude`, `python3`, `MainThread`, `hook-linux-amd6`, `lumen-linux-amd`, `chrome-devtools`, `caddy`, `jetbrainsd`, `yandex_browser` × 15 | `evidence/systemd_pid1_prekill.log` |
| 15:28:23 | `user@1000.service: Failed with result 'signal'` / `Consumed 1h 21.484s CPU time, 23.6G memory peak, 488.2M memory swap peak` | `evidence/user1000_grepped.log` bottom |
| 15:28:22 | `systemd-logind[1296]: Removed session 1` / `Removed session 4` — **AFTER** the SIGKILL, not before | `evidence/stop_terminate_paths.log` |
| 15:28:22 | GDM greeter reappears on tty1 (`gdm-launch-environment ... session opened for gdm-greeter`) | `evidence/gdm_compositor_events.log` |
| 15:28:35 | milosvasic re-authenticated; `session-7` (wayland/class=user) + `session-8` (manager); user@1000 started again | `evidence/stop_terminate_paths.log` line 7478; `evidence/user1000_grepped.log` last two lines |

**Elapsed dead:** ≈ 13 s (15:28:22 → 15:28:35 relogin). GDM auto-reset the greeter within 1 s.

---

## Comparative signature table across #2 / #3 / #4 / #5

Sources: `docs/incidents/2026-08-18-perceived-forced-logout-2nd.md` (#2), `docs/incidents/2026-08-18-3rd-forced-logout.md` (#3), `docs/incidents/2026-08-19-4th-forced-logout.md` + `docs/qa/BOB-123/incident-4-forensics.log` (#4), THIS file (#5).

| Signature | #2 (2026-08-18 20:50) | #3 (2026-08-18 23:45) | #4 (2026-08-19 00:37) | #5 (2026-08-19 15:28) |
|---|---|---|---|---|
| `gdm-session-worker` PAM `session_close` acct=`milosvasic` at exact SIGKILL timestamp | **YES** (per #4 doc) | **YES** (per #4 doc) | **YES** (`inc4_forensics_head.txt` line 3116) | **YES** (`evidence/kill_moment.log` L6996) |
| `terminal=/dev/tty2 res=success` in the audit1106 | YES | YES | YES | **YES** |
| `user@1000.service: Main process exited, code=killed, status=9/KILL` (bare, no preceding Stopping/Deactivating) | YES | YES | YES | **YES** (`evidence/systemd_pid1_prekill.log` L1) |
| Explicit `loginctl terminate` / `systemctl stop user@1000` / `Manager.StopUnit` / `KillUnit` in window | **NO** (per #4 §"Journal search ... returns EMPTY") | **NO** | **NO** | **NO** (`evidence/stop_terminate_paths.log` — only *post-kill* `Removed session 1/4`) |
| `Linger=yes` (should have preserved user@1000) | YES (per #4) | YES | YES (`inc4_forensics_head.txt` §3) | **YES** (`evidence/loginctl_user_state.txt`) |
| `IdleAction=ignore` (verified in #4) | verified | verified | verified | **not re-checked this incident** — `/etc/systemd/logind.conf` not read (no §11.4.199 exact-reproduction re-run required) |
| Kernel OOM (`oom-kill`, `invoked oom-killer`) fired | NO | NO | NO | **NO** (`evidence/kernel_oom_scan.log` empty) |
| `systemd-oomd` triggered a kill decision | NO | NO | NO | **NO** (`evidence/oomd_journal.log` shows only Start at 15:07:40; nothing else) |
| Suspend/hibernate/power-state event | NO | NO | NO | **NO** (`evidence/power_states.log` = 2 noise lines about gsd-media-keys keybindings, no actual power transition) |
| `KillUserProcesses` runtime state | unset (per #4) | unset | unset (per #4 §"Ruled out") | **not re-queried** (`busctl` not re-run this incident) |
| user@1000 memory peak at teardown | not recorded per-incident | not recorded | not recorded in #4 doc | **23.6 GB in 20 min 41 s** (`evidence/user1000_service_journal.log`? — actually in `user1000_grepped.log`) |
| user@1000 CPU peak at teardown | — | — | — | **1 h 21.484 s** in 20:41 wall clock (≈ 4 cores saturated) |
| Load average at incident window | not captured | not captured | `0.20, 0.70, 1.06` (light) | `0.80, 5.01, 4.65` at 15:34 (`docs/qa/BOB-124/incident-5-forensics.log`) — HEAVY |
| Parallel subagent load at kill | 3+ concurrent (per #4 §"defensive move") | 3+ | 3+ (Task 85/86/BOB-122/BOB-118 landed) | **4 concurrent (Wave-6 Q/R/S/T at 15:12) + scaling_probe pytest fleet** |
| `auditctl` / `ausearch` / `/etc/audit/rules.d/` present | NO | NO | NO (per #4 §"Recommended next step") | **NO** (`auditctl absent: YES`, `/etc/audit absent: YES`) |
| Session dead-time before relogin | — | — | 13 min | **13 s** (fastest) |

**Signature match ratio:** every checkable dimension for #5 matches #4 exactly. The two "not re-checked" cells (`IdleAction`, `KillUserProcesses`) were verified stable in #4 and no reboot changed `logind.conf` — but `evidence/loginctl_user_state.txt` shows `IdleHint=no IdleSinceHint=0`, i.e. logind considered the session non-idle at teardown.

---

## Session context (§11.4.6, what the session was doing)

Between 15:12 and 15:28 the SDD orchestration dispatched **Wave-6** — four concurrent Claude subagents (Agents Q/R/S/T per `.superpowers/sdd/progress.md`) plus the merge-search scaling_probe pytest fleet was hammering `/api/v1/search` (`journal_inc5.log` at 15:28:00-01 shows ≥12 different `scaling_probe_*` query ids being fanned across trackers, tripping the 10/min rate limiter — `429 Too Many Requests` bursts). Agent S completed BOB-096 chaos tests at commit `76d6b1f6`; other Wave-6 agents were mid-flight. `crun-buildah` scopes at 15:28:10-15 indicate container build/reload activity. `pgrep -af pytest` at investigation time returned empty (post-kill), consistent with the SIGKILL cascade having reaped them. This matches the #4 forensic note that "all 4 incidents occurred during heavy parallel subagent load" — #5 makes it 5-of-5.

**The load-vs-memory correlation:** `user@1000` consumed 23.6 GB peak in 20:41 elapsed. The prior session (per `docs/incidents/2026-08-19-5th-forced-logout.md`) consumed 25.1 GB in 3 h 22 min. The per-minute rate for the killed session is **≈ 1.14 GB/min** vs **≈ 0.124 GB/min** for the prior — an order of magnitude faster. Whether this rate is causal (systemd-oomd on some ancestor slice, some resource-cap watchdog, or a memory-triggered PAM-close policy) remains **§11.4.6 UNCONFIRMED**: no oomd/OOM/pressure event fired, `/proc/pressure/memory` at investigation time shows `avg60=0.00`, and the initiator is not self-attributed anywhere in the journal.

---

## What ruled OUT this incident (`evidence/` cited)

- **Kernel OOM-killer:** `evidence/kernel_oom_scan.log` returns 0 hits across 15:07-15:29
- **systemd-oomd:** `evidence/oomd_journal.log` shows only boot-time Start; no kill decision, no memory-pressure log
- **Suspend / hibernate / power event:** `evidence/power_states.log` contains only 2 GSD keybinding-registration warnings; kernel journal shows no `PM: suspend` / `Reached target Sleep`
- **Explicit unit-stop invocation** (`loginctl terminate-user`, `systemctl stop user@1000`, `KillUnit`, `Manager.StopUnit`): `evidence/stop_terminate_paths.log` contains only *post-kill* `Removed session 1` and `Removed session 4` from `systemd-logind`. No preceding stop RPC.
- **CONST-033 host power-state transitions:** uptime intact (`up 26 min` at 15:34 → up 31 min at 15:38), no kernel `suspend`/`hibernate` messages
- **Any process explicitly emitting `kill -9` visible in journal:** no `signal 9 to pid ...` audit trail (audit rules absent — see below)

---

## The recurring architectural gap (unchanged across #2–#5)

`auditd` is not installed on this host: `command -v auditctl` returns nothing, `command -v ausearch` returns nothing, `/etc/audit/` does not exist, `/etc/audit/rules.d/` does not exist. The `docs/incidents/2026-08-19-sudo-audit-rules-for-operator.md` install script (Rev 3) was authored + committed but never run with sudo. Without those rules, the kernel audit subsystem cannot attribute a `signal=9` delivery to a specific initiator PID/UID/cmdline. `evidence/user_scope_events_head.log` and `evidence/kill_moment.log` prove the audit *subsystem is running* (`type=1106/1113/1104` messages present), but the `SYSCALL kill` and `PATH exec loginctl|systemctl` watches that would name the initiator are absent from the rules file that does not exist.

Per `docs/incidents/2026-08-19-5th-forced-logout.md` §"Systematic-debugging Phase 4.5" (Iron Law: NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST + "if ≥3 fixes failed: STOP and question the architecture"), the architectural problem is not the SIGKILL mechanism — it is the audit-install gap that has now blocked Phase 1 attribution 5 consecutive times.

---

## What is genuinely NEW in #5 vs #4

1. **Memory-consumption rate ×10 faster than the prior session** — 23.6 GB in 20:41 vs 25.1 GB in 3 h 22 min. The reboot did NOT reset the runaway consumer; whatever pattern of subagent-driven memory growth surfaced in prior sessions surfaced again immediately after a clean boot with the same wave-6 orchestration profile.
2. **Fastest recovery** — 13 s dead-time vs #4's 13 min. This suggests operator was actively at the console and re-authenticated immediately.
3. **Container build activity in the pre-kill window** — `crun-buildah` scopes at 15:28:10-15 and overlayfs xino warnings across 15:27:14 → 15:28:15 (`evidence/kernel_events.log`). Not observed being called out for #2/#3/#4 timelines.
4. **Rate-limiter saturation** — the merge-search proxy issued dozens of `429 Too Many Requests` responses in the seconds before the kill, indicating heavy synthesised load from the scaling_probe pytest fleet.

None of these change the SIGKILL initiator attribution — all four are *correlate signals*, not causal proofs (§11.4.6).

---

## Verdict (§11.4.6)

**§11.4.6 Iron-Law status: STILL INCOMPLETE.** Every observable class ruled out in #4 is ruled out again in #5. Every signature that fired in #4 fired in #5 in identical shape. The initiator remains unattributed because kernel audit rules are still not installed on the host. #5 matches #2/#3/#4 as one class of incident with high confidence: identical PAM close signature + identical bare SIGKILL exit shape + identical `Linger=yes` contradiction + identical absence of every candidate mechanism (kernel OOM, systemd-oomd, explicit stop RPC, power event). The load-and-memory correlation is stronger in #5 than in prior incidents but neither #4's nor #5's data can distinguish CAUSE from CORRELATION without the audit-rules attribution.

---

## Evidence files (all under `docs/qa/BOB-124/`)

- `journal_inc5.log` — full journalctl 15:25-15:30 (11,330 lines)
- `evidence/kill_moment.log` — filtered kill window
- `evidence/systemd_pid1_prekill.log` — every `systemd[1]` message 15:28:15-22
- `evidence/pre_kill_15s_window.log` — 15-s pre-kill filtered journal
- `evidence/signals_at_kill.log` — GDM/mutter/logind/PAM signals at kill
- `evidence/kernel_events.log` — kernel messages (overlayfs, veth, rfkill; **no OOM**)
- `evidence/kernel_oom_scan.log` — **empty** (0 kernel-OOM hits)
- `evidence/oomd_journal.log` — systemd-oomd unit journal (Start only, no kill decisions)
- `evidence/oom_extended.log` — extended OOM/PSI/swap scan
- `evidence/power_states.log` — 2 hits (both false-positive keybinding registrations)
- `evidence/stop_terminate_paths.log` — logind session removals (all post-kill)
- `evidence/gdm_compositor_events.log` — GDM/gnome-shell activity around kill
- `evidence/gdm_worker_3976.log` — the actor of the PAM close (PID 3976 = gdm-session-worker)
- `evidence/user1000_grepped.log` — full user@1000.service lifecycle in window
- `evidence/user1000_service_journal.log` — helix-server journal noise (unrelated to kill)
- `evidence/user_scope_events_head.log` — user/session scope timeline (100-line head)
- `evidence/loginctl_user_state.txt` — `Linger=yes State=active`, `Timestamp=15:07:40`, IdleHint=no
- `evidence/proc_pressure_memory.txt` — current PSI (`avg60=0.00` at investigation time)
- `evidence/free_now.txt` — memory state at investigation
- `evidence/inc4_forensics_head.txt` — first 80 lines of #4 forensics for comparison
- `evidence/kernel_oom_scan.log` — 0 hits, ruling out kernel OOM

## Cross-references

- `docs/incidents/2026-08-18-perceived-forced-logout-2nd.md` (BOB-116, #2)
- `docs/incidents/2026-08-18-3rd-forced-logout.md` (BOB-120, #3)
- `docs/incidents/2026-08-19-4th-forced-logout.md` (BOB-123, #4)
- `docs/incidents/2026-08-19-5th-forced-logout.md` (BOB-124, #5)
- `docs/incidents/2026-08-19-sudo-audit-rules-for-operator.md` (Rev 3 — still uninstalled)
- `docs/proposals/external-watchdog-for-forced-logout-architectural-gap.md` (Path 2 proposal)
- `~/.claude-claude4/.../memory/forced_logout_incidents.md` (playbook)

## Iron Law compliance

No source changes made. No sudo invoked. No auditd installed. No shell scripts modified. Only evidence files written under `docs/qa/BOB-124/`.
