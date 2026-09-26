#!/usr/bin/env bash
# FR-006 (review finding I-6): verify-closure re-runs the recorded command in a
# FRESH process with cwd = repository root -- never `eval`ed inside the audit's
# own shell, where it would inherit set -u, internal functions and variables,
# and the caller's cwd. Also covers m4: the corruption-incident log lives under
# the AUDIT_QA_ROOT tree (or AUDIT_INCIDENT_LOG_DIR), never always under the
# real repo's docs/qa. The m4 cases run a COPY of the script inside a throwaway
# git repository, so an injected corruption can never touch this project's own
# tracked evidence.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
repo="$(pwd)"

pass=0
fail=0
check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"; pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"; fail=$((fail + 1))
    fi
}

qa="$repo/tests/audit/fixtures/docs_qa_fixture"
run_vc() { # cwd item -> "rc|output"
    local cwd="$1" item="$2" out rc=0
    out="$(cd "$cwd" && AUDIT_QA_ROOT="$qa" bash "$repo/scripts/zero_shortcomings_audit.sh" verify-closure "$item" 2>&1)" || rc=$?
    printf '%s|%s' "$rc" "$out"
}

r="$(run_vc "$repo" BOB-FIXTURE-FRESH-PROCESS)"
printf '    fresh-process: %s\n' "$(printf '%s' "$r" | tr '\n' ' ')"
check "I-6 the recorded command sees no audit-internal variable, function or set -u (exit 0)" \
    '[[ "${r%%|*}" == 0 ]]'

r_root="$(run_vc "$repo" BOB-FIXTURE-CWD)"
r_elsewhere="$(run_vc / BOB-FIXTURE-CWD)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
r_tmp="$(run_vc "$work" BOB-FIXTURE-CWD)"
printf '    cwd from repo root: %s\n' "${r_root%%|*}"
printf '    cwd from /:         %s\n' "${r_elsewhere%%|*}"
printf '    cwd from a tmp dir: %s\n' "${r_tmp%%|*}"
check "I-6 invoked from the repo root, the cwd-sensitive command matches" '[[ "${r_root%%|*}" == 0 ]]'
check "I-6 invoked from /, the result is the same (cwd is the repo root)" '[[ "${r_elsewhere%%|*}" == 0 ]]'
check "I-6 invoked from a throwaway dir, the result is the same" '[[ "${r_tmp%%|*}" == 0 ]]'

# --- m4: incident log location, in a throwaway repo copy -------------------
sb="$work/sandbox"
mkdir -p "$sb/scripts/lib" "$sb/docs/qa/BOB-OTHER"
cp "$repo/scripts/zero_shortcomings_audit.sh" "$sb/scripts/"
cp "$repo"/scripts/lib/audit_*.sh "$sb/scripts/lib/"
(
    cd "$sb"
    git init -q .
    git config user.email t@t.invalid; git config user.name t
    echo "other original" > docs/qa/BOB-OTHER/closure_evidence_1.md
    git add -A && git commit -q -m seed
)
alt="$work/alt_qa"
mkdir -p "$alt/BOB-CORRUPTER"
cat > "$alt/BOB-CORRUPTER/closure_evidence_1.md" <<'MD'
**Command:** `echo corrupt > docs/qa/BOB-OTHER/closure_evidence_1.md; echo '1 passed, 0 failed'`
**Result Summary:** 1 passed, 0 failed
**Evidence Layer:** runtime
**Test Type:** unit
MD
m4rc=0
m4out="$(cd "$sb" && AUDIT_QA_ROOT="$alt" bash scripts/zero_shortcomings_audit.sh verify-closure BOB-CORRUPTER 2>&1)" || m4rc=$?
printf '    m4 output: %s\n' "$(printf '%s' "$m4out" | tr '\n' ' ')"
check "m4 the corruption was reverted in the sandbox repo" \
    '[[ "$(cat "$sb/docs/qa/BOB-OTHER/closure_evidence_1.md")" == "other original" ]]'
check "m4 the incident log is written under the AUDIT_QA_ROOT tree" \
    'compgen -G "$alt/zero_shortcomings_audit/*.log" >/dev/null'
check "m4 no incident log is written under the repo's own docs/qa" \
    '[[ ! -d "$sb/docs/qa/zero_shortcomings_audit" ]]'

# AUDIT_INCIDENT_LOG_DIR override, plus an end-to-end DELETION (I-2(a)).
sed -i 's#^\*\*Command:\*\* .*#**Command:** `rm docs/qa/BOB-OTHER/closure_evidence_1.md; echo '"'"'1 passed, 0 failed'"'"'`#' \
    "$alt/BOB-CORRUPTER/closure_evidence_1.md"
over="$work/incident_override"
(cd "$sb" && AUDIT_QA_ROOT="$alt" AUDIT_INCIDENT_LOG_DIR="$over" bash scripts/zero_shortcomings_audit.sh verify-closure BOB-CORRUPTER >/dev/null 2>&1) || true
check "m4 AUDIT_INCIDENT_LOG_DIR overrides the incident log location" \
    'compgen -G "$over/*.log" >/dev/null && grep -q "docs/qa/BOB-OTHER/closure_evidence_1.md" "$over"/*.log'
check "I-2(a) end-to-end: a file DELETED by the recorded command is restored" \
    '[[ "$(cat "$sb/docs/qa/BOB-OTHER/closure_evidence_1.md" 2>/dev/null)" == "other original" ]]'
check "the real repo's docs/qa gained no incident log from this test" \
    '[[ -z "$(git -C "$repo" status --porcelain -- docs/qa)" ]]'

printf 'test_zero_shortcomings_audit_fresh_process: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
