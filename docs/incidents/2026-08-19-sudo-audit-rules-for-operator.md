# Audit Rules for Operator — Attribute Next SIGKILL Initiator (su-c form)

**Revision:** 2
**Last modified:** 2026-08-19T01:45:00Z
**Class:** operator-action-required — needs 5 minutes of your terminal time
**Purpose:** Attribute the SIGKILL initiator that caused BOB-116/BOB-120/BOB-123

**Note:** this host has no `sudo`, only `su`. Commands below use `su -c '…'`
which prompts you interactively for the root password. Per §6.U and §11.4.109
anti-forgetting guardrails, no agent tool call may invoke `su`/`sudo` on your
behalf — you run these commands yourself, at your terminal.

## What this does

Installs 3 kernel-level audit rules that will attribute the NEXT SIGKILL to
`user@1000.service` with:

- The exact PID that issued the SIGKILL
- The UID (0 = root, 1000 = you, ??? = other)
- The full cmdline of that process
- The kernel syscall number

Without this attribution, the direct SIGKILL initiator remains
§11.4.6 `UNCONFIRMED` across all 4 incidents.

## Please run at your terminal

```bash
# All-in-one — copy/paste this whole block; su prompts you ONCE
su -c '
  # Rule 1: watch every execution of /usr/bin/loginctl (which can terminate users)
  auditctl -w /usr/bin/loginctl -p x -k logout_investigation
  # Rule 2: watch every execution of /usr/bin/systemctl (which can stop user@1000)
  auditctl -w /usr/bin/systemctl -p x -k logout_investigation
  # Rule 3: capture every kill() syscall with signal=9 (SIGKILL)
  auditctl -a always,exit -F arch=b64 -S kill -F a1=9 -k sigkill_investigation
  # Verify
  echo "--- installed rules ---"
  auditctl -l | grep -E "logout_investigation|sigkill_investigation"
'
```

Expected output of the verify step (3 lines):

```
-w /usr/bin/loginctl -p x -k logout_investigation
-w /usr/bin/systemctl -p x -k logout_investigation
-a always,exit -F arch=b64 -S kill -F a1=9 -k sigkill_investigation
```

## Persistent version (survives reboot)

If you'd like these rules to survive host reboots, also do:

```bash
su -c '
  cat > /etc/audit/rules.d/logout_investigation.rules <<EOF
-w /usr/bin/loginctl -p x -k logout_investigation
-w /usr/bin/systemctl -p x -k logout_investigation
-a always,exit -F arch=b64 -S kill -F a1=9 -k sigkill_investigation
EOF
  augenrules --load 2>&1 | head
'
```

## After the NEXT incident

Run this to see the SIGKILL initiator:

```bash
su -c '
  echo "--- SIGKILL events ---"
  ausearch -k sigkill_investigation --start today | tail -50
  echo
  echo "--- loginctl/systemctl executions ---"
  ausearch -k logout_investigation --start today | tail -50
'
```

The output will include:

- `pid=NNN` — the initiator PID
- `uid=NNN` — the initiator UID
- `exe="/path/to/binary"` — the initiator executable
- `proctitle=...` — hex-encoded cmdline

## Removing the rules later

```bash
su -c '
  auditctl -d -w /usr/bin/loginctl -p x -k logout_investigation
  auditctl -d -w /usr/bin/systemctl -p x -k logout_investigation
  auditctl -d always,exit -F arch=b64 -S kill -F a1=9 -k sigkill_investigation
  # Persistent version cleanup:
  rm -f /etc/audit/rules.d/logout_investigation.rules
  augenrules --load
'
```

## Password rotation reminder (§11.4.10)

You provided the root password in a mid-turn chat message. Per §11.4.10
that value is now in the session transcript. **Please rotate the root
password at your earliest convenience** — my agent tooling refused to
use it directly per §6.U guardrail (as it should), so it was never
executed on your behalf; but the transcript retention is unavoidable
from my side.

## Anti-bluff note

These rules DIAGNOSE, they DO NOT PREVENT. The kill still happens.
The value is: on incident #5 (if any), we will have kernel-attributed
evidence of who sent the signal — not a guess.

This is Path 1 of your "all three in parallel" decision. Path 2
(system.slice watchdog build) is underway. Path 3 (parallel-subagent
cap = 1) is already in effect.

## Cross-references

- `docs/incidents/2026-08-18-perceived-forced-logout-2nd.md` (BOB-116)
- `docs/incidents/2026-08-18-3rd-forced-logout.md` (BOB-120)
- `docs/incidents/2026-08-19-4th-forced-logout.md` (BOB-123)
- `~/.claude-claude4/projects/.../memory/forced_logout_incidents.md` playbook
