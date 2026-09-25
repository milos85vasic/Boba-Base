#!/usr/bin/env bash
# test_auto_commit_forensic_capture.sh — Hermetic executing test for BOB-077's
# forensic-capture instrument (scripts/hooks/auto-commit-forensic-capture.sh).
#
# Drives the REAL invocation path — not a `bash -n` parse-check
# (§11.4.224(A)): asserts on the script's real exit status + stdout via its
# own --self-test, AND independently drives the PUBLIC `<sha>` interface
# against a hermetic temp repo + a redirected AUTO_COMMIT_FORENSIC_LOG path
# (never the real repo's tracked log), parsing the emitted JSON-Lines record
# with a dependency-free field extractor to assert on actual field VALUES
# (state-delta assertions, §11.4.238), not merely "a file got created".
#
# §1.1 — Paired meta-test mutation: neuter the bare-pattern match in the
# script (comment out the `_match_bare_pattern` return-0 branch) -> its own
# --self-test flips to FAIL (golden-bad no longer records) -> restore ->
# re-assert GREEN. Proven manually during authoring; recorded in
# docs/qa/BOB-077/investigation_20260925.md.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
CAPTURE="${PROJECT_ROOT}/scripts/hooks/auto-commit-forensic-capture.sh"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

# Dependency-free extractor for a top-level string field's value out of a
# single-line JSON object — good enough for this script's own flat,
# non-nested string/number fields (never trusted for arbitrary JSON).
json_field() {
    local json="$1" key="$2"
    printf '%s' "$json" | sed -n "s/.*\"${key}\":\"\\([^\"]*\\)\".*/\\1/p"
}

if [[ ! -x "${CAPTURE}" ]]; then
    echo "FATAL: capture script missing or not executable at ${CAPTURE}" >&2
    exit 2
fi

# --- 1: bash -n parse sanity (necessary, never sufficient per §11.4.224(A)) ---
if bash -n "${CAPTURE}"; then
    pass "capture script is syntactically valid bash"
else
    fail "capture script fails bash -n"
fi

# --- 2: real invocation, --self-test polarity (golden-good + golden-bad +
#     field-completeness + credential-stripping + idempotence, all defined
#     inside the script's own --self-test) ---
SELFTEST_OUT="$(bash "${CAPTURE}" --self-test 2>&1)"
SELFTEST_EXIT=$?
if [[ "${SELFTEST_EXIT}" -eq 0 ]]; then
    pass "capture --self-test exits 0 on unmutated source"
else
    fail "capture --self-test exited ${SELFTEST_EXIT} on unmutated source (expected 0): ${SELFTEST_OUT}"
fi
for line in "golden-good     PASS" "golden-bad      PASS" "credential-strip PASS" "field:git_remotes PASS" "field:push_timing PASS" "idempotence      PASS"; do
    if echo "${SELFTEST_OUT}" | grep -qF "${line}"; then
        pass "self-test line present: ${line}"
    else
        fail "self-test line missing/not-PASS: '${line}' — full output: ${SELFTEST_OUT}"
    fi
done

# --- 3: real invocation against a hermetic temp repo via the PUBLIC
#     `<sha>` interface (not just --self-test), parsing actual field
#     VALUES out of the emitted record. ---
TMPREPO="$(mktemp -d)"
TMPLOGDIR="$(mktemp -d)"
TMPLOG="${TMPLOGDIR}/forensic.jsonl"
_cleanup_tmp() { rm -rf "${TMPREPO}" "${TMPLOGDIR}" 2>/dev/null || true; }
trap _cleanup_tmp EXIT

git -C "${TMPREPO}" init -q -b main
git -C "${TMPREPO}" config user.email "bob077-test@example.invalid"
git -C "${TMPREPO}" config user.name "Bob077 Tester"
git -C "${TMPREPO}" remote add origin "git@example.invalid:bob077/test.git"

# 3a: a real, descriptive commit produces NO record (golden-good, real
#     interface, not just self-test).
git -C "${TMPREPO}" commit -q --allow-empty -m "feat: real work (ATM-777)"
GOOD_SHA="$(git -C "${TMPREPO}" rev-parse HEAD)"
(cd "${TMPREPO}" && AUTO_COMMIT_FORENSIC_LOG="${TMPLOG}" bash "${CAPTURE}" "${GOOD_SHA}") >/dev/null 2>&1
if [[ ! -f "${TMPLOG}" ]]; then
    pass "real invocation on a descriptive commit writes no log file"
else
    fail "real invocation on a descriptive commit unexpectedly created a log file (§11.4.201(1) false positive)"
fi

# 3b: a genuinely bare "Auto-commit" commit (the exact RD2-00 shape) IS
#     recorded, with real field values matching the real commit metadata.
git -C "${TMPREPO}" commit -q --allow-empty -m "Auto-commit"
BARE_SHA="$(git -C "${TMPREPO}" rev-parse HEAD)"
REAL_COMMITTER_EMAIL="$(git -C "${TMPREPO}" log -1 --format='%ce' "${BARE_SHA}")"
(cd "${TMPREPO}" && AUTO_COMMIT_FORENSIC_LOG="${TMPLOG}" bash "${CAPTURE}" "${BARE_SHA}") >/dev/null 2>&1

if [[ -f "${TMPLOG}" ]] && grep -q '^{' "${TMPLOG}"; then
    pass "bare 'Auto-commit' commit produces a log record via the real invocation path"
else
    fail "bare 'Auto-commit' commit produced no log record (state-delta assertion failed)"
fi

RECORD="$(grep '^{' "${TMPLOG}" | tail -1)"
EXTRACTED_SHA="$(json_field "${RECORD}" "commit_sha")"
EXTRACTED_EMAIL="$(json_field "${RECORD}" "committer_email")"
EXTRACTED_SUBJECT="$(json_field "${RECORD}" "commit_subject")"
EXTRACTED_REMOTE_NAME="$(printf '%s' "${RECORD}" | grep -oE '"name":"[^"]*"' | head -1 | sed -n 's/.*:"\(.*\)"/\1/p')"

if [[ "${EXTRACTED_SHA}" == "${BARE_SHA}" ]]; then
    pass "recorded commit_sha matches the actual commit SHA (not fabricated)"
else
    fail "recorded commit_sha '${EXTRACTED_SHA}' != actual '${BARE_SHA}'"
fi
if [[ "${EXTRACTED_EMAIL}" == "${REAL_COMMITTER_EMAIL}" ]]; then
    pass "recorded committer_email matches real git metadata (not fabricated)"
else
    fail "recorded committer_email '${EXTRACTED_EMAIL}' != real '${REAL_COMMITTER_EMAIL}'"
fi
if [[ "${EXTRACTED_SUBJECT}" == "Auto-commit" ]]; then
    pass "recorded commit_subject is the exact bare pattern"
else
    fail "recorded commit_subject '${EXTRACTED_SUBJECT}' != 'Auto-commit'"
fi
if [[ "${EXTRACTED_REMOTE_NAME}" == "origin" ]]; then
    pass "recorded git_remotes reflects the real configured remote ('origin')"
else
    fail "recorded git_remotes first entry '${EXTRACTED_REMOTE_NAME}' != 'origin'"
fi

# --- 4: the real repo's own installed post-commit hook (if any) wires this
#     script — check the WIRING is present in the tracked hook source,
#     without invoking a real commit against the real repo (forbidden by
#     this task's scope — commits are simulated only in the temp repo
#     above). ---
POST_COMMIT_SRC="${PROJECT_ROOT}/scripts/git_hooks/post-commit"
if [[ -f "${POST_COMMIT_SRC}" ]] && grep -q "auto-commit-forensic-capture.sh" "${POST_COMMIT_SRC}"; then
    pass "scripts/git_hooks/post-commit is wired to invoke auto-commit-forensic-capture.sh"
else
    fail "scripts/git_hooks/post-commit does NOT reference auto-commit-forensic-capture.sh — wiring missing"
fi
if bash -n "${POST_COMMIT_SRC}"; then
    pass "scripts/git_hooks/post-commit remains syntactically valid bash after the wiring edit"
else
    fail "scripts/git_hooks/post-commit fails bash -n after the wiring edit"
fi

echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi
exit 0
