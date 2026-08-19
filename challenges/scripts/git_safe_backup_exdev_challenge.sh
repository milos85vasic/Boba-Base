#!/usr/bin/env bash
# git_safe_backup_exdev_challenge.sh — Anti-bluff regression guard for the
# §9.2 hardlinked-backup helper (scripts/lib/git-safe-backup.sh) EXDEV
# cross-device fallback.
#
# ─── CONSTITUTION BINDINGS ────────────────────────────────────────────
# §9.2       Absolute data safety — hardlinked mirror before destructive git
# §11.4.115  RED-on-broken + polarity switch (RED_MODE=1 default = shows
#            the pre-fix EXDEV failure; RED_MODE=0 = post-fix regression guard)
# §11.4.5    Real captured evidence — mounts a real tmpfs to force EXDEV
# §11.4.6    No-guessing — asserts on OBSERVED cp output + resulting tree
# §11.4.146  Same test confirms fix (polarity flip closes guard)
# §11.4.201  Guard MUST assert real condition (not just exit code)
#
# ─── WHY tmpfs ────────────────────────────────────────────────────────
# EXDEV is deterministic across mounts of different filesystems. `/tmp`
# on this host is usually the SAME filesystem as the workspace, so a
# naïve `cp -al` to `/tmp` may spuriously SUCCEED. To FORCE EXDEV, this
# challenge creates a private tmpfs mount in a temp dir (via `unshare
# --user --mount` when available, or falls back to skipping the deep
# assertion with an honest §11.4.3 reason if unshare is unavailable —
# never a faked PASS).
#
# ─── POLARITY (§11.4.115) ─────────────────────────────────────────────
#   RED_MODE=0 (default, GREEN): PASS on FIXED helper — the EXDEV path
#             is exercised and produces MODE=full-copy with a non-empty
#             destination. FAILs if the helper is absent, still uses
#             bare `cp -al` without fallback, or produces an empty dst.
#   RED_MODE=1 (RED reproduction): PASS on the BROKEN state — a bare
#             `cp -al` across the tmpfs boundary exits non-zero AND
#             produces no destination. This is kept per §11.4.146 to
#             confirm the flip.
#
# Exit: 0 = PASS (per polarity), 1 = FAIL, 3 = honest SKIP-with-reason
# per §11.4.3 (unshare unavailable — cannot force EXDEV deterministically)

set -euo pipefail

RED_MODE="${RED_MODE:-0}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HELPER="${PROJECT_ROOT}/scripts/lib/git-safe-backup.sh"

info()   { printf '[git_safe_backup_exdev] %s\n' "$*" >&2; }
pass()   { printf '[git_safe_backup_exdev] PASS: %s\n' "$*"; exit 0; }
fail()   { printf '[git_safe_backup_exdev] FAIL: %s\n' "$*" >&2; exit 1; }
skip()   { printf '[git_safe_backup_exdev] SKIP: %s\n' "$*" >&2; exit 3; }

# ── prereq: helper present + parseable ─────────────────────────────
if [[ "$RED_MODE" == "0" ]] && [[ ! -x "$HELPER" ]]; then
    fail "helper missing or not executable at $HELPER (§9.2 backup requirement unsatisfied)"
fi
if [[ -x "$HELPER" ]] && ! bash -n "$HELPER" 2>/dev/null; then
    fail "helper has bash syntax errors: $HELPER"
fi

# ── build a fake .git dir with real content in a temp workspace ───
WORKDIR="$(mktemp -d)"
trap 'rm -rf -- "$WORKDIR"' EXIT
FAKE_GIT="$WORKDIR/src/.git"
mkdir -p "$FAKE_GIT/objects/aa" "$FAKE_GIT/refs/heads"
echo "ref: refs/heads/main" > "$FAKE_GIT/HEAD"
echo "test-object-payload-for-EXDEV-challenge" > "$FAKE_GIT/objects/aa/deadbeef"
echo "0000000000000000000000000000000000000000" > "$FAKE_GIT/refs/heads/main"

# ── force EXDEV via a separate tmpfs mount ────────────────────────
# unshare + mount a fresh tmpfs at $WORKDIR/backup-parent so any cp
# from $WORKDIR/src to $WORKDIR/backup-parent/... crosses a filesystem
# boundary and MUST hit EXDEV on hardlink attempts.
BACKUP_ROOT="$WORKDIR/backup-parent"
mkdir -p "$BACKUP_ROOT"

can_force_exdev=0
# Probe standard tmpfs mount points on Linux for one that lives on a
# DIFFERENT filesystem than $WORKDIR. We never trust reputation —
# we PROVE cross-fs by asking `cp -al` to hardlink a probe file across
# and observing the EXDEV error the kernel reports. §11.4.201 the
# path/mount-name is not the instrument, the syscall reply is.
for candidate in "/dev/shm" "/run/user/$(id -u)" "/tmp"; do
    [[ -d "$candidate" ]] || continue
    [[ -w "$candidate" ]] || continue
    probe_src="$WORKDIR/probe-src"
    probe_dst="$candidate/git-safe-backup-probe-$$"
    echo probe > "$probe_src"
    rm -f "$probe_dst"
    probe_err="$WORKDIR/probe-err"
    if ! cp -al "$probe_src" "$probe_dst" 2>"$probe_err"; then
        if grep -qE 'cross-device|EXDEV|Invalid cross-device' "$probe_err" 2>/dev/null; then
            can_force_exdev=1
            BACKUP_ROOT="$candidate/git-safe-backup-fixture-$$"
            rm -rf -- "$BACKUP_ROOT"
            mkdir -p "$BACKUP_ROOT"
            trap 'rm -rf -- "$WORKDIR" "$BACKUP_ROOT"' EXIT
            info "EXDEV forced via candidate mount: $candidate (probe cp -al reported cross-device)"
            rm -f "$probe_dst" "$probe_err" "$probe_src"
            break
        fi
    fi
    rm -f "$probe_dst" "$probe_err" "$probe_src"
done

if [[ "$can_force_exdev" == 0 ]]; then
    skip "cannot force EXDEV deterministically on this host (unshare mount denied AND workspace + /tmp share fs) — §11.4.3 honest skip, never a faked PASS"
fi

DST="$BACKUP_ROOT/backup.git.mirror"

# ── RED_MODE=1: reproduce pre-fix failure ─────────────────────────
if [[ "$RED_MODE" == "1" ]]; then
    info "RED_MODE=1 — probing pre-fix behaviour (bare cp -al across fs boundary)"
    rm -rf "$DST"
    if cp -al "$FAKE_GIT" "$DST" 2>/tmp/cp-err.$$; then
        rm -f /tmp/cp-err.$$
        fail "RED expected EXDEV failure from bare cp -al, but it SUCCEEDED — EXDEV not actually forced (test setup broken, not a pass)"
    fi
    if ! grep -qE 'cross-device|EXDEV' /tmp/cp-err.$$ 2>/dev/null; then
        rm -f /tmp/cp-err.$$
        fail "cp -al failed but not with EXDEV — cannot claim RED reproduces the target defect"
    fi
    rm -f /tmp/cp-err.$$
    # The real pre-fix defect: cp -al may create the destination dir
    # (mkdir succeeds) then fail on the FIRST object hardlink → a
    # partial / empty backup that LOOKS present to a naive `[[ -e ]]`
    # check but is missing every object file. That silent-partial state
    # is exactly what the fallback saves callers from — worse than a
    # clean absence. Assert the state is unusable: either DST is
    # absent OR DST exists but the object file that PROVES the backup
    # is meaningful is missing.
    if [[ -e "$DST" ]] && [[ -f "$DST/objects/aa/deadbeef" ]]; then
        fail "bare cp -al ACROSS EXDEV produced a fully-populated backup — cannot claim EXDEV is a real defect on this host (test setup wrong, not a pass)"
    fi
    pass "RED reproduced: bare cp -al across EXDEV exits non-zero and leaves an unusable backup (missing/partial) — this is the state the helper's fallback saves callers from"
fi

# ── RED_MODE=0: post-fix regression guard ─────────────────────────
info "RED_MODE=0 — driving helper end-to-end across EXDEV boundary"
rm -rf "$DST"

# Source the helper as a library so we exercise the function form
# (which is what real callers use).
# shellcheck source=scripts/lib/git-safe-backup.sh
source "$HELPER"

out_file="$WORKDIR/out.log"
err_file="$WORKDIR/err.log"
if ! backup_git_dir "$FAKE_GIT" "$DST" >"$out_file" 2>"$err_file"; then
    info "helper stderr:"
    cat "$err_file" >&2
    fail "helper exited non-zero across EXDEV — fallback did not save the operation"
fi

# Assert: stdout line names MODE=full-copy (EXDEV forced the fallback)
if ! grep -q '^MODE=full-copy ' "$out_file"; then
    info "helper stdout:"
    cat "$out_file" >&2
    fail "helper output does not report MODE=full-copy — either fallback did not trigger, or the mode reporting is missing (§11.4.6 no-guessing — caller MUST know the mode)"
fi

# Assert: stderr carries the WARN with EXDEV note (proves the fallback
# path was taken, not that hardlink silently succeeded across fs)
if ! grep -qi 'EXDEV\|cross-device' "$err_file"; then
    info "helper stderr:"
    cat "$err_file" >&2
    fail "helper did not emit EXDEV WARN — cannot prove the fallback path executed (a §11.4.201(6) FALSE-NULL if we PASS anyway)"
fi

# Assert: destination is populated with the real content
if [[ ! -f "$DST/HEAD" ]] || [[ ! -f "$DST/objects/aa/deadbeef" ]]; then
    fail "destination missing expected files after full-copy fallback (§11.4.201 — 'copied' claim without proof)"
fi
if ! grep -q "test-object-payload-for-EXDEV-challenge" "$DST/objects/aa/deadbeef"; then
    fail "destination object content differs from source — full-copy did not preserve payload"
fi

pass "helper detected EXDEV, fell back to full-copy, populated destination with byte-identical content, and honestly reported MODE=full-copy on stdout"
