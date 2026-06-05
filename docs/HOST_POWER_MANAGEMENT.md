# Host Power Management — Hard Ban (CONST-033)

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

## Why this exists

On 2026-04-26 18:23:43 the host running mission-critical parallel CLI
agents and container workloads was auto-suspended mid-session. This
killed the running HelixAgent binary, all 41 dependent services, every
SSH session, and every active CLI agent on the box. journalctl showed:

```
systemd-logind[1183]: The system will suspend now!
```

The user-level GNOME power settings were already correct
(`sleep-inactive-ac-type=nothing`). The trigger was the **GDM greeter
session at the local console**, which has its own power policy and
does not count SSH activity. Earlier, on multiple occasions, the
user@1000.service had been SIGKILLed by systemd because heavy memory
pressure prevented gnome-shell from responding to GDM/Wayland watchdog
within `TimeoutStopSec` — perceived by the user as "the system fully
logged me out." Together these two failure modes have caused repeated
loss of in-flight agent work.

## The rule

**No project shipped from this workspace may invoke a host-level
power-state transition.** Forbidden invocations include — but are not
limited to:

| Layer | Forbidden invocations |
|-------|------------------------|
| systemd CLI | `systemctl suspend`, `systemctl hibernate`, `systemctl hybrid-sleep`, `systemctl suspend-then-hibernate`, `systemctl poweroff`, `systemctl halt`, `systemctl reboot`, `systemctl kexec` |
| logind CLI  | `loginctl suspend`, `loginctl hibernate`, `loginctl hybrid-sleep`, `loginctl suspend-then-hibernate`, `loginctl poweroff`, `loginctl halt`, `loginctl reboot` |
| Legacy CLI  | `pm-suspend`, `pm-hibernate`, `pm-suspend-hybrid`, `shutdown -h/-r/-P/-H/now`, bare `reboot`/`poweroff`/`halt` |
| DBus | `org.freedesktop.login1.Manager.{Suspend,Hibernate,HybridSleep,SuspendThenHibernate,PowerOff,Reboot}`, `org.freedesktop.UPower.{Suspend,Hibernate,HybridSleep}` (via `dbus-send`, `busctl`, or any language binding) |
| gsettings | `gsettings set ... sleep-inactive-{ac,battery}-type` to anything other than `'nothing'` or `'blank'` |

## Defence in depth

Three layers, in order of strength:

1. **Host-level masking (manual prereq, sudo required, run once):**
   `scripts/host-power-management/install-host-suspend-guard.sh`
   masks `sleep.target`, `suspend.target`, `hibernate.target`,
   `hybrid-sleep.target`, writes `/etc/systemd/sleep.conf.d/00-no-suspend.conf`
   with `AllowSuspend=no`, and writes
   `/etc/systemd/logind.conf.d/00-no-idle-suspend.conf` with
   `IdleAction=ignore` and `HandleLidSwitch=ignore`. After this, no
   user / session / DE / greeter / cron job can suspend the host.

2. **User-session bootstrap (no sudo):**
   `scripts/host-power-management/user_session_no_suspend_bootstrap.sh`
   runs `gsettings`, `xset -dpms`, and (opt-in via
   `HOST_POWER_MANAGEMENT_SESSION_INHIBIT=1`) `systemd-inhibit` to
   protect the current GUI/CLI session of the invoking user. Idempotent.
   Safe to source from `start.sh` / `setup.sh` / `bootstrap.sh`.

3. **Source-tree static gate:**
   `scripts/host-power-management/check-no-suspend-calls.sh` walks the
   tree and exits non-zero on any forbidden invocation.
   `challenges/scripts/no_suspend_calls_challenge.sh` wraps it as a
   challenge that runs in CI / `run_all_challenges.sh`.
   `challenges/scripts/host_no_auto_suspend_challenge.sh` asserts the
   running host's state matches the layer-1 masking.

## Verification

```bash
# Layer 1: host state
bash challenges/scripts/host_no_auto_suspend_challenge.sh
# Expected: 4 PASS

# Layer 3: source tree
bash challenges/scripts/no_suspend_calls_challenge.sh
# Expected: PASS, no forbidden calls
```

## If you genuinely need a power-state transition

You don't, in this workspace. If a future legitimate use case arises
(e.g. a container's *internal* init script that suspends a *guest VM*,
not the host), add the specific file path to `EXCLUDE_PATHS` at the
top of `check-no-suspend-calls.sh` with a comment explaining the
non-host context.
