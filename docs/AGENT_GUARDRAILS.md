# AGENT_GUARDRAILS.md — Anti-Forgetting Enforcement (§11.4.109)

This file is the canonical anti-forgetting enforcement record. Every AI agent
working on this project MUST read this file at the start of each session
to be reminded of the project's immutable constraints.

## Immutable Constraints

- §11.4.10: Credentials are NEVER committed. `.env` is gitignored.
- §11.4.30: `.gitignore` must cover all sensitive patterns.
- §11.4.44: All `docs/**/*.md` files carry revision headers.
- §11.4.65: Every `.md` file has a sibling `.html` and `.pdf` export.
- §11.4.75: Pre-commit, pre-push, commit-msg, and post-commit hooks are active. Do NOT bypass them.
- §11.4.85: Stress and chaos tests exist. Wire them before release.
- §11.4.109: This file MUST be read at session start.
- §11.4.113: Force-push (`--force`, `--force-with-lease`, `push +`) is STRICTLY FORBIDDEN.
- §11.4.125: Code-review gate runs before pre-build. NO bypass.
- §11.4.78: CodeGraph integration is required.
- §11.4.24: Build-resource stats tracking is required.
- §11.4.66: Interactive clarification must be used when blocked.

## Session Start Ritual

Every agent session starts with:
1. Read this file.
2. Run `bash scripts/pre_build_verification.sh` to confirm all invariants hold.
3. Run `bash tests/test_constitution_inheritance.sh` to confirm inheritance chain is intact.
4. Proceed with the task.
