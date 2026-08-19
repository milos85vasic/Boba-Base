# 5th Forced-Logout Incident — 2026-08-19 15:28:22 CEST

**Revision:** 2
**Last modified:** 2026-08-19T17:22:00Z
**Tracker:** BOB-124
**Verdict (§11.4.6):** ✅ **RESOLVED via BOB-126** — the 7th incident's kernel audit trail captured the SAME root cause that drove ALL 7 forced-logout incidents (BOB-116/120/123/124/125/126): a pytest process calling `kill(-1, SIGKILL)` via `MagicMock.__int__==1 → os.killpg(1, 9)` in `tests/unit/merge_service/test_deadline_tunable.py::test_deadline_hit_flag_true_when_readline_times_out`. Fix landed 2026-08-19 at boba commit `ad4b46a` (search.py int-guard + test hardening + §11.4.115 RED regression guard) + constitution commit `502586c` (universal §11.4.263 process-group signal-safety mandate) + boba pointer bump `bf01cf3`. See `docs/incidents/2026-08-19-6th-forced-logout.md` for the full attribution + §11.4.6 correction of the earlier "PAM/Linger contradiction" hypothesis.

**REV-2 correction (2026-08-19 17:22):** the original doc claimed "PAM session_close" mechanism. That was a downstream EFFECT of the pytest kill(-1) — not the initiator. Attribution was CORRECTED by BOB-126's kernel audit trail (which required audit rules installed 15:56 to capture, ~1.5h after this 5th incident occurred).

## What happened

At `2026-08-19 15:28:22 CEST` (21 minutes after the 15:07 login),
`user@1000.service` was SIGKILLed:

```
Aug 19 15:28:22 nezha systemd[1]: user@1000.service: Main process exited,
    code=killed, status=9/KILL
```

Same class as BOB-116 (#2), BOB-120 (#3), BOB-123 (#4). Fifth in the class.

## Distinction from the 15:06 clean shutdown

At `2026-08-19 15:06:20-35` there was a CLEAN shutdown for the operator's
intentional reboot:

```
Aug 19 15:06:20 systemd[1]: Stopping user@1000.service - User Manager...
Aug 19 15:06:35 systemd[1]: user@1000.service: Deactivated successfully.
Aug 19 15:06:35 audit[1]: SERVICE_STOP ... res=success
```

The 15:06 event was `SERVICE_STOP res=success` (systemd Stop with normal
exit). The 15:28:22 event is `code=killed, status=9/KILL` — the incident
class. Not the same event.

## §11.4.6 Iron Law status

Phase 1 STILL incomplete. The BOB-123 audit rules (`docs/incidents/
2026-08-19-sudo-audit-rules-for-operator.md`) were authored + committed
but NEVER installed:

- `/etc/audit/rules.d/logout_investigation.rules` — DOES NOT EXIST
- `ausearch` — NOT on PATH (auditd package may not be installed)
- BOB-123 watchdog — NOT INSTALLED into system.slice

Without kernel audit attribution, the SIGKILL initiator remains
UNATTRIBUTABLE. This is now the 5th consecutive incident where Phase 1
could not complete for the same structural reason.

## Systematic-debugging Phase 4.5 verdict

Per skill: "If ≥ 3 fixes failed: STOP and question the architecture."

We are now at 5 attempts, all blocked at the SAME architectural gap:
**preventive gates authored but not installed** (requires operator
terminal action).

**The architectural problem is not the SIGKILL mechanism — it's the
install gap.**

## Correlate signal — heavy memory

Prior session (13:13 → 15:06) `user@1000.service: Consumed 3h 22min
7.454s CPU time, 25.1G memory peak`. 25 GB is very high. Load average
at 15:32 (4 min after this incident) is `1.59, 6.39, 5.03` — sustained
recent heavy load.

Correlate strongly with prior 4 incidents which also happened under
heavy parallel-subagent load.

## Actions this session

- ⏸️ Paused new subagent dispatches (operator "fix it all" directive)
- ✅ Filed this incident doc
- 🔄 Attempting to restart boba services (4/5 containers not yet up
  post-reboot)
- 🚨 Escalating to operator via AskUserQuestion — Path 1 audit rules
  install is the ONLY remaining Phase 1 completion path

## Cross-references

- `docs/incidents/2026-08-18-perceived-forced-logout-2nd.md` (BOB-116)
- `docs/incidents/2026-08-18-3rd-forced-logout.md` (BOB-120)
- `docs/incidents/2026-08-19-4th-forced-logout.md` (BOB-123)
- `docs/incidents/2026-08-19-sudo-audit-rules-for-operator.md` (Rev 3 — Path 1)
- `scripts/system-slice-watchdog/` (Path 2, ready-to-install)
- Memory playbook: `~/.claude-claude4/.../memory/forced_logout_incidents.md`
- Evidence: `docs/qa/BOB-124/incident-5-forensics.log`
