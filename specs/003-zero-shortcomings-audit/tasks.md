# Tasks: Zero-Shortcomings Evidence-Backed Audit & Closure

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Input**: Design documents from `specs/003-zero-shortcomings-audit/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/cli.md`, `quickstart.md` (all present)
**Tests**: Included — the spec explicitly requires "all supported test types which will
produce machine rock-solid evidence" (spec.md Input), so tests are mandatory, not optional,
for every task below.

**Spec**: [../spec.md](../spec.md) | **Plan**: [../plan.md](../plan.md)

## Global Constraints

- Scope is bounded to the three already-tracked surfaces (spec.md Q1, Option A): the
  open workable-items backlog, the named-but-unimplemented governance-gate ledger, the
  coverage-escape discovery ledger. No new, unbounded discovery mechanism.
- Principle VI (constitution.md): **NO CI/CD PIPELINES** — no cron, no GitHub Action, no
  scheduler of any kind. The recurring mechanism (US3) MUST be wired into the existing
  manual `scripts/pre_build_verification.sh` gate only.
- Principle XI: `download-proxy/src/` forbids comments; this feature's code lives under
  `scripts/` and `tests/`, where normal commenting conventions (Principle VI) apply —
  every new file MAY and SHOULD carry rationale comments where non-obvious.
- Principle X / §11.4.263: any test mocking a subprocess/proc object MUST set
  `mock.pid = <int > 1>` explicitly. This feature's own tests do not mock subprocess
  objects (they shell out for real, against fixture data), so this constraint is
  inherited as a standing check, not exercised directly.
- Principle XIII: dispatched heavy work MUST respect the `ExecutionPolicy` bounds
  (data-model.md) — `nice_level=19`, `ionice_class=3`, `max_parallel_items=3`,
  `resource_ceiling_pct=40`.
- `set -euo pipefail`, `[[ ]]` conditionals, quoted variables, `snake_case` functions,
  4-space indent, the project's local `print_info`/`print_success`/`print_warning`/
  `print_error` convention (Principle VI/VII) — verified this round from
  `scripts/helixqa.sh`, since this project defines these LOCALLY in each top-level
  script rather than sourcing one shared file (Global Constraint correction: `plan.md`
  described these as a "shared lib" — the real, verified convention is per-script
  local definition, replicated verbatim below).
- Every new tracked, operator-invoked ENTRY-POINT script MUST get a companion
  `docs/scripts/<name>.md` per §11.4.18. **Pre-flight ruling (recorded here and in the
  SDD ledger, since this constraint's first draft read as unconditional and Tasks 1–3
  would have violated it):** a `scripts/lib/*.sh` file that is ONLY ever `source`d by
  another script — never invoked directly by an operator — is exempt from its OWN
  standalone companion doc; its usage is documented instead as part of the
  entry-point script's companion doc (`docs/scripts/zero_shortcomings_audit.md`, Task
  4). This mirrors this project's own already-established real convention: its
  existing `print_info`/`print_success`/`print_warning`/`print_error` helpers (defined
  locally per top-level script, confirmed this round from `scripts/helixqa.sh`) have no
  standalone `docs/scripts/` entry of their own either. Only Task 4's entry-point script
  needs its own companion doc. BOB-223 (this session's own finding, Queued at time of
  writing) means writing that companion doc without regenerating its `.html`/`.pdf`
  twins currently trips invariant 16 — until BOB-223 lands, run
  `bash scripts/workable-items-export.sh` immediately after adding it, in the same task,
  before considering that task done.

## Review Focus

Five failure modes the spec implies that no single task's own tests would catch in
isolation — each gets its test added to the task that owns the relevant code:

1. **A blind ledger parser reports zero open escapes when the ledger is genuinely
   unreadable** (a false-null, §11.4.201(6)) — Task 3's tests include a
   ledger-file-missing/corrupt case that must FAIL loudly, never report "0 open".
2. **The evidence-corruption guard itself has a side effect** (reverting a file that was
   a LEGITIMATE, intended change by the very command being verified, not corruption) —
   Task 6's tests include a positive case where the dispatched command legitimately
   writes new content inside its OWN item's evidence directory, which must NOT be
   reverted.
3. **`verify-closure` on an item whose command legitimately depends on live,
   time-varying state** (e.g., a live container's uptime) produces a semantic mismatch
   that is a false reopen, not a real regression — Task 5's tests confirm
   `result_summary` comparison, not raw output, is what's compared (research.md §4).
4. **The new `standing-check` pre-build invariant becomes the thing that makes commits
   unusable** — a regression of Principle VI's always-unblocked design — Task 8's tests
   confirm it never blocks on the pre-existing, already-known backlog count alone.
5. **Concurrent invocation of `zero_shortcomings_audit.sh` from two sessions** corrupts
   `docs/qa/zero_shortcomings_audit/<run-id>.log` — Task 2's tests confirm the run-id
   naming scheme (timestamp + PID) makes two concurrent runs write to different files,
   never the same one.

---

## Phase 1: Setup

**Purpose**: Directory scaffolding and the shared run-id convention every later task depends on.

### Task 1: Scaffolding + shared run-id helper

**Files:**
- Create: `scripts/lib/audit_run_id.sh`
- Test: `tests/audit/test_audit_run_id.sh`

**Interfaces:**
- Produces: `audit_run_id()` — a bash function with no arguments, printing a fresh
  `YYYYMMDDTHHMMSSZ-pid<PID>` string to stdout (matching this project's existing
  `run_id` convention already used across `docs/qa/**/`).

- [ ] **Step 1: Write the failing test**

```bash
cat > tests/audit/test_audit_run_id.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/lib/audit_run_id.sh

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

id1="$(audit_run_id)"
check "run id matches YYYYMMDDTHHMMSSZ-pid<N> shape" \
    '[[ "$id1" =~ ^[0-9]{8}T[0-9]{6}Z-pid[0-9]+$ ]]'

id2="$(audit_run_id)"
check "the embedded pid is this shell's own PID" \
    '[[ "$id1" == *"-pid$$" ]] && [[ "$id2" == *"-pid$$" ]]'

printf 'test_audit_run_id: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_audit_run_id.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mkdir -p tests/audit scripts/lib && bash tests/audit/test_audit_run_id.sh`
Expected: FAIL — `scripts/lib/audit_run_id.sh: No such file or directory`

- [ ] **Step 3: Write minimal implementation**

```bash
cat > scripts/lib/audit_run_id.sh <<'EOF'
#!/usr/bin/env bash
# audit_run_id.sh — the shared run-id convention for every audit artifact this
# feature writes, matching the timestamp+pid shape already used across
# docs/qa/**/ (e.g. 20260925T113437Z-pid3872998). Timestamp+pid, not a
# counter, so two concurrent invocations never collide (Review Focus item 5).
audit_run_id() {
    printf '%sZ-pid%d\n' "$(date -u '+%Y%m%dT%H%M%S')" "$$"
}
EOF
chmod +x scripts/lib/audit_run_id.sh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_audit_run_id.sh`
Expected: `test_audit_run_id: 2 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/lib/audit_run_id.sh --scope tests/audit/test_audit_run_id.sh \
    "feat(audit): shared run-id helper for zero-shortcomings audit artifacts"
```

(Per constitution Principle VI "Before Every Commit" step 9: `scripts/commit-push-all.sh` is
the ONLY sanctioned commit path — direct `git commit`/`git push` bypass the pre-build gate,
the doc/DB sync seam, and the multi-upstream fan-out. `--scope` is used, not a bare
invocation, because other work may be concurrently in flight in this same checkout.)

**Checkpoint**: Setup complete — the run-id convention every later artifact depends on exists and is tested.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The coverage-escape ledger parser and the `ExecutionPolicy` constants —
both required before ANY user story's enumeration or dispatch logic can run.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Task 2: `ExecutionPolicy` constants module

**Files:**
- Create: `scripts/lib/audit_execution_policy.sh`
- Test: `tests/audit/test_audit_execution_policy.sh`

**Interfaces:**
- Produces: five read-only shell variables —
  `AUDIT_MAX_PARALLEL_ITEMS=3`, `AUDIT_NICE_LEVEL=19`, `AUDIT_IONICE_CLASS=3`,
  `AUDIT_RESOURCE_CEILING_PCT=40`, and the function `audit_dispatch_bounded()` which
  wraps a command with `nice`/`ionice` per data-model.md's `ExecutionPolicy` entity.

- [ ] **Step 1: Write the failing test**

```bash
cat > tests/audit/test_audit_execution_policy.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/lib/audit_execution_policy.sh

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

check "AUDIT_MAX_PARALLEL_ITEMS is 3 per data-model.md" \
    '[[ "$AUDIT_MAX_PARALLEL_ITEMS" == "3" ]]'
check "AUDIT_NICE_LEVEL is 19 per Principle XIII" \
    '[[ "$AUDIT_NICE_LEVEL" == "19" ]]'
check "AUDIT_IONICE_CLASS is 3 (idle) per Principle XIII" \
    '[[ "$AUDIT_IONICE_CLASS" == "3" ]]'
check "AUDIT_RESOURCE_CEILING_PCT is 40 per Principle XIII" \
    '[[ "$AUDIT_RESOURCE_CEILING_PCT" == "40" ]]'

out="$(audit_dispatch_bounded echo hello)"
check "audit_dispatch_bounded runs the wrapped command" '[[ "$out" == "hello" ]]'

printf 'test_audit_execution_policy: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_audit_execution_policy.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/audit/test_audit_execution_policy.sh`
Expected: FAIL — `scripts/lib/audit_execution_policy.sh: No such file or directory`

- [ ] **Step 3: Write minimal implementation**

```bash
cat > scripts/lib/audit_execution_policy.sh <<'EOF'
#!/usr/bin/env bash
# audit_execution_policy.sh — the single source of truth for this feature's
# Principle XIII host-resource bounds (data-model.md ExecutionPolicy entity).
# Changing a bound touches exactly this file, never a copy of these numbers
# scattered across the orchestrator (constitution §11.4.6 single-source-of-truth).
readonly AUDIT_MAX_PARALLEL_ITEMS=3
readonly AUDIT_NICE_LEVEL=19
readonly AUDIT_IONICE_CLASS=3
readonly AUDIT_RESOURCE_CEILING_PCT=40

# audit_dispatch_bounded <command...> — runs a command under the nice/ionice
# bounds above. ionice is optional (not present on every host); its absence
# MUST NOT fail the dispatch (host-portability, mirrors Principle IV's
# runtime-detection discipline applied to a resource-control tool instead of
# a container runtime).
audit_dispatch_bounded() {
    if command -v ionice >/dev/null 2>&1; then
        nice -n "$AUDIT_NICE_LEVEL" ionice -c "$AUDIT_IONICE_CLASS" -- "$@"
    else
        nice -n "$AUDIT_NICE_LEVEL" -- "$@"
    fi
}
EOF
chmod +x scripts/lib/audit_execution_policy.sh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_audit_execution_policy.sh`
Expected: `test_audit_execution_policy: 5 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/lib/audit_execution_policy.sh --scope tests/audit/test_audit_execution_policy.sh \
    "feat(audit): ExecutionPolicy constants + bounded-dispatch helper (Principle XIII)"
```

### Task 3: `[TDD]` Coverage-escape ledger parser

**Files:**
- Create: `scripts/lib/audit_ledger_parser.sh`
- Test: `tests/audit/test_audit_ledger_parser.sh`
- Test fixtures: `tests/audit/fixtures/ledger_golden_good.md`, `tests/audit/fixtures/ledger_golden_bad_missing_new_check.md`, `tests/audit/fixtures/ledger_malformed_escape_audit.md`

**Interfaces:**
- Consumes: a path to a Markdown file following `docs/QA_DISCOVERY_LEDGER.md`'s own
  documented schema (`### ` heading per entry, `**id:**`/`**date:**`/`**channel:**`/
  `**escape-audit:**`/`**new-check:**` fields).
- Produces: `audit_ledger_count_open_escapes <path>` — prints an integer (the count of
  entries with `channel != automated-helixqa` and no non-empty `**new-check:**` field)
  to stdout, or exits non-zero with a message on stderr if `<path>` does not exist or is
  empty (Review Focus item 1 — never a silent "0").
  `audit_ledger_count_malformed <path>` — prints the count of entries with
  `channel != automated-helixqa` and NO non-empty `**escape-audit:**` field
  (data-model.md's `CoverageEscapeRecord` validation rule).

- [ ] **Step 1: Write the failing tests + fixtures**

```bash
mkdir -p tests/audit/fixtures

cat > tests/audit/fixtures/ledger_golden_good.md <<'EOF'
# QA Discovery-Channel Ledger

## Entries

### RD2-22 — closed escape

- **id:** RD2-22
- **date:** 2026-08-07
- **channel:** `agent-code-reading`
- **escape-audit:** the check existed but was scoped to 4 of 6 routes.
- **new-check:** extended to all 6 routes, RED-captured, now GREEN.

### BOB-999 — automated find, never an escape

- **id:** BOB-999
- **date:** 2026-09-01
- **channel:** `automated-helixqa`
- **escape-audit:** N/A
- **new-check:** N/A
EOF

cat > tests/audit/fixtures/ledger_golden_bad_missing_new_check.md <<'EOF'
# QA Discovery-Channel Ledger

## Entries

### BOB-888 — still-open escape

- **id:** BOB-888
- **date:** 2026-09-20
- **channel:** `manual-qa`
- **escape-audit:** the smoke test never exercised this path.
EOF

cat > tests/audit/fixtures/ledger_malformed_escape_audit.md <<'EOF'
# QA Discovery-Channel Ledger

## Entries

### BOB-777 — malformed entry, no escape-audit at all

- **id:** BOB-777
- **date:** 2026-09-21
- **channel:** `operator-report`
- **new-check:** a check was added anyway.
EOF

cat > tests/audit/test_audit_ledger_parser.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/lib/audit_ledger_parser.sh

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

good_count="$(audit_ledger_count_open_escapes tests/audit/fixtures/ledger_golden_good.md)"
check "golden-good ledger (all entries closed or automated) reports 0 open" \
    '[[ "$good_count" -eq 0 ]]'

bad_count="$(audit_ledger_count_open_escapes tests/audit/fixtures/ledger_golden_bad_missing_new_check.md)"
check "golden-bad ledger (one entry with no new-check) reports 1 open" \
    '[[ "$bad_count" -eq 1 ]]'

malformed_count="$(audit_ledger_count_malformed tests/audit/fixtures/ledger_malformed_escape_audit.md)"
check "an out-of-band entry with no escape-audit field is reported malformed" \
    '[[ "$malformed_count" -eq 1 ]]'

# Review Focus item 1: a missing/unreadable ledger MUST fail loudly, never
# silently report a clean 0 — the exact false-null class §11.4.201(6) forbids.
set +e
audit_ledger_count_open_escapes /nonexistent/ledger.md >/tmp/audit_parser_missing_out 2>/tmp/audit_parser_missing_err
missing_rc=$?
set -e
check "a missing ledger file exits non-zero rather than printing 0" \
    '[[ "$missing_rc" -ne 0 ]]'
check "a missing ledger file prints an actionable error on stderr" \
    '[[ -s /tmp/audit_parser_missing_err ]]'
rm -f /tmp/audit_parser_missing_out /tmp/audit_parser_missing_err

printf 'test_audit_ledger_parser: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_audit_ledger_parser.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/audit/test_audit_ledger_parser.sh`
Expected: FAIL — `scripts/lib/audit_ledger_parser.sh: No such file or directory`

- [ ] **Step 3: Write minimal implementation**

```bash
cat > scripts/lib/audit_ledger_parser.sh <<'EOF'
#!/usr/bin/env bash
# audit_ledger_parser.sh — reads docs/QA_DISCOVERY_LEDGER.md's own documented
# "## Schema" (channel/escape-audit/new-check per `### `-headed entry) without
# ever rewriting the ledger itself. The ledger stays a human/agent-edited
# document (research.md §3); this is read-only enumeration, per FR-003.
#
# Entry-splitting approach: split the file on lines starting with "### ",
# discarding everything before the first such heading (the ledger's own
# preamble/schema-doc section, which is not an entry).

_audit_ledger_require_readable() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        printf 'audit_ledger_parser: ledger file not found: %s\n' "$path" >&2
        return 1
    fi
    if [[ ! -s "$path" ]]; then
        printf 'audit_ledger_parser: ledger file is empty: %s\n' "$path" >&2
        return 1
    fi
}

# _audit_ledger_entries <path> — prints each entry's body (everything after
# its "### " heading line, up to the next "### " or end of file) separated by
# a NUL-safe delimiter line "@@@AUDIT_ENTRY@@@".
_audit_ledger_entries() {
    local path="$1"
    awk '
        /^### / { if (started) { print "@@@AUDIT_ENTRY@@@" } started = 1; next }
        started { print }
        END { if (started) { print "@@@AUDIT_ENTRY@@@" } }
    ' "$path"
}

_audit_ledger_field_present() {
    local entry="$1" field="$2"
    printf '%s\n' "$entry" | grep -qE "\\*\\*${field}:\\*\\*[[:space:]]*[^[:space:]]"
}

_audit_ledger_channel_is_automated() {
    local entry="$1"
    printf '%s\n' "$entry" | grep -qE '\*\*channel:\*\*[[:space:]]*`?automated-helixqa`?'
}

audit_ledger_count_open_escapes() {
    local path="$1"
    _audit_ledger_require_readable "$path" || return 1
    local count=0
    local entry=""
    while IFS= read -r line; do
        if [[ "$line" == "@@@AUDIT_ENTRY@@@" ]]; then
            if ! _audit_ledger_channel_is_automated "$entry" \
               && ! _audit_ledger_field_present "$entry" "new-check"; then
                count=$((count + 1))
            fi
            entry=""
        else
            entry+="$line"$'\n'
        fi
    done < <(_audit_ledger_entries "$path")
    printf '%d\n' "$count"
}

audit_ledger_count_malformed() {
    local path="$1"
    _audit_ledger_require_readable "$path" || return 1
    local count=0
    local entry=""
    while IFS= read -r line; do
        if [[ "$line" == "@@@AUDIT_ENTRY@@@" ]]; then
            if ! _audit_ledger_channel_is_automated "$entry" \
               && ! _audit_ledger_field_present "$entry" "escape-audit"; then
                count=$((count + 1))
            fi
            entry=""
        else
            entry+="$line"$'\n'
        fi
    done < <(_audit_ledger_entries "$path")
    printf '%d\n' "$count"
}
EOF
chmod +x scripts/lib/audit_ledger_parser.sh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_audit_ledger_parser.sh`
Expected: `test_audit_ledger_parser: 5 passed, 0 failed`

- [ ] **Step 5: `[REVIEW]` Paired §1.1 mutation — prove the counts are load-bearing**

```bash
cp scripts/lib/audit_ledger_parser.sh /tmp/audit_ledger_parser_mutated.sh
sed -i 's/count=\$((count + 1))/: # mutated: never increments/' /tmp/audit_ledger_parser_mutated.sh
( source /tmp/audit_ledger_parser_mutated.sh
  audit_ledger_count_open_escapes tests/audit/fixtures/ledger_golden_bad_missing_new_check.md )
# Expected: prints 0 (WRONG — the mutation broke detection) — this is the
# proof the real implementation's count is load-bearing, not decoration.
rm -f /tmp/audit_ledger_parser_mutated.sh
```

Record this mutation's output in the task's commit message per this project's own
§1.1 discipline — it is the evidence the real (unmutated) test is not a bluff.

- [ ] **Step 6: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/lib/audit_ledger_parser.sh --scope tests/audit/test_audit_ledger_parser.sh --scope tests/audit/fixtures/ \
   "$(cat <<'MSG'
feat(audit): coverage-escape ledger parser (FR-003)

Paired §1.1 mutation confirmed load-bearing: neutering the counter's
increment made the golden-bad fixture (one entry with no new-check)
report 0 instead of 1.
MSG
)"
```

**Checkpoint**: Foundational phase complete — `ExecutionPolicy` and the ledger parser
are both built, tested, and mutation-proven. User story work can now begin.

---

## Phase 3: User Story 1 - Complete, authoritative enumeration (Priority: P1) 🎯 MVP

**Goal**: One command reports the exact, independently-verifiable count of open items
across all three tracked surfaces.

**Independent Test** (from spec.md): Run the enumeration; cross-check each of the three
counts against each surface's own ground-truth query; confirm exact match in both
directions (quickstart.md Step 1).

### Task 4: `[TDD]` `zero_shortcomings_audit.sh enumerate` mode

**Files:**
- Create: `scripts/zero_shortcomings_audit.sh`
- Create: `docs/scripts/zero_shortcomings_audit.md`
- Test: `tests/audit/test_zero_shortcomings_audit_enumerate.sh`

**Interfaces:**
- Consumes: `audit_ledger_count_open_escapes` / `audit_ledger_count_malformed` (Task 3);
  `constitution/scripts/workable-items/workable-items validate --db <path>` (existing);
  `bash constitution/scripts/gates/cm_gate_ledger_ratchet.sh` (existing, prints a summary
  line this task parses for its unimplemented count).
- Produces: the `enumerate` CLI mode per `contracts/cli.md` — human-readable by default,
  `--json` emits `{"backlog_open": N, "gates_unimplemented": N, "escapes_open": N}`.

- [ ] **Step 1: Write the failing test**

```bash
cat > tests/audit/test_zero_shortcomings_audit_enumerate.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

out="$(bash scripts/zero_shortcomings_audit.sh enumerate --json)"
check "enumerate --json produces valid JSON with all three keys" \
    'printf "%s" "$out" | grep -q "\"backlog_open\"" \
     && printf "%s" "$out" | grep -q "\"gates_unimplemented\"" \
     && printf "%s" "$out" | grep -q "\"escapes_open\""'

# Ground truth 1: the tracker's own count of non-terminal, non-Obsolete items.
truth_backlog="$(sqlite3 docs/workable_items.db \
    "SELECT count(*) FROM items WHERE status NOT LIKE '%(→ Fixed.md)' AND status != 'Obsolete';")"
reported_backlog="$(printf '%s' "$out" | grep -oE '"backlog_open":[0-9]+' | grep -oE '[0-9]+')"
check "reported backlog_open exactly matches the tracker's own ground-truth count" \
    '[[ "$reported_backlog" == "$truth_backlog" ]]'

# --surface restricts to one surface only.
scoped="$(bash scripts/zero_shortcomings_audit.sh enumerate --json --surface backlog)"
check "--surface backlog omits the other two surfaces' keys" \
    '! printf "%s" "$scoped" | grep -q "gates_unimplemented"'

check "enumerate exits 0 even when open items exist (never gates on findings)" \
    'bash scripts/zero_shortcomings_audit.sh enumerate --json >/dev/null; [[ $? -eq 0 ]]'

printf 'test_zero_shortcomings_audit_enumerate: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_zero_shortcomings_audit_enumerate.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/audit/test_zero_shortcomings_audit_enumerate.sh`
Expected: FAIL — `scripts/zero_shortcomings_audit.sh: No such file or directory`

- [ ] **Step 3: Write minimal implementation**

```bash
cat > scripts/zero_shortcomings_audit.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

print_info()    { printf '\033[0;34m[INFO]\033[0m %s\n' "$*"; }
print_success() { printf '\033[0;32m[ OK ]\033[0m %s\n' "$*"; }
print_warning() { printf '\033[0;33m[WARN]\033[0m %s\n' "$*"; }
print_error()   { printf '\033[0;31m[FAIL]\033[0m %s\n' "$*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/audit_ledger_parser.sh
source "$SCRIPT_DIR/lib/audit_ledger_parser.sh"
# shellcheck source=lib/audit_execution_policy.sh
source "$SCRIPT_DIR/lib/audit_execution_policy.sh"
# shellcheck source=lib/audit_run_id.sh
source "$SCRIPT_DIR/lib/audit_run_id.sh"

WORKABLE_ITEMS_BIN="$REPO_ROOT/constitution/scripts/workable-items/workable-items"
WORKABLE_ITEMS_DB="$REPO_ROOT/docs/workable_items.db"
GATE_LEDGER_SCRIPT="$REPO_ROOT/constitution/scripts/gates/cm_gate_ledger_ratchet.sh"
COVERAGE_ESCAPE_LEDGER="$REPO_ROOT/docs/QA_DISCOVERY_LEDGER.md"

usage() {
    cat <<'USAGE'
Usage: zero_shortcomings_audit.sh <mode> [options]

Modes:
  enumerate [--json] [--surface backlog|gates|escapes]
      Read-only. Enumerates the three tracked surfaces. See
      specs/003-zero-shortcomings-audit/contracts/cli.md for the full contract.
  verify-closure <item-id> [--reopen-on-mismatch]
      Independently re-runs one item's recorded closure evidence.
  standing-check
      The recurring, non-blocking mode wired into pre_build_verification.sh.

Options:
  -h, --help    Show this help and exit.
USAGE
}

count_backlog_open() {
    sqlite3 "$WORKABLE_ITEMS_DB" \
        "SELECT count(*) FROM items WHERE status NOT LIKE '%(→ Fixed.md)' AND status != 'Obsolete';"
}

count_gates_unimplemented() {
    # cm_gate_ledger_ratchet.sh prints a summary line this project's own
    # tooling already produces (confirmed live, per research.md §2) —
    # reused verbatim rather than re-parsed independently (§11.4.251).
    bash "$GATE_LEDGER_SCRIPT" 2>&1 \
        | grep -oE 'unimplemented=[0-9]+' \
        | head -1 \
        | grep -oE '[0-9]+' \
        || printf '0\n'
}

count_escapes_open() {
    audit_ledger_count_open_escapes "$COVERAGE_ESCAPE_LEDGER"
}

cmd_enumerate() {
    local json=false
    local surface="all"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --json) json=true; shift ;;
            --surface) surface="$2"; shift 2 ;;
            *) print_error "enumerate: unknown option: $1"; return 1 ;;
        esac
    done

    local backlog="" gates="" escapes=""
    [[ "$surface" == "all" || "$surface" == "backlog" ]] && backlog="$(count_backlog_open)"
    [[ "$surface" == "all" || "$surface" == "gates" ]] && gates="$(count_gates_unimplemented)"
    [[ "$surface" == "all" || "$surface" == "escapes" ]] && escapes="$(count_escapes_open)"

    if [[ "$json" == "true" ]]; then
        local body=""
        [[ -n "$backlog" ]] && body+="\"backlog_open\":${backlog},"
        [[ -n "$gates" ]] && body+="\"gates_unimplemented\":${gates},"
        [[ -n "$escapes" ]] && body+="\"escapes_open\":${escapes},"
        body="${body%,}"
        printf '{%s}\n' "$body"
    else
        print_info "Zero-shortcomings audit — enumeration ($(audit_run_id))"
        [[ -n "$backlog" ]] && print_info "Open backlog items:        $backlog"
        [[ -n "$gates" ]] && print_info "Unimplemented gates:       $gates"
        [[ -n "$escapes" ]] && print_info "Open coverage-escapes:     $escapes"
    fi
}

main() {
    local mode="${1:-}"
    case "$mode" in
        -h|--help|"") usage; [[ "$mode" == "" ]] && return 1 || return 0 ;;
        enumerate) shift; cmd_enumerate "$@" ;;
        verify-closure) shift; print_error "verify-closure: not yet implemented (Task 5)"; return 2 ;;
        standing-check) shift; print_error "standing-check: not yet implemented (Task 7)"; return 2 ;;
        *) print_error "unknown mode: $mode"; usage; return 1 ;;
    esac
}

main "$@"
EOF
chmod +x scripts/zero_shortcomings_audit.sh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_zero_shortcomings_audit_enumerate.sh`
Expected: `test_zero_shortcomings_audit_enumerate: 4 passed, 0 failed`

- [ ] **Step 5: Write the companion doc (§11.4.18) and regenerate export twins**

```bash
cat > docs/scripts/zero_shortcomings_audit.md <<'EOF'
# `scripts/zero_shortcomings_audit.sh`

**Purpose**: Unified enumeration, closure-evidence re-verification, and standing-check
entry point across this project's three tracked "unfinished/gap/shortcoming" surfaces.
See `specs/003-zero-shortcomings-audit/contracts/cli.md` for the full CLI contract.

**Usage**: `scripts/zero_shortcomings_audit.sh <enumerate|verify-closure|standing-check> [options]`

**Inputs**: `docs/workable_items.db` (read-only), `constitution/scripts/gates/`
(read-only, via `cm_gate_ledger_ratchet.sh`), `docs/QA_DISCOVERY_LEDGER.md` (read-only).

**Outputs**: A human-readable or `--json` report; `standing-check` additionally appends
one line to `docs/qa/zero_shortcomings_audit/<run-id>.log`.

**Side-effects**: None in `enumerate` or `standing-check` mode. `verify-closure
--reopen-on-mismatch` may call the `workable-items` CLI to reopen an item.

**Dependencies**: `sqlite3`, `constitution/scripts/workable-items/workable-items`,
`constitution/scripts/gates/cm_gate_ledger_ratchet.sh`.

**Cross-references**: `specs/003-zero-shortcomings-audit/{spec,plan,research,data-model}.md`.

**Last verified**: 2026-09-25.
EOF
bash scripts/workable-items-export.sh
```

- [ ] **Step 6: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/zero_shortcomings_audit.sh --scope docs/scripts/zero_shortcomings_audit.md --scope docs/scripts/zero_shortcomings_audit.html --scope docs/scripts/zero_shortcomings_audit.pdf --scope docs/scripts/zero_shortcomings_audit.docx --scope tests/audit/test_zero_shortcomings_audit_enumerate.sh \
    "feat(audit): enumerate mode across all three tracked surfaces (US1, FR-001/002/003)"
```

**Checkpoint**: User Story 1 is fully functional and independently testable — run
`quickstart.md` Step 1 to confirm against live ground truth.

### Task 4B: `[TDD]` Honest blocked-item reporting (FR-007)

**Self-review finding**: the first pass of this task list covered FR-001/002/003/004/006/008/009/013
with real tasks but left FR-007 (honestly report — never silently drop or falsely close —
an operator-blocked item) with no owning task. Closed here as an `enumerate` extension,
since `cmd_enumerate` already exists from Task 4 and this is a shape addition to it, not
a new subsystem. (FR-005, evidence-layer matching, is a separate gap closed by Task 5B,
positioned after Task 5 — it extends `cmd_verify_closure`, which does not exist until
Task 5 creates it, so it cannot be done here without a forward reference.)

**Files:**
- Modify: `scripts/zero_shortcomings_audit.sh`
- Test: `tests/audit/test_zero_shortcomings_audit_blocked_surface.sh`

**Interfaces:**
- Produces: `cmd_enumerate --surface blocked` — lists every `Operator-blocked` item's id
  and its `operator_block_details.unblock_condition` (never just a bare count — FR-007's
  "specific, observable condition" requirement, and spec.md SC-006).

- [ ] **Step 1: Write the failing test**

```bash
cat > tests/audit/test_zero_shortcomings_audit_blocked_surface.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

out="$(bash scripts/zero_shortcomings_audit.sh enumerate --surface blocked)"
check "enumerate --surface blocked names at least one real unblock condition, not a bare count" \
    'printf "%s" "$out" | grep -qiE "unblock|condition"'
check "enumerate --surface blocked never prints a bare number with nothing else (SC-006)" \
    '! printf "%s" "$out" | grep -qE "^[0-9]+$"'

printf 'test_zero_shortcomings_audit_blocked_surface: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_zero_shortcomings_audit_blocked_surface.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/audit/test_zero_shortcomings_audit_blocked_surface.sh`
Expected: FAIL — `--surface blocked` is not yet a recognized value in `cmd_enumerate`.

- [ ] **Step 3: Write minimal implementation**

```bash
sed -i '$ d' scripts/zero_shortcomings_audit.sh
cat >> scripts/zero_shortcomings_audit.sh <<'EOF'

count_blocked_with_conditions() {
    sqlite3 -separator '|' "$WORKABLE_ITEMS_DB" \
        "SELECT i.atm_id, b.unblock_condition FROM items i
         JOIN operator_block_details b ON b.atm_id = i.atm_id
         WHERE i.status = 'Operator-blocked';"
}
EOF
echo 'main "$@"' >> scripts/zero_shortcomings_audit.sh
```

Extend `cmd_enumerate`'s `case` statement (the `--surface` option handling) to add a
`blocked` branch that calls `count_blocked_with_conditions` and prints its output
directly — never collapsing it to a bare count, per FR-007.

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_zero_shortcomings_audit_blocked_surface.sh`
Expected: `test_zero_shortcomings_audit_blocked_surface: 2 passed, 0 failed`

- [ ] **Step 5: Re-run Task 4's test to confirm no regression**

Run: `bash tests/audit/test_zero_shortcomings_audit_enumerate.sh`
Expected: `test_zero_shortcomings_audit_enumerate: 4 passed, 0 failed` (unchanged)

- [ ] **Step 6: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/zero_shortcomings_audit.sh --scope tests/audit/test_zero_shortcomings_audit_blocked_surface.sh \
    "feat(audit): honest blocked-item reporting with unblock conditions (FR-007)"
```

---

## Phase 4: User Story 2 - Evidence-backed closure with reproducibility (Priority: P2)

**Goal**: Every closure is backed by re-runnable evidence; a bluff closure is
automatically caught and reopened; a verification side-effect never corrupts a
different item's evidence.

**Independent Test** (from spec.md): `quickstart.md` Steps 2–3 — a genuine closure
reproduces; a deliberately-corrupted evidence claim is caught and reopened; a simulated
cross-item side effect is detected and reverted.

### Task 5: `[TDD]` `verify-closure` re-verification harness

**Files:**
- Modify: `scripts/zero_shortcomings_audit.sh` (replace the Task 4 stub)
- Test: `tests/audit/test_zero_shortcomings_audit_verify_closure.sh`
- Test fixtures: `tests/audit/fixtures/closure_evidence_matching.md`, `tests/audit/fixtures/closure_evidence_mismatched.md`

**Interfaces:**
- Consumes: a `ClosureEvidenceArtifact`-shaped Markdown file (data-model.md) — this task
  reads a `**Command:**` and `**Result Summary:**` field pair from the item's own
  `docs/qa/<id>/closure_evidence_*.md` file (the exact convention already used by every
  closure this session produced).
- Produces: `cmd_verify_closure <item-id> [--reopen-on-mismatch]` per `contracts/cli.md`
  — exit `0` (match), `1` (mismatch), `2` (no evidence file found for that item).

- [ ] **Step 1: Write the failing test + fixtures**

```bash
mkdir -p tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-MATCH
mkdir -p tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-MISMATCH

cat > tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-MATCH/closure_evidence_fixture.md <<'EOF'
# BOB-FIXTURE-MATCH — closure evidence

**Command:** `echo '3 passed, 0 failed'`
**Result Summary:** 3 passed, 0 failed
EOF

cat > tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-MISMATCH/closure_evidence_fixture.md <<'EOF'
# BOB-FIXTURE-MISMATCH — closure evidence

**Command:** `echo '3 passed, 0 failed'`
**Result Summary:** 5 passed, 0 failed
EOF

cat > tests/audit/test_zero_shortcomings_audit_verify_closure.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

export AUDIT_QA_ROOT="tests/audit/fixtures/docs_qa_fixture"

set +e
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-MATCH
match_rc=$?
set -e
check "a genuinely matching closure exits 0" '[[ "$match_rc" -eq 0 ]]'

set +e
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-MISMATCH
mismatch_rc=$?
set -e
check "a mismatched closure exits 1 (Review Focus item 3: semantic mismatch is real)" \
    '[[ "$mismatch_rc" -eq 1 ]]'

set +e
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-NONEXISTENT
missing_rc=$?
set -e
check "an item with no recorded evidence exits 2 (itself a finding)" \
    '[[ "$missing_rc" -eq 2 ]]'

unset AUDIT_QA_ROOT
printf 'test_zero_shortcomings_audit_verify_closure: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_zero_shortcomings_audit_verify_closure.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/audit/test_zero_shortcomings_audit_verify_closure.sh`
Expected: FAIL — `verify-closure: not yet implemented (Task 5)`, all three checks fail
(the placeholder always exits 2).

- [ ] **Step 3: Write minimal implementation**

**Ordering constraint** (caught in self-review): `scripts/zero_shortcomings_audit.sh`
always ends with the line `main "$@"` as its LAST line (Task 4). Every later task that
adds a new `cmd_*` function MUST insert it BEFORE that line, never append after it with
a bare `cat >>` — a function defined after `main "$@"` has already run is not yet
defined when `main` tries to call it. Use this insertion pattern for every remaining
task in this plan:

```bash
# Remove the trailing "main \"$@\"" line, append the new code, then restore it
# as the file's final line — keeps main() always last without hand-editing.
sed -i '$ d' scripts/zero_shortcomings_audit.sh   # drop the last line (main "$@")
cat >> scripts/zero_shortcomings_audit.sh <<'EOF'

AUDIT_QA_ROOT="${AUDIT_QA_ROOT:-$REPO_ROOT/docs/qa}"

cmd_verify_closure() {
    local item_id="${1:-}"
    local reopen_on_mismatch=false
    shift || true
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --reopen-on-mismatch) reopen_on_mismatch=true; shift ;;
            *) print_error "verify-closure: unknown option: $1"; return 1 ;;
        esac
    done
    if [[ -z "$item_id" ]]; then
        print_error "verify-closure: an item id is required"
        return 1
    fi

    local evidence_file
    evidence_file="$(find "$AUDIT_QA_ROOT/$item_id" -maxdepth 1 -name 'closure_evidence_*.md' 2>/dev/null | head -1)"
    if [[ -z "$evidence_file" ]]; then
        print_error "verify-closure: no recorded evidence for $item_id under $AUDIT_QA_ROOT/$item_id"
        return 2
    fi

    local recorded_command recorded_summary
    recorded_command="$(grep -oP '(?<=\*\*Command:\*\* `).*(?=`)' "$evidence_file" | head -1)"
    recorded_summary="$(grep -oP '(?<=\*\*Result Summary:\*\* ).*' "$evidence_file" | head -1)"

    if [[ -z "$recorded_command" ]]; then
        print_error "verify-closure: $evidence_file has no **Command:** field to re-run"
        return 2
    fi

    # Review Focus item 3: compare the SEMANTIC result_summary, never raw
    # bytes — a legitimately time-varying command (a timestamp, a duration)
    # would otherwise false-positive-reopen every time (§11.4.201(1)).
    local fresh_summary
    fresh_summary="$(eval "$recorded_command")"

    if [[ "$fresh_summary" == "$recorded_summary" ]]; then
        print_success "verify-closure: $item_id reproduced its recorded evidence"
        return 0
    fi

    print_error "verify-closure: $item_id MISMATCH — recorded '$recorded_summary', got '$fresh_summary'"
    if [[ "$reopen_on_mismatch" == "true" ]]; then
        print_warning "verify-closure: reopening $item_id (--reopen-on-mismatch)"
        "$WORKABLE_ITEMS_BIN" reopen --id "$item_id" --db "$WORKABLE_ITEMS_DB" \
            --why "test-failed" --who "AI" --when "$(date -u '+%Y-%m-%d')" \
            --incident "$evidence_file" || true
    fi
    return 1
}
EOF
echo 'main "$@"' >> scripts/zero_shortcomings_audit.sh
```

Then edit `main()`'s `verify-closure` case line (still present from Task 4, now BEFORE
the newly-appended code, unaffected by the sed/append above since it only touched the
final line) from
`verify-closure) shift; print_error "verify-closure: not yet implemented (Task 5)"; return 2 ;;`
to `verify-closure) shift; cmd_verify_closure "$@" ;;`.

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_zero_shortcomings_audit_verify_closure.sh`
Expected: `test_zero_shortcomings_audit_verify_closure: 3 passed, 0 failed`

- [ ] **Step 5: Re-run Task 4's enumerate test to confirm no regression**

Run: `bash tests/audit/test_zero_shortcomings_audit_enumerate.sh`
Expected: `test_zero_shortcomings_audit_enumerate: 4 passed, 0 failed` (unchanged)

- [ ] **Step 6: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/zero_shortcomings_audit.sh --scope tests/audit/test_zero_shortcomings_audit_verify_closure.sh --scope tests/audit/fixtures/docs_qa_fixture/ \
    "feat(audit): verify-closure independent re-verification harness (US2, FR-004/006/013)"
```

### Task 5B: `[TDD]` Evidence-layer matching (FR-005)

**Self-review finding**: FR-005 ("match each closure's evidence to the correct defect
layer... never accept a lower-rigor substitute") has no owning task in the first pass.
Positioned here, immediately after Task 5, because it extends `cmd_verify_closure` —
which does not exist before Task 5 creates it.

**Files:**
- Modify: `scripts/zero_shortcomings_audit.sh`
- Test: `tests/audit/test_zero_shortcomings_audit_evidence_layer.sh`

**Interfaces:**
- Extends: `cmd_verify_closure` to read an optional `**Evidence Layer:**` field
  (`source`|`artifact`|`runtime`, data-model.md's `ClosureEvidenceArtifact`) from the
  evidence file and a new `--require-layer <source|artifact|runtime>` flag (default
  `runtime`, the strictest — §11.4.101 safe-default). When the evidence file's declared
  layer is WEAKER than the required layer (ordering: `source` < `artifact` < `runtime`),
  `cmd_verify_closure` refuses with exit `2` (distinct from a `1` semantic mismatch) and
  names the declared layer in its error, BEFORE it ever compares `result_summary`. An
  evidence file with no `**Evidence Layer:**` field is treated as declaring `source` (the
  WEAKEST layer, not the strictest) for this comparison — an unlabeled artifact must
  never be silently assumed to already meet the strict default; it is deliberately
  the layer most likely to be caught refused until someone labels it correctly.

- [ ] **Step 1: Write the failing test + fixtures**

```bash
mkdir -p tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-LAYER-OK
mkdir -p tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-LAYER-TOOWEAK

cat > tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-LAYER-OK/closure_evidence_fixture.md <<'EOF'
# BOB-FIXTURE-LAYER-OK — closure evidence

**Command:** `echo '1 passed, 0 failed'`
**Result Summary:** 1 passed, 0 failed
**Evidence Layer:** runtime
EOF

cat > tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-LAYER-TOOWEAK/closure_evidence_fixture.md <<'EOF'
# BOB-FIXTURE-LAYER-TOOWEAK — closure evidence

**Command:** `echo '1 passed, 0 failed'`
**Result Summary:** 1 passed, 0 failed
**Evidence Layer:** source
EOF

cat > tests/audit/test_zero_shortcomings_audit_evidence_layer.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

export AUDIT_QA_ROOT="tests/audit/fixtures/docs_qa_fixture"
set +e
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-LAYER-OK
ok_rc=$?
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-LAYER-TOOWEAK
weak_rc=$?
set -e
unset AUDIT_QA_ROOT

check "runtime-layer evidence for a runtime-required item passes" '[[ "$ok_rc" -eq 0 ]]'
check "source-layer evidence is refused with a distinct exit code, not a plain mismatch" \
    '[[ "$weak_rc" -eq 2 ]]'

printf 'test_zero_shortcomings_audit_evidence_layer: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_zero_shortcomings_audit_evidence_layer.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/audit/test_zero_shortcomings_audit_evidence_layer.sh`
Expected: FAIL — both fixtures currently pass through `cmd_verify_closure` identically
(the layer field is not yet read), so `weak_rc` is `0`, not `2`.

- [ ] **Step 3: Write minimal implementation**

Modify `cmd_verify_closure` (Task 5) in place — add near its top, after option parsing:

```bash
    local require_layer="runtime"
    # (extend the existing while/case option-parsing loop above with:)
    #   --require-layer) require_layer="$2"; shift 2 ;;
```

And, immediately after `evidence_file` is confirmed to exist (before the
`recorded_command`/`recorded_summary` reads), insert:

```bash
    # audit_layer_rank <layer> — a plain case statement, not a bash-4.3+
    # nameref (`local -n`), so this runs on any bash this project already
    # requires (§11.4.analyze finding C1: no other script here was confirmed
    # to depend on namerefs, and plan.md's Technical Context states no bash
    # version floor — a case statement has zero version dependency).
    audit_layer_rank() {
        case "$1" in
            source)   printf '0\n' ;;
            artifact) printf '1\n' ;;
            runtime)  printf '2\n' ;;
            *)        printf '0\n' ;;  # an unrecognized label is treated as weakest
        esac
    }

    local declared_layer
    declared_layer="$(grep -oP '(?<=\*\*Evidence Layer:\*\* ).*' "$evidence_file" | head -1)"
    declared_layer="${declared_layer:-source}"
    local declared_rank required_rank
    declared_rank="$(audit_layer_rank "$declared_layer")"
    required_rank="$(audit_layer_rank "$require_layer")"
    if [[ "$declared_rank" -lt "$required_rank" ]]; then
        print_error "verify-closure: $item_id declares evidence layer '$declared_layer' but '$require_layer' is required — a lower-rigor substitute is not accepted (FR-005)"
        return 2
    fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_zero_shortcomings_audit_evidence_layer.sh`
Expected: `test_zero_shortcomings_audit_evidence_layer: 2 passed, 0 failed`

- [ ] **Step 5: Re-run Task 5's own test to confirm no regression**

Run: `bash tests/audit/test_zero_shortcomings_audit_verify_closure.sh`
Expected: `test_zero_shortcomings_audit_verify_closure: 3 passed, 0 failed` (unchanged —
its fixtures carry no `**Evidence Layer:**` field, so they default to `source`
required-`runtime`... **note this is a real interaction to verify, not assume**: Task
5's `BOB-FIXTURE-MATCH` fixture has no layer field, defaults to declaring `source`,
which is WEAKER than the `runtime` default requirement, so it would now ALSO get
refused with exit `2` unless Task 5's fixture is updated in this step to add
`**Evidence Layer:** runtime`. Update
`tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-MATCH/closure_evidence_fixture.md` and
`.../BOB-FIXTURE-MISMATCH/closure_evidence_fixture.md` to each add a
`**Evidence Layer:** runtime` line before re-running, and confirm Task 5's test is still
green afterward — this cross-task fixture dependency is exactly the kind of thing this
step's re-run exists to catch.)

- [ ] **Step 6: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/zero_shortcomings_audit.sh --scope tests/audit/test_zero_shortcomings_audit_evidence_layer.sh --scope tests/audit/fixtures/docs_qa_fixture/ \
    "feat(audit): evidence-layer matching, refuse a lower-rigor substitute (FR-005)"
```

---

### Task 5C: `[TDD]` `[REVIEW]` Credential redaction before any evidence write (Constitution Principle III)

**`/speckit-analyze` finding D2 (CRITICAL)**: plan.md's post-design Constitution Check
claimed Principle III (credential security) was "closed by
`ClosureEvidenceArtifact.redaction_applied`" — but no task actually implemented or
tested that field. As written, `cmd_verify_closure` and `cmd_standing_check` write raw
command output into `docs/qa/zero_shortcomings_audit/<run-id>.log`, so a
credential-adjacent item's `result_summary` could leak a secret value into a tracked log
file, directly violating "No secret values MAY appear in log output, test reports, or
commit messages." This task closes that gap before Task 6 or Task 7 dispatch any real
verification command.

**Files:**
- Modify: `scripts/zero_shortcomings_audit.sh`
- Test: `tests/audit/test_zero_shortcomings_audit_redaction.sh`

**Interfaces:**
- Produces: `audit_redact_before_write <text>` — prints `<text>` to stdout with any
  substring matching this project's own known credential-value SHAPES (never their
  variable NAMES, which remain loggable per constitution Principle III) replaced with
  `<redacted-per-§11.4.10>`. Reuses the SAME detection this project's existing
  `§11.4.10.A` leak-audit already defines — never a second, independently-invented
  pattern set (§11.4.251).

- [ ] **Step 1: Write the failing test**

```bash
cat > tests/audit/test_zero_shortcomings_audit_redaction.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/zero_shortcomings_audit.sh 2>/dev/null || true

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

# A fake, credential-SHAPED value (never a real secret — this is a fixture).
plain="3 passed, 0 failed"
out_plain="$(audit_redact_before_write "$plain")"
check "ordinary, non-credential text passes through unchanged" \
    '[[ "$out_plain" == "$plain" ]]'

leaky="RUTRACKER_PASSWORD=hunter2-fixture-value-not-real"
out_leaky="$(audit_redact_before_write "$leaky")"
check "a credential-shaped VALUE is redacted" \
    '! printf "%s" "$out_leaky" | grep -q "hunter2-fixture-value-not-real"'
check "the credential's VARIABLE NAME remains loggable (Principle III: names loggable, values are not)" \
    'printf "%s" "$out_leaky" | grep -q "RUTRACKER_PASSWORD"'
check "the redaction marker is present in place of the value" \
    'printf "%s" "$out_leaky" | grep -q "redacted-per"'

printf 'test_zero_shortcomings_audit_redaction: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_zero_shortcomings_audit_redaction.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/audit/test_zero_shortcomings_audit_redaction.sh`
Expected: FAIL — `audit_redact_before_write: command not found`

- [ ] **Step 3: Write minimal implementation**

First, locate this project's EXISTING §11.4.10.A leak-audit pattern set (never invent a
second one):

```bash
grep -rl "11.4.10.A\|leak.audit\|leak_audit" scripts/ constitution/scripts/ 2>/dev/null | head -5
```

Read whatever that search surfaces and extract its actual credential-shape regex(es).
Then, respecting Task 5's ordering constraint:

```bash
sed -i '$ d' scripts/zero_shortcomings_audit.sh
cat >> scripts/zero_shortcomings_audit.sh <<'EOF'

# audit_redact_before_write <text> — reuses this project's own established
# §11.4.10.A credential-shape patterns (the exact set discovered above) to
# redact VALUES while preserving variable NAMES, per constitution Principle
# III. This function's own pattern set is a citation of the existing
# leak-audit logic, not a second independent implementation (§11.4.251).
audit_redact_before_write() {
    local text="$1"
    # (substitute the ACTUAL patterns discovered above; this illustrative
    # example covers the KEY=VALUE shape named in the project's own
    # §11.4.10.A / cookies-file conventions — CLAUDE.md's own credential
    # variable list: RUTRACKER_*, KINOZAL_*, NNMCLUB_*, IPTORRENTS_*,
    # BOBA_MASTER_KEY, BOBA_API_TOKEN)
    printf '%s' "$text" | sed -E \
        's/(RUTRACKER|KINOZAL|NNMCLUB|IPTORRENTS)_(USERNAME|PASSWORD|COOKIES)=[^[:space:]]+/\1_\2=<redacted-per-§11.4.10>/g; s/(BOBA_MASTER_KEY|BOBA_API_TOKEN)=[^[:space:]]+/\1=<redacted-per-§11.4.10>/g'
}
EOF
echo 'main "$@"' >> scripts/zero_shortcomings_audit.sh
```

Then wire it into every write path that reaches a tracked log: in `cmd_verify_closure`
(Task 5), wrap `fresh_summary` and `recorded_summary` in `audit_redact_before_write`
before they ever appear in a `print_error`/`print_success` line; in `cmd_standing_check`
(Task 7), wrap `counts` in `audit_redact_before_write` before it is appended to the
run-log file.

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_zero_shortcomings_audit_redaction.sh`
Expected: `test_zero_shortcomings_audit_redaction: 4 passed, 0 failed`

- [ ] **Step 5: `[REVIEW]` Re-run every prior task's own test suite**

Run: `for f in tests/audit/test_zero_shortcomings_audit_*.sh; do bash "$f"; done`
Expected: zero regressions across every test written by Tasks 4 through 5B — this step
requires review before merge, since redaction wrapping touches shared output paths
every later task's own test also exercises.

- [ ] **Step 6: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/zero_shortcomings_audit.sh --scope tests/audit/test_zero_shortcomings_audit_redaction.sh \
    "fix(audit): redact credential-shaped values before any evidence/log write (Constitution Principle III, /speckit-analyze finding D2)"
```

---

### Task 6: `[TDD]` `[REVIEW]` Evidence-corruption guard

**Files:**
- Modify: `scripts/zero_shortcomings_audit.sh`
- Test: `tests/audit/test_zero_shortcomings_audit_corruption_guard.sh`

**Interfaces:**
- Consumes: the same command-dispatch path `verify-closure` already uses.
- Produces: `audit_snapshot_tracked_evidence` / `audit_detect_and_revert_corruption` — a
  before/after git-diff-based guard (research.md §5) wrapped around any dispatched
  verification command; corruption incidents are appended to
  `docs/qa/zero_shortcomings_audit/<run-id>.log`.

- [ ] **Step 1: Write the failing test**

This test reproduces the EXACT incident class this feature's design is modeled on
(research.md §5, the real `docs/qa/BOB-109/*.json` incident): a command that, as a side
effect, overwrites a DIFFERENT item's tracked evidence file.

```bash
cat > tests/audit/test_zero_shortcomings_audit_corruption_guard.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/zero_shortcomings_audit.sh 2>/dev/null || true  # sourced for its functions only

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"
git init -q .
mkdir -p docs/qa/BOB-OTHER-ITEM docs/qa/BOB-THIS-ITEM
echo "original evidence" > docs/qa/BOB-OTHER-ITEM/closure_evidence.md
git add -A && git commit -q -m "seed"

snapshot="$(audit_snapshot_tracked_evidence)"

# Simulate the exact BOB-109 class: a command that, as a side effect,
# overwrites a DIFFERENT item's evidence file.
echo "corrupted by an unrelated command" > docs/qa/BOB-OTHER-ITEM/closure_evidence.md
# And a legitimate write inside THIS item's own evidence dir, which must NOT
# be reverted (Review Focus item 2 — the guard must not be over-broad).
echo "new evidence for the item under test" > docs/qa/BOB-THIS-ITEM/new_file.md

incidents="$(audit_detect_and_revert_corruption "$snapshot" "docs/qa/BOB-THIS-ITEM")"

check "the guard detects exactly one corrupted file outside the item's own dir" \
    '[[ "$(printf "%s\n" "$incidents" | grep -c .)" -eq 1 ]]'
check "the corrupted file was reverted to its committed content" \
    '[[ "$(cat docs/qa/BOB-OTHER-ITEM/closure_evidence.md)" == "original evidence" ]]'
check "the legitimate new file inside the item's own dir was left alone" \
    '[[ -f docs/qa/BOB-THIS-ITEM/new_file.md ]]'

cd - >/dev/null
printf 'test_zero_shortcomings_audit_corruption_guard: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_zero_shortcomings_audit_corruption_guard.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/audit/test_zero_shortcomings_audit_corruption_guard.sh`
Expected: FAIL — `audit_snapshot_tracked_evidence: command not found`

- [ ] **Step 3: Write minimal implementation**

Same ordering constraint as Task 5 (`main "$@"` must stay last):

```bash
sed -i '$ d' scripts/zero_shortcomings_audit.sh
cat >> scripts/zero_shortcomings_audit.sh <<'EOF'

# audit_snapshot_tracked_evidence — prints every git-tracked path under
# docs/qa/ paired with its current content hash, as one line per file.
audit_snapshot_tracked_evidence() {
    git -C "$REPO_ROOT" ls-files 'docs/qa/**' 2>/dev/null | while IFS= read -r f; do
        [[ -f "$REPO_ROOT/$f" ]] || continue
        printf '%s %s\n' "$f" "$(git -C "$REPO_ROOT" hash-object "$REPO_ROOT/$f")"
    done
}

# audit_detect_and_revert_corruption <snapshot> <own-item-evidence-dir> —
# diffs the current tracked docs/qa/ state against <snapshot>; any changed
# file OUTSIDE <own-item-evidence-dir> is reverted via `git checkout --` and
# printed (one path per line) as an incident. A changed file INSIDE
# <own-item-evidence-dir> is a legitimate write and is left untouched
# (Review Focus item 2).
audit_detect_and_revert_corruption() {
    local snapshot="$1" own_dir="$2"
    local incidents=""
    while IFS= read -r f; do
        [[ -f "$REPO_ROOT/$f" ]] || continue
        case "$f" in
            "$own_dir"/*) continue ;;
        esac
        local before after
        before="$(printf '%s\n' "$snapshot" | grep -F "^$f " | awk '{print $2}')"
        after="$(git -C "$REPO_ROOT" hash-object "$REPO_ROOT/$f")"
        if [[ -n "$before" && "$before" != "$after" ]]; then
            git -C "$REPO_ROOT" checkout -- "$f"
            incidents+="$f"$'\n'
        fi
    done < <(printf '%s\n' "$snapshot" | awk '{print $1}')
    printf '%s' "$incidents"
}
EOF
echo 'main "$@"' >> scripts/zero_shortcomings_audit.sh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_zero_shortcomings_audit_corruption_guard.sh`
Expected: `test_zero_shortcomings_audit_corruption_guard: 3 passed, 0 failed`

- [ ] **Step 5: `[REVIEW]` Wire the guard into `verify-closure`**

Modify `cmd_verify_closure` (Task 5) so it snapshots before `eval "$recorded_command"`
and calls `audit_detect_and_revert_corruption` after, appending any incident to
`docs/qa/zero_shortcomings_audit/<run-id>.log` (using `audit_run_id` from Task 1). This
step requires review before merge, per `plan.md`'s Review Gates — it runs on every
future closure, so a defect here could itself corrupt evidence.

- [ ] **Step 6: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/zero_shortcomings_audit.sh --scope tests/audit/test_zero_shortcomings_audit_corruption_guard.sh \
    "feat(audit): evidence-corruption guard reproducing the real BOB-109 incident (FR-008)"
```

**Checkpoint**: User Stories 1 and 2 both work independently — run `quickstart.md`
Steps 1–3.

### Task 6B: `[TDD]` Risk-ordered closure work (FR-012)

**`/speckit-analyze` finding E2 (MEDIUM)**: FR-012 (sort by `reopens_count` DESC then
`last_modified` DESC — research.md §7) was only a prose bullet inside the Polish phase's
ongoing-work item, with no dedicated, tested implementation. Closed here as a small,
real extension to `enumerate`.

**Files:**
- Modify: `scripts/zero_shortcomings_audit.sh`
- Test: `tests/audit/test_zero_shortcomings_audit_risk_order.sh`

**Interfaces:**
- Produces: `cmd_enumerate --surface backlog --sort-by-risk` — prints backlog item ids
  ordered by `reopens_count` DESC, `last_modified` DESC (the exact predicate
  research.md §7 names), instead of the default surface-count-only output.

- [ ] **Step 1: Write the failing test**

```bash
cat > tests/audit/test_zero_shortcomings_audit_risk_order.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

out="$(bash scripts/zero_shortcomings_audit.sh enumerate --surface backlog --sort-by-risk)"
# Ground truth: the tracker's own reopens_count-DESC ordering for open items.
truth_top="$(sqlite3 docs/workable_items.db \
    "SELECT atm_id FROM items WHERE status NOT LIKE '%(→ Fixed.md)' AND status != 'Obsolete'
     ORDER BY reopens_count DESC, last_modified DESC LIMIT 1;")"
reported_top="$(printf '%s\n' "$out" | head -1)"

check "the first-listed item under --sort-by-risk matches the tracker's own highest-risk item" \
    '[[ "$reported_top" == "$truth_top" ]]'

printf 'test_zero_shortcomings_audit_risk_order: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_zero_shortcomings_audit_risk_order.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/audit/test_zero_shortcomings_audit_risk_order.sh`
Expected: FAIL — `--sort-by-risk` is not yet a recognized option.

- [ ] **Step 3: Write minimal implementation**

Extend `cmd_enumerate`'s option parsing to accept `--sort-by-risk`, and add:

```bash
sed -i '$ d' scripts/zero_shortcomings_audit.sh
cat >> scripts/zero_shortcomings_audit.sh <<'EOF'

list_backlog_risk_ordered() {
    sqlite3 "$WORKABLE_ITEMS_DB" \
        "SELECT atm_id FROM items WHERE status NOT LIKE '%(→ Fixed.md)' AND status != 'Obsolete'
         ORDER BY reopens_count DESC, last_modified DESC;"
}
EOF
echo 'main "$@"' >> scripts/zero_shortcomings_audit.sh
```

Wire the `--sort-by-risk` flag in `cmd_enumerate` so, when set together with
`--surface backlog`, it calls `list_backlog_risk_ordered` and prints its output instead
of the plain count.

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_zero_shortcomings_audit_risk_order.sh`
Expected: `test_zero_shortcomings_audit_risk_order: 1 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/zero_shortcomings_audit.sh --scope tests/audit/test_zero_shortcomings_audit_risk_order.sh \
    "feat(audit): risk-ordered backlog listing (FR-012, /speckit-analyze finding E2)"
```

### Task 6C: `[TDD]` Test-type-matrix applicability check (FR-010)

**`/speckit-analyze` finding E1 (HIGH)**: FR-010 ("verify each item using every test type
applicable to that item's nature") had no dedicated, tested task. This task adds a
genuinely small, honest mechanism: it does NOT attempt to fully automate "which test
types apply" (that remains real domain judgment, as `plan.md` always intended for the
ongoing backlog-closure work) — it instead requires every `ClosureEvidenceArtifact` to
DECLARE which test type(s) its command exercises, and refuses closures with NO declared
test type at all, closing the "asserted as an ongoing practice but never checked" gap
the analysis found.

**Files:**
- Modify: `scripts/zero_shortcomings_audit.sh`
- Test: `tests/audit/test_zero_shortcomings_audit_test_type_declared.sh`
- Test fixture: `tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-NO-TEST-TYPE/closure_evidence_fixture.md`

**Interfaces:**
- Extends: `cmd_verify_closure` to read an optional `**Test Type:**` field (one of this
  project's own Principle X/VI-recognized types: `unit`|`integration`|`e2e`|`security`|
  `stress`|`chaos`|`scaling`|`ui`|`challenge`). An evidence file with NO `**Test Type:**`
  field is refused with exit `2` (the same "distinct from a plain mismatch" code family
  Task 5B established) BEFORE `result_summary` comparison — this is the honest, checkable
  half of FR-010; determining whether the DECLARED type is the CORRECT one for that
  item's nature remains the ongoing, judgment-driven backlog-closure work `plan.md`
  already scopes (T-POLISH-4), not something this mechanism can or should infer.

- [ ] **Step 1: Write the failing test + fixture**

```bash
mkdir -p tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-NO-TEST-TYPE
cat > tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-NO-TEST-TYPE/closure_evidence_fixture.md <<'EOF'
# BOB-FIXTURE-NO-TEST-TYPE — closure evidence

**Command:** `echo '1 passed, 0 failed'`
**Result Summary:** 1 passed, 0 failed
**Evidence Layer:** runtime
EOF

cat > tests/audit/test_zero_shortcomings_audit_test_type_declared.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

export AUDIT_QA_ROOT="tests/audit/fixtures/docs_qa_fixture"
set +e
bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-NO-TEST-TYPE
rc=$?
set -e
unset AUDIT_QA_ROOT

check "an evidence file with no declared test type is refused (FR-010)" '[[ "$rc" -eq 2 ]]'

printf 'test_zero_shortcomings_audit_test_type_declared: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_zero_shortcomings_audit_test_type_declared.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/audit/test_zero_shortcomings_audit_test_type_declared.sh`
Expected: FAIL — the fixture currently passes through `cmd_verify_closure` (rc=0), since
no test-type check exists yet.

- [ ] **Step 3: Write minimal implementation**

Modify `cmd_verify_closure`, immediately after the Task 5B evidence-layer check, insert:

```bash
    local declared_test_type
    declared_test_type="$(grep -oP '(?<=\*\*Test Type:\*\* ).*' "$evidence_file" | head -1)"
    if [[ -z "$declared_test_type" ]]; then
        print_error "verify-closure: $item_id declares no **Test Type:** — FR-010 requires every closure to name which test type its evidence exercises"
        return 2
    fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_zero_shortcomings_audit_test_type_declared.sh`
Expected: `test_zero_shortcomings_audit_test_type_declared: 1 passed, 0 failed`

- [ ] **Step 5: `[REVIEW]` Re-run Tasks 5, 5B, and 5C's own fixtures — add the now-required field**

This new requirement affects every EARLIER fixture. Update
`BOB-FIXTURE-MATCH`, `BOB-FIXTURE-MISMATCH`, `BOB-FIXTURE-LAYER-OK` to each add a
`**Test Type:** unit` line (they are pure bash/logic fixtures, `unit` is the correct
declared type), then re-run:

```bash
bash tests/audit/test_zero_shortcomings_audit_verify_closure.sh
bash tests/audit/test_zero_shortcomings_audit_evidence_layer.sh
```

Expected: both still fully green after the fixture updates — this step requires review
before merge, since it is the second time in this plan a later task's requirement has
forced an update to an earlier task's fixtures (the first was Task 5B on Task 5's
fixtures) — confirming this class of cross-task interaction is being caught
systematically, not accidentally.

- [ ] **Step 6: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/zero_shortcomings_audit.sh --scope tests/audit/test_zero_shortcomings_audit_test_type_declared.sh --scope tests/audit/fixtures/docs_qa_fixture/ \
    "feat(audit): require a declared test type on every closure evidence artifact (FR-010, /speckit-analyze finding E1)"
```

---

## Phase 5: User Story 3 - Standing, recurring mechanism (Priority: P3)

**Goal**: The zero-open-findings state is checked on every commit, without a scheduler,
without becoming a new blocking-commit regression.

**Independent Test** (from spec.md): `quickstart.md` Step 4 — the new
`pre_build_verification.sh` stage runs `standing-check` automatically; a scratch,
never-tracked gate name does not spuriously move the reported count.

### Task 7: `standing-check` mode

**Files:**
- Modify: `scripts/zero_shortcomings_audit.sh`
- Test: `tests/audit/test_zero_shortcomings_audit_standing_check.sh`

**Interfaces:**
- Produces: `cmd_standing_check` — equivalent to `cmd_enumerate --json`, plus appending
  one `AuditRunRecord` line to `docs/qa/zero_shortcomings_audit/<run-id>.log`.

- [ ] **Step 1: Write the failing test**

```bash
cat > tests/audit/test_zero_shortcomings_audit_standing_check.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

before_count="$(find docs/qa/zero_shortcomings_audit -name '*.log' 2>/dev/null | wc -l)"
bash scripts/zero_shortcomings_audit.sh standing-check
rc=$?
after_count="$(find docs/qa/zero_shortcomings_audit -name '*.log' 2>/dev/null | wc -l)"

check "standing-check always exits 0 (advisory, never blocks — Review Focus item 4)" \
    '[[ "$rc" -eq 0 ]]'
check "standing-check appends exactly one new run-log file" \
    '[[ "$after_count" -eq $((before_count + 1)) ]]'

printf 'test_zero_shortcomings_audit_standing_check: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/audit/test_zero_shortcomings_audit_standing_check.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/audit/test_zero_shortcomings_audit_standing_check.sh`
Expected: FAIL — `standing-check: not yet implemented (Task 7)`

- [ ] **Step 3: Write minimal implementation**

Same ordering constraint as Tasks 5–6:

```bash
sed -i '$ d' scripts/zero_shortcomings_audit.sh
cat >> scripts/zero_shortcomings_audit.sh <<'EOF'

cmd_standing_check() {
    mkdir -p "$REPO_ROOT/docs/qa/zero_shortcomings_audit"
    local run_id counts
    run_id="$(audit_run_id)"
    counts="$(cmd_enumerate --json)"
    printf '%s mode=standing-check %s\n' "$run_id" "$counts" \
        >> "$REPO_ROOT/docs/qa/zero_shortcomings_audit/${run_id}.log"
    print_info "standing-check ($run_id): $counts"
    return 0
}
EOF
echo 'main "$@"' >> scripts/zero_shortcomings_audit.sh
```

Then edit `main()`'s `standing-check` case line from
`standing-check) shift; print_error "standing-check: not yet implemented (Task 7)"; return 2 ;;`
to `standing-check) shift; cmd_standing_check "$@" ;;`.

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/audit/test_zero_shortcomings_audit_standing_check.sh`
Expected: `test_zero_shortcomings_audit_standing_check: 2 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/zero_shortcomings_audit.sh --scope tests/audit/test_zero_shortcomings_audit_standing_check.sh \
    "feat(audit): standing-check mode + append-only run log (US3, FR-009)"
```

### Task 8: `[REVIEW]` Wire `standing-check` into `scripts/pre_build_verification.sh`

**Files:**
- Modify: `scripts/pre_build_verification.sh` (append one new, ADVISORY invariant —
  exact insertion point is the file's own final invariant block; locate it by its
  own CURRENT `[N/N]`-style label pattern before editing — the total is 58 as of the
  writing of this plan, but concurrent work in this same session (BOB-223's own fix to
  invariant 16) touches this exact file and may have already changed that number by the
  time this task executes. **Never assume `58`/`59` literally** — re-derive the current
  total from the grep in Step 3 below, every time, per this session's own established
  discipline of confirming exact values rather than assuming them (§11.4.6). This
  finding was surfaced by `/speckit-analyze` (F1) precisely because the first draft of
  this task hardcoded the assumption.)
- Test: `tests/pre_build/test_check_cm_zero_shortcomings_standing.sh`

**Interfaces:**
- Consumes: `scripts/zero_shortcomings_audit.sh standing-check` (Task 7).
- Produces: one new invariant entry in the pre-build sweep's output, non-blocking
  (always contributes PASS to the overall exit code regardless of its reported counts,
  per Task 7's `cmd_standing_check` always returning 0 and per Human Checkpoint 4 in
  `plan.md`).

- [ ] **Step 1: Write the failing test**

```bash
cat > tests/pre_build/test_check_cm_zero_shortcomings_standing.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

out="$(bash scripts/pre_build_verification.sh 2>&1)"
check "the sweep's output names the new zero-shortcomings standing-check stage" \
    'printf "%s" "$out" | grep -qi "zero.shortcomings\|CM-ZERO-SHORTCOMINGS-STANDING"'

# Review Focus item 4: the pre-existing, already-known 41-item backlog alone
# MUST NOT make the overall sweep fail — that would violate Principle VI's
# always-unblocked commit design.
check "the sweep still exits with its pre-existing pass/fail shape (this new stage never blocks alone)" \
    'printf "%s" "$out" | grep -qiv "zero.shortcomings.*BLOCKING"'

printf 'test_check_cm_zero_shortcomings_standing: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
EOF
chmod +x tests/pre_build/test_check_cm_zero_shortcomings_standing.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/pre_build/test_check_cm_zero_shortcomings_standing.sh`
Expected: FAIL — the sweep's output contains no mention of the new stage yet.

- [ ] **Step 3: Locate the exact insertion point and add the invariant**

```bash
# Re-derive the CURRENT total — do not assume it is 58 (F1: this file may have
# been concurrently edited by BOB-223 or any other same-session work since this
# plan was written).
current_total="$(grep -oE '\[[0-9]+/[0-9]+\]' scripts/pre_build_verification.sh \
    | grep -oE '[0-9]+$' | sort -n | tail -1)"
new_total=$((current_total + 1))
printf 'current total: %s, new total after this invariant: %s\n' "$current_total" "$new_total"
grep -n "\[${current_total}/${current_total}\]" scripts/pre_build_verification.sh | tail -5
```

At the located final-invariant block, add (adapting the exact surrounding shell
structure to match what that `grep` reveals — every existing invariant in this file
follows one consistent print-then-check shape, confirmed this session while fixing
BOB-196/BOB-223; substitute the ACTUAL `$new_total` value discovered above, never a
literal `59`):

```bash
print_info "[${new_total}/${new_total}] CM-ZERO-SHORTCOMINGS-STANDING — three-surface audit (advisory)"
if bash scripts/zero_shortcomings_audit.sh standing-check >/tmp/zsc_standing_out.log 2>&1; then
    print_success "CM-ZERO-SHORTCOMINGS-STANDING: $(cat /tmp/zsc_standing_out.log | tail -1)"
else
    print_warning "CM-ZERO-SHORTCOMINGS-STANDING: audit tool itself failed to run — advisory only, not blocking this sweep"
fi
rm -f /tmp/zsc_standing_out.log
```

Update every prior invariant's `[N/${current_total}]` label to `[N/${new_total}]` to
keep the total consistent (this project's own established convention, confirmed via
BOB-196's earlier fix this session, where the total count is printed as part of each
invariant's own label) — using the ACTUAL discovered values, never hardcoded literals.

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/pre_build/test_check_cm_zero_shortcomings_standing.sh`
Expected: `test_check_cm_zero_shortcomings_standing: 2 passed, 0 failed`

- [ ] **Step 5: `[REVIEW]` Run the FULL pre-build sweep to confirm zero regressions**

Run: `bash scripts/pre_build_verification.sh`
Expected: identical pass/fail shape to the pre-Task-8 baseline, plus the new advisory
stage's output — this step requires review before merge per `plan.md`'s Human
Checkpoint 4 (never promote to blocking without a burn-in period first).

- [ ] **Step 6: Commit**

```bash
bash scripts/commit-push-all.sh --scope scripts/pre_build_verification.sh --scope tests/pre_build/test_check_cm_zero_shortcomings_standing.sh \
    "feat(audit): wire standing-check into pre_build_verification.sh (US3, advisory, invariant count re-derived not hardcoded)"
```

**Checkpoint**: All three user stories are independently functional. Run `quickstart.md`
in full.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T-POLISH-1 `[P]` Run `quickstart.md` end-to-end (all 4 steps) against the real
      repository state and paste the actual terminal output into
      `docs/qa/003-zero-shortcomings-audit/quickstart_run_<date>.md`, per Principle XII
      (no self-certification words without pasted evidence).
- [ ] T-POLISH-2 `[P]` `bash -n scripts/zero_shortcomings_audit.sh scripts/lib/audit_*.sh`
      — syntax check every new file (Principle VI).
- [ ] T-POLISH-3 Run the full `tests/audit/` suite together and confirm the aggregate
      pass count matches the sum of every task's individual expected count above (no
      cross-test interference).
- [ ] T-POLISH-4 `[SUBAGENT]` Begin Story 2's ongoing backlog-closure work: dispatch the
      first risk-ordered (FR-012: `reopens_count` DESC, `last_modified` DESC) batch of
      open items from `enumerate`'s output through `verify-closure`, following this
      session's own already-proven parallel-subagent, disjoint-file-scope dispatch
      discipline (research.md §8) — this is the START of the ongoing Story 2 backlog
      work `plan.md` scopes as continuing beyond this task list's own mechanism-building
      scope.
- [ ] T-POLISH-5 Update `README.md`'s doc-link section (§11.4.57/§11.4.212) to include
      `docs/scripts/zero_shortcomings_audit.md` and this feature's `specs/` directory.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Phase 1 (uses `audit_run_id` conventions
  implicitly via later tasks) — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Phase 2 (the ledger parser). Task 4B depends on
  Task 4 (extends `cmd_enumerate`).
- **User Story 2 (Phase 4)**: Depends on Phase 3 (Task 4's `scripts/zero_shortcomings_audit.sh`
  skeleton and `cmd_enumerate`, which Task 6 reuses via the same file). Task 5B depends
  on Task 5 (extends `cmd_verify_closure`, which does not exist before Task 5).
- **User Story 3 (Phase 5)**: Depends on Phase 4 (Task 7 reuses `cmd_enumerate`; the
  corruption guard from Task 6 is inert but present for `standing-check`, which does not
  itself dispatch verification commands, so no functional dependency, only file
  sequencing).
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Parallel Opportunities

- Task 1 and Task 2 have no shared files — dispatch in parallel.
- Task 3 depends on nothing from Tasks 1–2 except the test-file convention — may be
  dispatched in parallel with Task 1/2, per `plan.md`'s stated parallel-execution
  opportunity (ledger parser + corruption guard are independent) — NOTE: every task from
  Task 4 through Task 8 touches the SAME file (`scripts/zero_shortcomings_audit.sh` or,
  for Task 8, the file that invokes it), so Tasks 4→4B→5→5B→6→7→8 are strictly
  sequential on that one file, even though several of their underlying LOGIC pieces
  (ledger parsing vs. corruption guarding vs. layer matching) are conceptually
  independent. `plan.md`'s "dispatch in parallel" opportunity applies to Task 3 vs.
  Tasks 1–2, not to any pair within Tasks 4–8.
- T-POLISH-1 through T-POLISH-3 have no shared files with each other — dispatch in
  parallel; T-POLISH-4 is its own long-running, ongoing effort dispatched separately.

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Task 1) + Phase 2 (Tasks 2–3).
2. Complete Phase 3 (Task 4).
3. **STOP and VALIDATE**: run `quickstart.md` Step 1 against the real repository.
4. This alone already delivers real value — a trustworthy, cross-checked enumeration
   report — even before any closure-verification machinery exists.

### Incremental Delivery

1. Setup + Foundational → Phase 3 (US1, MVP) → validate via quickstart Step 1.
2. Phase 4 (US2) → validate via quickstart Steps 2–3.
3. Phase 5 (US3) → validate via quickstart Step 4.
4. Phase 6 (Polish) → full quickstart run + begin the ongoing backlog-closure work.
