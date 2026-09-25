#!/usr/bin/env bash
# scripts/hooks/auto-commit-forensic-capture.sh — BOB-077 forensic capture for
# the "Auto-commit" / "Auto-commit <epoch-ms>" mystery-commit pattern.
#
# ─── WHY THIS EXISTS ────────────────────────────────────────────────────
# docs/Issues.md BOB-077 (RD2-10). Operator decision 2026-08-26 (§11.4.66):
# "UNKNOWN — INSTRUMENT THE NEXT OCCURRENCE." The mechanical MECHANISM was
# identified 2026-09-25 with hard evidence (see
# docs/qa/BOB-077/investigation_20260925.md): two generic, project-agnostic
# shell scripts in the operator's shared `project_toolkit` (NOT part of this
# repo, exported on PATH as the `commit` and `commit-fully` commands) fall
# back to an auto-generated commit message whenever invoked with no explicit
# message argument:
#   - Software-Toolkit/Utils/Git/commit.sh:  MESSAGE="Auto-commit $SESSION"
#     where $SESSION = $(($(date +%s%N)/1000000)) computed INSIDE that
#     script — produces "Auto-commit <epoch-ms>".
#   - Upstreamable/commit.sh: MESSAGE="Auto-commit $SESSION" using the
#     shell's *inherited* $SESSION env var (not computed) — when that var is
#     unset/empty (confirmed empty in this environment at investigation
#     time), the message is the literal string "Auto-commit " (trailing
#     space) which `git commit -m` strips per its default "strip" cleanup
#     mode, landing as the bare "Auto-commit" pattern.
# This closes WHY the pattern exists, but NOT which host/session actually
# invoked one of those commands for any GIVEN future occurrence, nor
# whether the identified mechanism is the ONLY source. Per the operator's
# 2026-08-26 decision this script is still owed: instrument every future
# occurrence with a captured forensic record naming its origin, rather than
# re-guessing from git metadata alone (§11.4.6).
#
# ─── WHAT IT CAPTURES ───────────────────────────────────────────────────
# One append-only JSON-Lines record per matching commit, written to
# LOG_FILE, containing: committer identity (name+email) and author identity,
# the commit's own committer-date (carries its timezone offset, e.g. +0500),
# the OBSERVING host's current hostname and timezone offset (a cross-check:
# if this hook is genuinely firing on the committing host, the two offsets
# should agree), the capturing user, the repo working directory, every
# configured git remote (name + push URL, credential-stripped), the elapsed
# seconds between the commit's own timestamp and the moment this hook
# observed it (near-zero ⇒ hook fired live via a real post-commit trigger;
# large ⇒ this was a retroactive/manual scan, honestly labelled as such),
# and an explicit, honest note on the one field this hook CANNOT measure
# (see "PUSH TIMING — HONEST LIMITATION" below).
#
# ─── PUSH TIMING — HONEST LIMITATION (§11.4.6) ──────────────────────────
# `git`'s `post-commit` hook fires strictly LOCALLY, immediately after the
# commit object is written, and BEFORE any `git push` of that commit has
# happened (a commit can sit local-only indefinitely, or be pushed by a
# wholly separate later command/process). This script therefore CANNOT
# observe true push-completion time from a post-commit trigger alone — it
# records only the CONFIGURED remotes (the ones a subsequent push COULD
# target), never a "pushed at" timestamp. Building a paired pre-push/
# post-push instrument to close that gap was considered and deliberately
# NOT done in this pass: this repo's existing scripts/git_hooks/pre-push
# hook already performs a blocking §11.4.75 mutation-marker re-check by
# rebuilding HEAD into a temp worktree, and §11.4.234 mandates that no hook
# addition may risk making the commit/push mechanism newly blockable —
# bolting extra logic onto that specific hook was judged higher-risk than
# the value of a push-timestamp field. If push-timing ever becomes load-
# bearing for closing this item, the correct extension point is a NEW,
# separate, non-blocking pre-push (or post-push, where the platform
# supports one) hook that only appends to this same LOG_FILE — never an
# edit to the existing blocking pre-push gate.
#
# ─── TRIGGER / WIRING ────────────────────────────────────────────────────
# Wired from scripts/git_hooks/post-commit (installed into .git/hooks/
# post-commit via scripts/install_git_hooks.sh — never auto-installed,
# §11.4.234 "hooks must never silently gate the commit/push mechanism").
# post-commit fires on every LOCAL commit made through a checkout that has
# this hook installed, regardless of which command/wrapper/script invoked
# `git commit` — this is deliberate: since the actual producing mechanism
# is external, project-agnostic tooling this repo does not control (see
# above), the only reliable observation point is "after the fact, on every
# commit, no matter what created it" — exactly the polling/post-commit
# choice the tracked item's own acceptance text names as the fallback.
# Also directly runnable standalone (`bash scripts/hooks/
# auto-commit-forensic-capture.sh [<sha>]`) for manual/retroactive scans;
# the capture-delta field honestly distinguishes a live post-commit fire
# from a retroactive run.
#
# ─── USAGE ────────────────────────────────────────────────────────────────
#   bash scripts/hooks/auto-commit-forensic-capture.sh [<sha>]
#       Inspect <sha> (default: HEAD). If its subject matches a closed
#       bare/templated pattern, append one JSON-Lines record to LOG_FILE.
#       A non-matching commit is a silent no-op (exit 0, nothing written).
#   AUTO_COMMIT_FORENSIC_LOG=<path> bash scripts/hooks/auto-commit-forensic-capture.sh [<sha>]
#       Override the log path (used by --self-test; also usable to redirect
#       output for a dry run without touching the tracked log).
#   bash scripts/hooks/auto-commit-forensic-capture.sh --self-test
#       §11.4.107(10) self-validation: golden-good (non-matching commit
#       produces no record) + golden-bad (both closed patterns produce a
#       correctly-populated record) + a field-completeness assertion, all
#       in a disposable temp git repo. Never touches the real repo or its
#       log file.
#
# ─── EXIT ───────────────────────────────────────────────────────────────
#   Always 0 (never blocks; this is an observer, not a gate — §11.4.234).
#   --self-test exits 1 on a self-test failure, 0 on pass.
#
# BARE_PATTERNS below is kept in lockstep with scripts/hooks/
# unattributed-commit-guard.sh's own BARE_PATTERNS array by convention (not
# by sourcing — the guard's own argument-parsing/mode-dispatch runs
# unconditionally at file scope, so sourcing it here would re-execute that
# dispatch instead of just importing the pattern list; a 3-line duplicated
# constant was judged lower-risk than editing that script's control flow).
# If you add a new bare/templated pattern to either script, add it to both.
#
# Constitution: §11.4.6 (no-guessing — every field either measured or
# explicitly labelled unmeasurable), §11.4.10 (credentials never leak —
# remote URLs are credential-stripped before logging), §11.4.66 (operator
# decision this script fulfils), §11.4.75 (hooks are mechanical, generic),
# §11.4.84 (working-tree quiescence — this observer never mutates), §11.4.85
# stress/chaos posture N/A (observer-only, no mutation surface), §11.4.107(10)
# (self-validated golden-good/golden-bad), §11.4.201(7)(a) (structure- not
# substring-matching), §11.4.234 (hooks never gate commit/push).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
    echo "ERROR: not inside a git repository" >&2
    exit 2
fi

BARE_PATTERNS=(
    '^Auto-commit$'
    '^Auto-commit [0-9]+$'
    '^sync:[[:space:]]'
)

LOG_FILE="${AUTO_COMMIT_FORENSIC_LOG:-$REPO_ROOT/docs/qa/BOB-077/auto_commit_forensic_log.jsonl}"

# Emits 0 (matched, sets MATCHED_PATTERN) or 1 (no match). $1=subject
_match_bare_pattern() {
    local subject="$1" pat
    for pat in "${BARE_PATTERNS[@]}"; do
        if [[ "$subject" =~ $pat ]]; then
            MATCHED_PATTERN="$pat"
            return 0
        fi
    done
    return 1
}

# JSON-string-escape a single field (backslash, double-quote, control chars).
# Never trusts input shape (§11.4.6) — a remote URL or committer name could
# contain any byte a human types.
_json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="$(printf '%s' "$s" | tr '\n' ' ')"
    printf '%s' "$s"
}

# Strips embedded basic-auth credentials from a remote URL before it is ever
# written to the log (§11.4.10) — e.g. https://user:token@host/x -> https://host/x.
# SSH-style remotes (git@host:path) carry no embedded credential and pass
# through unchanged.
_strip_url_credentials() {
    local url="$1"
    if [[ "$url" =~ ^(https?://)[^/@]*@(.*)$ ]]; then
        printf '%s%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    else
        printf '%s' "$url"
    fi
}

# Builds the JSON array of {"name":...,"push_url":...} for every configured
# remote in $1=repo-root.
_remotes_json() {
    local root="$1" first=1 out="[" name url safe
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        url="$(git -C "$root" remote get-url --push "$name" 2>/dev/null || git -C "$root" remote get-url "$name" 2>/dev/null || echo "")"
        safe="$(_strip_url_credentials "$url")"
        [ "$first" -eq 1 ] || out+=","
        out+="{\"name\":\"$(_json_escape "$name")\",\"push_url\":\"$(_json_escape "$safe")\"}"
        first=0
    done < <(git -C "$root" remote 2>/dev/null)
    out+="]"
    printf '%s' "$out"
}

# Captures + appends one forensic record for $1=sha $2=root $3=log_file.
# Returns 0 always (never fails the caller — an observer must not itself
# become a new bluff-surface / blocking failure mode).
_capture_record() {
    local sha="$1" root="$2" logfile="$3"
    local subject committer_name committer_email author_name author_email
    local committer_date author_date commit_tz observing_tz hostname_val
    local capture_wall_epoch commit_epoch delta remotes_json dir

    subject="$(git -C "$root" log -1 --format='%s' "$sha")"
    if ! _match_bare_pattern "$subject"; then
        return 0
    fi

    committer_name="$(git -C "$root" log -1 --format='%cn' "$sha")"
    committer_email="$(git -C "$root" log -1 --format='%ce' "$sha")"
    author_name="$(git -C "$root" log -1 --format='%an' "$sha")"
    author_email="$(git -C "$root" log -1 --format='%ae' "$sha")"
    committer_date="$(git -C "$root" log -1 --format='%cI' "$sha")"
    author_date="$(git -C "$root" log -1 --format='%aI' "$sha")"
    commit_epoch="$(git -C "$root" log -1 --format='%ct' "$sha")"
    commit_tz="${committer_date: -5}"

    observing_tz="$(date +%z 2>/dev/null || echo "?")"
    hostname_val="$(hostname -f 2>/dev/null || hostname 2>/dev/null || echo "?")"
    capture_wall_epoch="$(date -u +%s)"
    delta=$(( capture_wall_epoch - commit_epoch ))

    remotes_json="$(_remotes_json "$root")"
    dir="$(cd "$root" && pwd)"

    mkdir -p "$(dirname "$logfile")"
    if [ ! -f "$logfile" ]; then
        {
            echo "# BOB-077 auto-commit forensic capture log (JSON-Lines, one record per detected occurrence)."
            echo "# Written by scripts/hooks/auto-commit-forensic-capture.sh — see that script's header"
            echo "# for the full mandate, known mechanism, and honest limitations (push-timing not measured)."
            echo "# Each non-comment line below is one JSON object. Lines beginning with # are comments,"
            echo "# never data — a consumer of this file skips lines matching ^#."
        } > "$logfile"
    fi

    {
        printf '{'
        printf '"captured_at":"%s",' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf '"commit_sha":"%s",' "$(_json_escape "$sha")"
        printf '"commit_subject":"%s",' "$(_json_escape "$subject")"
        printf '"pattern_matched":"%s",' "$(_json_escape "$MATCHED_PATTERN")"
        printf '"committer_name":"%s",' "$(_json_escape "$committer_name")"
        printf '"committer_email":"%s",' "$(_json_escape "$committer_email")"
        printf '"author_name":"%s",' "$(_json_escape "$author_name")"
        printf '"author_email":"%s",' "$(_json_escape "$author_email")"
        printf '"committer_date":"%s",' "$(_json_escape "$committer_date")"
        printf '"author_date":"%s",' "$(_json_escape "$author_date")"
        printf '"commit_timezone_offset":"%s",' "$(_json_escape "$commit_tz")"
        printf '"observing_host_timezone_offset":"%s",' "$(_json_escape "$observing_tz")"
        printf '"observing_hostname":"%s",' "$(_json_escape "$hostname_val")"
        printf '"observing_user":"%s",' "$(_json_escape "${USER:-$(whoami 2>/dev/null || echo '?')}")"
        printf '"observing_repo_dir":"%s",' "$(_json_escape "$dir")"
        printf '"capture_delta_seconds":%s,' "$delta"
        printf '"git_remotes":%s,' "$remotes_json"
        printf '"push_timing":"NOT_MEASURED — see script header: post-commit fires strictly before push; true push-completion time is not observable from this hook alone (see PUSH TIMING — HONEST LIMITATION)"'
        printf '}\n'
    } >> "$logfile"

    echo "[auto-commit-forensic-capture] recorded ${sha} (${subject}) -> ${logfile}" >&2
    return 0
}

if [ "${1:-}" = "--self-test" ]; then
    echo "[auto-commit-forensic-capture] §11.4.107(10) self-test — golden-good / golden-bad / field-completeness"
    TMPREPO="$(mktemp -d)"
    TMPLOG="$(mktemp -d)/forensic.jsonl"
    trap 'rm -rf "$TMPREPO" "$(dirname "$TMPLOG")"' EXIT
    git -C "$TMPREPO" init -q -b main
    git -C "$TMPREPO" config user.email "selftest@example.invalid"
    git -C "$TMPREPO" config user.name "Self Test"
    git -C "$TMPREPO" remote add origin "https://user:secrettoken@example.invalid/selftest/repo.git"
    git -C "$TMPREPO" remote add mirror "git@example.invalid:selftest/repo.git"

    FAILED=0

    # golden-good: a real, descriptive commit — no record written.
    git -C "$TMPREPO" commit -q --allow-empty -m "feat: add sync endpoint (ATM-001)"
    GOOD_SHA="$(git -C "$TMPREPO" rev-parse HEAD)"
    _capture_record "$GOOD_SHA" "$TMPREPO" "$TMPLOG"
    if [ ! -f "$TMPLOG" ]; then
        echo "  golden-good     PASS  (non-matching commit produced no log file at all)"
    else
        echo "  golden-good     FAIL  (§11.4.201(1) false positive — non-matching commit was recorded)" >&2
        FAILED=1
    fi

    # golden-bad #1: bare "Auto-commit" (the trailing-space-stripped shape).
    git -C "$TMPREPO" commit -q --allow-empty -m "Auto-commit"
    BAD1_SHA="$(git -C "$TMPREPO" rev-parse HEAD)"
    _capture_record "$BAD1_SHA" "$TMPREPO" "$TMPLOG"

    # golden-bad #2: epoch-suffixed "Auto-commit <ms>" (the commit-fully shape).
    git -C "$TMPREPO" commit -q --allow-empty -m "Auto-commit 1700000000000"
    BAD2_SHA="$(git -C "$TMPREPO" rev-parse HEAD)"
    _capture_record "$BAD2_SHA" "$TMPREPO" "$TMPLOG"

    RECORD_COUNT="$(grep -c '^{' "$TMPLOG" 2>/dev/null || echo 0)"
    if [ "$RECORD_COUNT" -eq 2 ]; then
        echo "  golden-bad      PASS  (both closed-pattern commits recorded, exactly 2 records)"
    else
        echo "  golden-bad      FAIL  (expected exactly 2 records; got ${RECORD_COUNT})" >&2
        FAILED=1
    fi

    # Field-completeness + credential-stripping + no-fabrication assertions
    # against the SECOND record (BAD2, epoch-suffixed).
    REC2="$(grep '^{' "$TMPLOG" | tail -1)"
    check_field() {
        local key="$1" expect_substr="$2" label="$3"
        if printf '%s' "$REC2" | grep -q "\"${key}\":\"[^\"]*${expect_substr}"; then
            echo "  field:${label}  PASS"
        else
            echo "  field:${label}  FAIL  (key '${key}' missing expected content '${expect_substr}')" >&2
            FAILED=1
        fi
    }
    check_field "commit_sha" "$BAD2_SHA" "commit_sha"
    check_field "commit_subject" "Auto-commit 1700000000000" "commit_subject"
    check_field "committer_email" "selftest@example.invalid" "committer_email"
    check_field "committer_name" "Self Test" "committer_name"
    check_field "pattern_matched" "" "pattern_matched-present"

    if printf '%s' "$REC2" | grep -q "secrettoken"; then
        echo "  credential-strip FAIL  (§11.4.10 — embedded basic-auth token leaked into forensic log)" >&2
        FAILED=1
    else
        echo "  credential-strip PASS  (embedded basic-auth token stripped from logged remote URL)"
    fi
    if printf '%s' "$REC2" | grep -q '"name":"origin"' && printf '%s' "$REC2" | grep -q '"name":"mirror"'; then
        echo "  field:git_remotes PASS  (both configured remotes present)"
    else
        echo "  field:git_remotes FAIL  (expected both 'origin' and 'mirror' remote entries)" >&2
        FAILED=1
    fi
    if printf '%s' "$REC2" | grep -q '"push_timing":"NOT_MEASURED'; then
        echo "  field:push_timing PASS  (honestly labelled NOT_MEASURED, never fabricated)"
    else
        echo "  field:push_timing FAIL  (push_timing field missing or not honestly labelled)" >&2
        FAILED=1
    fi

    # Idempotence / no-corruption: capturing an ALREADY-non-matching commit
    # again must not touch the log.
    _capture_record "$GOOD_SHA" "$TMPREPO" "$TMPLOG"
    RECORD_COUNT_AFTER="$(grep -c '^{' "$TMPLOG" 2>/dev/null || echo 0)"
    if [ "$RECORD_COUNT_AFTER" -eq 2 ]; then
        echo "  idempotence      PASS  (re-scanning a non-matching commit added no new record)"
    else
        echo "  idempotence      FAIL  (record count changed: ${RECORD_COUNT} -> ${RECORD_COUNT_AFTER})" >&2
        FAILED=1
    fi

    if [ "$FAILED" -eq 1 ]; then
        echo "[auto-commit-forensic-capture] self-test FAILED"
        exit 1
    fi
    echo "[auto-commit-forensic-capture] self-test PASS — capture validated in both polarities + field completeness"
    exit 0
fi

SHA="${1:-HEAD}"
_capture_record "$SHA" "$REPO_ROOT" "$LOG_FILE"
exit 0
