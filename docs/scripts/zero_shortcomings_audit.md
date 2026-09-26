# `scripts/zero_shortcomings_audit.sh`

**Revision:** 2
**Last modified:** 2026-09-26T08:10:00Z

**Purpose**: Unified enumeration, closure-evidence re-verification, and standing-check
entry point across this project's three tracked "unfinished/gap/shortcoming" surfaces
(open backlog items, unimplemented named gates, open coverage-escapes).
See `specs/003-zero-shortcomings-audit/contracts/cli.md` for the full CLI contract.

**Usage**: `scripts/zero_shortcomings_audit.sh <enumerate|verify-closure|standing-check> [options]`

`-h` / `--help` prints the usage text and exits 0. Running with no mode prints the usage
and exits 1. An unknown mode prints `unknown mode: <x>` plus the usage and exits 1.
(The built-in `--help` text lists only the mode names and `--json`/`--surface`; the flags
below that it omits are documented from the script source.)

## Modes

### `enumerate [--json] [--surface S] [--sort-by-risk]`

Read-only. `S` is one of `all` (default), `backlog`, `gates`, `escapes`, `blocked`.

- Default text output: `Open backlog items`, `Unimplemented gates`, `Open coverage-escapes`
  counts (only for the selected surface).
- `--json`: one JSON object with the keys `backlog_open`, `gates_unimplemented`,
  `escapes_open` (only the selected surfaces' keys).
- `--surface blocked`: lists every `Operator-blocked` item as `id|unblock_condition`
  (joined from `operator_block_details`), never a bare count.
- `--sort-by-risk` (FR-012): prints the open backlog item ids ordered by reopen count
  descending (count of `Reopened` events in `item_history`), then `last_modified`
  descending, then id. With `--json` it prints a JSON array of ids. **Only valid with
  `--surface backlog`.**
- Errors (all exit 1, message on stderr): unknown option
  (`enumerate: unknown option: X`); unrecognized `--surface` value
  (`enumerate: unrecognized --surface value: 'X' (expected all|backlog|gates|escapes|blocked)`);
  `--sort-by-risk` with any surface other than `backlog`
  (`enumerate: --sort-by-risk applies only to --surface backlog (got 'X')`).
- The gate count fails loud (exit 1, message naming the gate script) when the gate-ledger
  script prints no parseable `unimplemented=N` line, rather than reporting 0.

### `verify-closure <item-id> [--reopen-on-mismatch] [--require-layer L]`

Independently re-runs the recorded closure evidence for one item. Evidence is read from the
first `closure_evidence_*.md` directly inside `<AUDIT_QA_ROOT>/<item-id>/`.
`--require-layer L` (`source`|`artifact`|`runtime`, default `runtime`) is the minimum
evidence layer accepted; the evidence's `**Evidence Layer:**` field (default `source` when
absent) must rank at or above it (`source` < `artifact` < `runtime`; an unrecognized label
ranks as `source`).

Required evidence-file fields:

- `**Evidence Layer:**` (optional; see above)
- `**Test Type:**` (FR-010) -- required. Allowed values, compared case-insensitively after
  trimming: `unit`, `integration`, `e2e`, `security`, `stress`, `chaos`, `scaling`, `ui`,
  `challenge`.
- ``**Command:** `<command>` `` -- the command to re-run (evaluated with `eval`).
- `**Result Summary:** <text>` -- compared exactly against the command's fresh stdout.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | The recorded command's fresh output equals the recorded Result Summary (`reproduced its recorded evidence`). |
| 1 | Mismatch (`MISMATCH -- recorded '...', got '...'`, values credential-redacted before printing); or usage error: missing item id, unknown option. |
| 2 | No `closure_evidence_*.md` found; declared layer below `--require-layer`; no `**Test Type:**`; invalid `**Test Type:**`; no `**Command:**` field. |

`--reopen-on-mismatch`: on a mismatch, calls the `workable-items reopen` CLI
(`--why test-failed --who AI`, evidence path = the evidence file) before returning 1.

Evidence-corruption guard (FR-008): before running the recorded command the script
snapshots (content hashes) every git-tracked file under `docs/qa/`; afterwards any such
file changed **outside** `<AUDIT_QA_ROOT>/<item-id>/` is restored (files that were already
dirty before the run are restored from a byte copy of their pre-command content, others
via `git checkout --`) and the incident is appended to
`docs/qa/zero_shortcomings_audit/<run-id>.log` with a warning on the console. The guard
never changes the exit code by itself.

### `standing-check`

Recurring, advisory mode; **always exits 0**. Runs `enumerate --json` for each of the
`backlog`, `gates`, `escapes` surfaces and appends one line to
`<AUDIT_STANDING_LOG_DIR>/<run-id>.log`:

`<run-id> mode=standing-check status=ok {"backlog_open":N,"gates_unimplemented":N,"escapes_open":N}`

If a sub-check fails, the line instead carries `status=degraded reason=<list> failed=<list>`
(reasons such as `db_missing`, `<surface>_rc<N>`) and a `WARN` is printed; the JSON body then
holds only the surfaces that succeeded. A missing/unreadable `docs/workable_items.db` is
detected before any `sqlite3` call (so a missing file is never silently created as an empty
DB) and recorded as `db_missing`. If redaction itself fails the line falls back to
`status=degraded reason=redaction_failed`.

Run id format: `YYYYMMDDTHHMMSSZ-pid<PID>`.

## Environment overrides

| Variable | Default | Effect |
|---|---|---|
| `WORKABLE_ITEMS_DB_OVERRIDE` | `docs/workable_items.db` | Backlog / blocked / reopen SQLite DB path. |
| `GATE_LEDGER_SCRIPT_OVERRIDE` | `constitution/scripts/gates/cm_gate_ledger_ratchet.sh` | Gate-ledger script used for the unimplemented-gate count. |
| `AUDIT_QA_ROOT` | `docs/qa` | Root searched for `<item-id>/closure_evidence_*.md`. |
| `AUDIT_STANDING_LOG_DIR` | `docs/qa/zero_shortcomings_audit` | Directory for the `standing-check` log (created if missing). |

## Redaction (Constitution Principle III / §11.4.10)

Every value printed on a mismatch, every command quoted in a corruption incident, and every
standing-check log line passes through `audit_redact_before_write`: the value half of a
`keyword<sep>value` pair (sep = `:` or `=`) is replaced by `<redacted-per-§11.4.10>` while the
keyword is kept. Keywords (case-insensitive): `password`, `passwd`, `secret`, `api_key`
(also `api-key`/`apikey`), `access_token`, `auth_token`, `client_secret`, plus the
project extension `key`, `token`, `cookies`. Comparison itself uses the raw values; only
what is printed or written is redacted. Bare `key`/`token` over-redact by design.

**Inputs**: `docs/workable_items.db` (read-only), `constitution/scripts/gates/`
(read-only, via `cm_gate_ledger_ratchet.sh`), `docs/QA_DISCOVERY_LEDGER.md` (read-only),
`docs/qa/<item-id>/closure_evidence_*.md` (read; `verify-closure`).

**Outputs**: A human-readable or `--json` report; `standing-check` appends one line to
`docs/qa/zero_shortcomings_audit/<run-id>.log`; `verify-closure` appends to the same log
only when the corruption guard reverted something.

**Side-effects**: None in `enumerate`. `standing-check` writes its log line.
`verify-closure` executes the recorded command (`eval`), may revert corrupted tracked
evidence files, and with `--reopen-on-mismatch` may call the `workable-items` CLI to
reopen an item.

**Dependencies**: `sqlite3`, `git`, `constitution/scripts/workable-items/workable-items`,
`constitution/scripts/gates/cm_gate_ledger_ratchet.sh`, and `scripts/lib/audit_*.sh`.

**Cross-references**: `specs/003-zero-shortcomings-audit/{spec,plan,research,data-model}.md`.

**Last verified**: 2026-09-26 (against the script source; the `--help` text itself was run).
