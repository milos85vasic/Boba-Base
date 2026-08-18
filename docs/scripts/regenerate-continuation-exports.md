# scripts/regenerate-continuation-exports.sh — surgical CONTINUATION.md export regen

**Revision:** 1
**Last modified:** 2026-08-18T22:47:00Z
**Status:** active

## Overview

`scripts/regenerate-continuation-exports.sh` regenerates
`docs/CONTINUATION.html` and `docs/CONTINUATION.pdf` from
`docs/CONTINUATION.md` via a direct `pandoc` (+ `weasyprint`) invocation. It
exists to close a specific, narrow gap: `docs/CONTINUATION.md` is edited
frequently (per §12.10, every non-trivial state change), but nothing
automatically regenerates its `.html`/`.pdf` siblings on every edit, so they
drift stale and trip pre-build invariant 16
(`CM-MARKDOWN-EXPORT-SYNC`, §11.4.65) in
`scripts/pre_build_verification.sh`.

## Why this script exists instead of just running the generic sweep

`scripts/generate_markdown_exports.sh` is the project's generic §11.4.65
exporter — it walks every `*.md` under the project root, `docs/`, and
`scripts/` and regenerates any `.html`/`.pdf`/`.docx` sibling older than its
source. `docs/CONTINUATION.md` **is** technically inside that script's scope
(it lives under `docs/`), so in principle running the generic sweep would
also fix CONTINUATION's stale exports.

It is deliberately **not** invoked here. Task #80 (docs_chain sync/verify
fix) found that `scripts/generate_markdown_exports.sh`'s mtime-gated pandoc
pass is docs_chain-unaware: it regenerates the `.docx` sibling for *any*
markdown file whose `.md` is newer than its `.docx`, including files that
are actually authored sources inside a registered
[Docs Chain](https://github.com/vasic-digital/docs_chain) context (see
`.docs_chain/contexts/codegraph-status.yaml` and
`.docs_chain/contexts/features-status.yaml`). Docs Chain owns the
`sync`/`verify` lifecycle for those files' derived exports; letting the
generic sweep race it corrupts the docs_chain-managed baseline (the exact
regression task #80 fixed).

`docs/CONTINUATION.md` is **not** a registered docs_chain context — a
`docs_chain sync --all` run touches nothing for it (confirmed: it reports
only the `codegraph-status` and `features-status` contexts, both unrelated).
So neither mechanism owns CONTINUATION's exports out of the box. Rather than
run the generic, project-wide sweep just to fix two files — and risk
re-triggering the class of docs_chain-baseline corruption task #80 already
had to remediate once — this script does a **surgical, single-target**
regeneration: it reads and writes nothing except
`docs/CONTINUATION.{html,pdf}`, using the identical pandoc/weasyprint
invocation shape `generate_markdown_exports.sh` uses, so the rendered output
stays visually/structurally consistent with every other exported doc in the
project.

## Prerequisites

- `bash`
- `pandoc` (hard dependency — the script exits non-zero if absent, since a
  missing exporter for a `CM-MARKDOWN-EXPORT-SYNC`-gated file is a real
  blocker, not a soft skip)
- `weasyprint` with a working `python3 -c "from weasyprint import HTML"`
  import (optional — the PDF step is skipped with an honest §11.4.3 reason
  if absent; the HTML step still runs)

## Usage

```bash
bash scripts/regenerate-continuation-exports.sh
```

No arguments, no flags. It always regenerates both exports unconditionally
on each invocation (it is a deliberately-invoked single-target regen, not a
sweep with its own mtime gate — a caller wanting mtime-gated behavior should
compare `docs/CONTINUATION.md`'s mtime against the exports before calling,
e.g. as part of a pre-commit hook).

### Example run

```
$ bash scripts/regenerate-continuation-exports.sh
[regen] docs/CONTINUATION.md -> docs/CONTINUATION.html
[regen] wrote /path/to/boba/docs/CONTINUATION.html
[regen] docs/CONTINUATION.html -> docs/CONTINUATION.pdf
[regen] wrote /path/to/boba/docs/CONTINUATION.pdf
[regen] done.
```

## Edge cases

- **`docs/CONTINUATION.md` missing** — hard failure (exit 1). The script
  never creates or edits `docs/CONTINUATION.md`; it is authoritative
  per §12.10 and is the input, never the output, of this script.
- **`pandoc` missing** — hard failure (exit 1). Since the whole point of the
  script is to satisfy a pre-build gate that requires the HTML export to
  exist and be fresh, silently skipping here would just relocate the
  original bluff rather than fix it.
- **`weasyprint` missing (or its Python import broken)** — the HTML step
  still runs; the PDF step is skipped with a printed `SKIP:` reason on
  stderr (§11.4.3). `CM-MARKDOWN-EXPORT-SYNC` will still FAIL on the missing
  `.pdf` in that environment — this is an honest reflection of what actually
  regenerated, not a workaround for the gate.
- **`docs/CONTINUATION.docx`** — out of scope for this script. The `.docx`
  sibling is a WARNING-only concern under `CM-MARKDOWN-EXPORT-SYNC`
  (missing/stale `.docx` never fails the gate, per BOB-011), so this script
  does not touch it. If a `.docx` refresh is ever wanted, run the generic
  `scripts/generate_markdown_exports.sh` sweep deliberately, accepting the
  docs_chain-interaction risk documented above.

## Internal behaviour

1. Resolve `PROJECT_ROOT` from the script's own location.
2. Verify `docs/CONTINUATION.md` exists; fail loudly if not.
3. Verify `pandoc` is on `PATH`; fail loudly if not.
4. `pandoc -f markdown -t html5 -o docs/CONTINUATION.html docs/CONTINUATION.md --metadata title="CONTINUATION"`
5. If `weasyprint` (and its Python bindings) are available:
   `weasyprint docs/CONTINUATION.html docs/CONTINUATION.pdf`
   Otherwise, print an honest skip reason and stop (exit 0 — the HTML
   export still landed).

## Related scripts

- `scripts/generate_markdown_exports.sh` — the generic §11.4.65 exporter
  this script deliberately does not invoke (see above).
- `scripts/pre_build_verification.sh` — invariant 16
  (`CM-MARKDOWN-EXPORT-SYNC`) is the gate this script exists to satisfy for
  `docs/CONTINUATION.md`.
- `constitution/scripts/render/render-governance-twins.sh` — a sibling
  single-purpose pandoc/weasyprint exporter (for the five governance twins:
  `Constitution.md`/`CLAUDE.md`/`AGENTS.md`/`GEMINI.md`/`QWEN.md`), following
  the same "don't run the generic sweep against a specially-owned doc set"
  pattern for a different reason (deterministic `SOURCE_DATE_EPOCH`-pinned
  rendering against a historical byte-identical baseline). CONTINUATION.md
  has no such baseline-pinning requirement, so this script does not pin
  `SOURCE_DATE_EPOCH`.

## Last verified

2026-08-18 — real invocation captured: `pandoc 3.10` produced
`docs/CONTINUATION.html` (61,660 bytes), `weasyprint` produced
`docs/CONTINUATION.pdf` (100,613 bytes), and a full
`scripts/pre_build_verification.sh` re-run afterward reported
`=== Result: 27 passed, 0 failed ===` with invariant 16
(`CM-MARKDOWN-EXPORT-SYNC`) reading
`PASS [17]: CM-MARKDOWN-EXPORT-SYNC: all in-scope docs have fresh
.html/.pdf siblings`.
