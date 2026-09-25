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
