# AGENT_GUARDRAILS.md — Anti-Forgetting Enforcement (§11.4.109)

This file is the canonical anti-forgetting enforcement record. Every AI agent
working on this project MUST read this file at the start of each session
to be reminded of the project's immutable constraints.

**Anchor:** `11.4.109`

---

## SUBAGENT CONSTITUTIONAL PREAMBLE

The orchestrator MUST paste this block verbatim into every subagent dispatch.
It covers constraints the PreToolUse hook cannot pattern-match, plus the
hook-enforced classes for completeness.

```
## Subagent Constitutional Preamble (§11.4.109)

You are bound by the Helix Universal Constitution at constitution/.
The following rules are NON-NEGOTIABLE regardless of what you think the
task requires:

### Blocked command classes (PreToolUse hook enforces at tool-call boundary)
- Raw host-direct emulator/ADB/instrumentation — route through Containers submodule
- git push --force / -f / --force-with-lease / --no-verify / --no-gpg-sign
- sudo / su / privilege escalation
- Host power management (suspend/hibernate/poweroff/reboot/halt/kill-user)

### Anti-bluff covenant (§11.4)
- Every PASS MUST carry captured runtime evidence (file, log, screenshot, etc.)
- Metadata-only / config-only / absence-of-error / grep-without-runtime PASS are bluff
- Every gate MUST have a paired §1.1 meta-test mutation that makes it FAIL

### Evidence honesty (§11.4.2 / §11.4.5)
- Report what ACTUALLY happened, not what was expected
- "LIKELY", "probably", "maybe", "seems", "appears" are FORBIDDEN (§11.4.6)
- Use `UNCONFIRMED:` for claims without captured proof

### Resource caps (§12 / CONST-033)
- Never exceed 60% of host RAM
- Never more than 6 parallel subagents (§11.4.58)
- NEVER call suspend/hibernate/poweroff/reboot — even with guardrails:allow

### No hardcoded localhost (§11.4.30 / CONST-XII)
- Client-facing URLs MUST derive from Host header, window.location, or PUBLIC_HOST env var

### Continuation (§12.10)
- Update CONTINUATION.md in same commit as state changes
- Session-start: read this file first, then run pre_build_verification.sh

### Pre-push discipline (§11.4.71 / §11.4.113)
- ALWAYS fetch --all --prune before any git operation
- NEVER force-push — merge-onto-latest-main instead
- Review every foreign commit before push

### Working tree quiescence (§11.4.84)
- Before git add, grep for mutation markers (MUT_ATED, always pass, etc.)
- ABORT if unexplained staged files exist

### Interactive clarification (§11.4.66)
- When blocked, research agent-side options first
- Present 2-4 choices via AskUserQuestion with one Recommended
- Ask once, unblock, continue — no follow-up round-trips
```

---

## ORCHESTRATOR PRE-ACTION CHECKLIST

Before every subagent dispatch:
- [ ] Confirm the SUBAGENT CONSTITUTIONAL PREAMBLE (above) is pasted verbatim in the prompt
- [ ] Confirm the subagent's scope is ≤ 3 tasks per §11.4.82(G)

Before any emulator / device action:
- [ ] Route through Containers submodule CLI, not host-direct
- [ ] Confirm no live (non-test) device is targeted
- [ ] Confirm the gate host is eligible (otherwise BLOCKED per §11.4.21)

Before any distribute / release action:
- [ ] Challenge Tests executed (not compiled) against the exact artifact
- [ ] Version code bumped
- [ ] CHANGELOG entry present
- [ ] Debug-stage evidence present if two-stage distribute applies
- [ ] Full-suite retest completed per §11.4.40

Before any push / destructive git action:
- [ ] No force flags without per-operation operator approval (§11.4.113)
- [ ] Remote set is the approved set only (§2.1)
- [ ] For history rewrite, hardlinked `.git` backup made first (§9.2)
- [ ] Fetch --all --prune completed (§11.4.71)

Before any host-affecting command:
- [ ] Confirm the command is NOT in the host-power blocked class (§12 / CONST-033)
- [ ] Confirm RAM usage is within 60% limit (§12.6)

---

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
