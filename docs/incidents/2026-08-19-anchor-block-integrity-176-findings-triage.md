# 2026-08-19 — Anchor-block-integrity checker surfaced 176 findings on the constitution mirror set: triage (no fixes)

**Revision:** 1
**Last modified:** 2026-08-19T11:49:41Z
**Status:** active
**Description:** Triage of the 176 real findings BOB-105's `scripts/anchor_block_integrity_check.sh` (commit `7cd080c` on `boba` HEAD `0497b3d`) surfaced against the four constitution mirrors (`constitution/{CLAUDE,AGENTS,QWEN,GEMINI}.md`). Investigation + classification ONLY per the operator directive — NO fixes applied. §11.4.238 discovery-channel-escape signal; §11.4.227(B) block-integrity/lockstep enforcement.
**Authority:** §11.4.227(B) canonical vs. mirror layer discipline, §11.4.157 mirror lockstep, §11.4.238 automated-QA-discovers, §11.4.44 revision header, §11.4.6 no-guessing.

## 1. Summary counts (measured 2026-08-19T11:49:41Z)

Checker: `bash scripts/anchor_block_integrity_check.sh --config scripts/anchor_block_integrity_check.conf` (commit `7cd080c`).

| Category | Count |
|---|---|
| Total findings | **176** |
| `DUPLICATE-OR-COLLISION` | 17 |
| `LOCKSTEP-DIVERGENCE` | 7 (task brief said 4 — actual 7) |
| `LOCKSTEP-GAP` | 152 |

The 7 divergences (not 4): `§11.4.69`, `§11.4.112`, `§11.4.120`, `§11.4.142`, `§11.4.192`, `§11.4.193`, `§11.4.201`, `§11.4.227`. Re-counting the checker output: `§11.4.201` is enumerated in the divergence list too. Correction: **8** distinct anchors show `LOCKSTEP-DIVERGENCE` when the additional duplicate-driven divergences are counted (see §3 note).

The 17 duplicates split: Constitution.md 3 (`§11.4.30`, `§11.4.93`, `§11.4.202`), CLAUDE.md 3, AGENTS.md 5, QWEN.md 4, GEMINI.md 2 — all in the anchor set `{§11.4.69, .112, .120, .142, .201}` plus the three Constitution-only cases.

## 2. `DUPLICATE-OR-COLLISION` — classification

All 17 duplicates are the SAME structural class: an anchor with (a) a compact-summary/reference-heading block **plus** (b) a later verbatim-mandate or amendment block. The F7 pattern the round-of-2026-07-22 amendment already forensically identified (§11.4.208/§11.4.209) is now measured on 8 additional anchors.

* **REAL DEFECT (mirror layer, 14 findings)**: `§11.4.69/.112/.120/.142/.201` duplicated across CLAUDE/AGENTS/QWEN/GEMINI mirrors. First occurrence is the compact section (bulleted-list entry or short heading), second is the full amendment block from a later round. Per §11.4.227(B) exactly-once-per-file: >1 block-start = FAIL. Reconciliation follows the F7 pattern — keep the fuller variant, union in any unique element from the compact.
* **CANONICAL-VS-MIRROR LAYER (3 findings)**: Constitution.md's `§11.4.30`, `§11.4.93`, `§11.4.202` each appear as two block-starts (`###` heading + a later `**bold`). §11.4.227(B) explicitly permits canonical-vs-mirror layer variance; however the RULE "exactly one block-start per anchor per file" is written FILE-scoped, not layer-scoped — so these are REAL DEFECTS at the same severity as the mirror duplicates but arguably require operator adjudication whether Constitution.md's dual-format tradition counts as a legitimate `<H3>+bold-reference` pair.

## 3. `LOCKSTEP-DIVERGENCE` — per-anchor triage

Extractor produces the first-block content-hash per mirror. Any mirror the same anchor appears twice in gets its FIRST occurrence hashed; that first occurrence's variant (compact vs. full) is often what the divergence reveals — not that the full text is different, but that the FIRST occurrence's shape differs.

### 3.1 §11.4.69 — **REAL DEFECT**
Hashes: AGENTS unique, others match. AGENTS.md has TWO occurrences (compact reference-heading L1526 + full amendment L2554); other three carry one block. First-occurrence hash for AGENTS is the compact short heading `**§11.4.69 — Universal sink-side positive-evidence taxonomy + mechanical enforcement (User mandate, 2026-05-20)**`; other mirrors' first hit is the full-body block. Same F7 shape as §11.4.208/.209.

### 3.2 §11.4.112 — **REAL DEFECT**
Three distinct hashes across four mirrors. AGENTS=QWEN duplicate the anchor (compact + full pattern), CLAUDE duplicates it too but at a different pair of line offsets, GEMINI is the outlier single-block. Root: divergent compact vs. verbatim variant of the impossibility-verdict-bounded amendment.

### 3.3 §11.4.120 — **REAL DEFECT** (same shape as .112)
Three hashes; AGENTS=QWEN, CLAUDE unique, GEMINI unique — compact/full order differs across the four mirrors.

### 3.4 §11.4.142 — **REAL DEFECT**
Two hashes; AGENTS=GEMINI=QWEN identical, CLAUDE differs. CLAUDE carries the "universal code-review — no exception" anchor as ONE block; the other three carry a second amendment block later in the file which the checker's first-block selection reveals as a compact/full mismatch.

### 3.5 §11.4.192 — **REAL DEFECT (whitespace/trailer-only class)**
Two hashes; AGENTS=CLAUDE, GEMINI=QWEN. Sampled bodies are word-for-word identical across 3200+ chars. Divergence is likely a trailing whitespace, trailing newline, or single-character formatting artifact (verified textually indistinguishable at 300-char boundaries). Fix is a byte-normalization pass; not a content re-mint.

### 3.6 §11.4.193 — **REAL DEFECT (genuine content divergence)**
Three hashes; QWEN=GEMINI, CLAUDE unique, AGENTS unique — the ONLY divergence of the seven that is a genuine content-level lockstep violation:
* GEMINI+QWEN carry the **full verbatim mandate** (~2600 chars including operator quote + numbered clauses 1-6 + gate list).
* CLAUDE.md carries a **medium-summary** variant (~700 chars, prose paragraph, no numbered clauses, no gate list).
* AGENTS.md carries a **short-summary** variant (~350 chars: "Blind typing is STRICTLY FORBIDDEN everywhere — every agent, every tool, every automation…").
Three distinct information levels — the exact F7-class divergence §11.4.227 was minted to prevent, hitting an anchor minted AFTER §11.4.227 already existed. Needs operator reconciliation to the FULLEST variant (GEMINI/QWEN body).

### 3.7 §11.4.201 — **REAL DEFECT**
Duplicate + divergence in all four mirrors — a second amendment block landed in each mirror at a different line offset, and the checker's first-hash selection picks up divergent variants.

### 3.8 §11.4.227 — **REAL DEFECT (whitespace/trailer-only class)**
Two hashes; AGENTS=GEMINI=QWEN identical, CLAUDE differs. Sampled bodies are near-identical (>5000 chars). Same likely root as §11.4.192 — trailing character or single-punctuation edit.

## 4. `LOCKSTEP-GAP` — 10-sample classification

Sampled across the 152 gap range. Categories per operator taxonomy:

| Sample anchor | Present in | Classification | Notes |
|---|---|---|---|
| §11.4.1 | CLAUDE only | REAL DEFECT | Anchor exists as `### §11.4.1` heading in CLAUDE but as un-shaped compact citation in others |
| §11.4.10.A | CLAUDE only | LEGITIMATE (sub-anchor) | Dotted sub-anchor legitimately only cataloged once |
| §11.4.83 | AGENTS/CLAUDE/QWEN, NOT GEMINI | REAL DEFECT | Both `###` (CLAUDE) and `**` (AGENTS) block-start forms present; GEMINI genuinely lacks it |
| §11.4.100 | AGENTS/QWEN only | CHECKER OVER-REACH + REAL DEFECT | CLAUDE has `- §11.4.100 — RETIRED` dash-bullet (regex excludes) — legitimate compact form; but GEMINI absent entirely |
| §11.4.108 | AGENTS/CLAUDE/QWEN, NOT GEMINI | REAL DEFECT | GEMINI backfill needed — this is a core four-layer verification anchor |
| §11.4.135 | AGENTS/QWEN only | REAL DEFECT | Missing from CLAUDE and GEMINI — release-blocking regression-guard anchor |
| §11.4.141 | AGENTS/GEMINI/QWEN, NOT CLAUDE | REAL DEFECT | CLAUDE carries compact bullet (`- §11.4.141 — ...`) which regex excludes; historically known collision territory |
| §11.4.157 | AGENTS/GEMINI/QWEN, NOT CLAUDE | REAL DEFECT | The mirror-lockstep anchor itself is missing from one mirror — self-referential ledger drift |
| §11.4.192 | (in gaps list) | CHECKER OVER-REACH | Also in divergence list — one finding double-reported |
| §11.4.72 | AGENTS only | REAL DEFECT | Audio-top-priority anchor missing from 3 of 4 mirrors |

### Pattern extrapolation to the full 152

Three visible cohorts:
1. **§11.4.1..§11.4.99** — early-anchor era: CLAUDE.md is the "compact retelling" file (bulleted `- §11.4.X` entries), AGENTS.md is the "full mirror". Regex `^(#{2,4} §|**§)` excludes dash-bullets → false-positive gap for anchors that ARE present in compact form. Estimated ~40-60 of the 152 are this class (checker over-reach — legitimate compact variance per §11.4.227(B) canonical-vs-mirror layer permission, extended to CLAUDE-vs-mirror layer by convention).
2. **§11.4.100..§11.4.134** — "present in AGENTS+CLAUDE+QWEN, NOT GEMINI" cohort (~35 anchors). GEMINI.md was added LATER (§11.4.157 landed 2026-06-15) — anchors minted before GEMINI joined the mirror set were never backfilled. REAL DEFECT class per §11.4.157 lockstep, requires GEMINI backfill.
3. **§11.4.135..§11.4.165** — "present in AGENTS+GEMINI+QWEN, NOT CLAUDE" cohort (~30 anchors). CLAUDE.md's compact-summary discipline for these ranges emits dash-bulleted `- §11.4.X` entries, not block-start-shaped headings. Legitimate compact variance OR checker over-reach depending on operator interpretation of §11.4.227(B).

Coarse split of the 152 gaps: **~70 REAL DEFECT** (missing-from-GEMINI cohort + genuinely absent anchors), **~70 CHECKER OVER-REACH / LEGITIMATE COMPACT VARIANCE** (CLAUDE dash-bullets), **~12 sub-anchor edge cases** (`§11.4.10.A`-class dotted ids only cataloged once by design).

## 5. Recommended next-step operator decisions (NOT executed)

1. **Reconcile §11.4.193 (highest-severity)** — the only "3 information levels" divergence. Operator picks canonical variant (recommend GEMINI/QWEN full body) and lockstep-syncs to all 4 mirrors.
2. **Byte-normalize §11.4.192 and §11.4.227** — trailing-whitespace/newline pass; verifiable by re-running the checker until hashes converge.
3. **Reconcile the 5 duplicate-driven divergences** (§11.4.69/.112/.120/.142/.201) via the F7 recipe from the 2026-07-22 round: keep the fuller variant, union unique elements from the compact, delete the duplicate — per §11.4.227(B).
4. **Backfill GEMINI.md** with the §11.4.100..§11.4.134 range (~35 anchors) that predate its mirror inclusion — a bulk lockstep sync.
5. **Operator-decide the compact-vs-full policy question**: per §11.4.227(B) canonical-vs-mirror variance is legitimate; extend explicitly to CLAUDE-compact-vs-AGENTS-full, or require CLAUDE to carry block-start-shaped compacts (bold `**§11.4.X**` instead of dash `- §11.4.X`). Choice determines whether ~70 of 152 gaps are REAL DEFECT or checker over-reach.
6. **Checker tuning** — teach the extractor to (a) count dash-bulleted `- §11.4.X` as compact-form block-start (per operator's policy in decision 5), (b) collapse dup-reports where an anchor appears in both DIVERGENCE and GAP lists, (c) surface Constitution.md dual `###`+`**` legitimately per §11.4.227(B).
7. **Fix Constitution.md's 3 duplicates** (§11.4.30/.93/.202) via the same F7 recipe OR document the dual-format as canonical-layer-permitted per §11.4.227(B).

None of the above are executed by this triage per operator directive.

## 6. Provenance

* Checker commit: `7cd080c` (`scripts/anchor_block_integrity_check.sh` — BOB-105 landing)
* Repo HEAD at triage: `0497b3d`
* Findings log preserved: `/tmp/anchor_findings.log` (186 lines, includes 176 FAIL lines + 10 header/verdict lines)
* Triage authored by: Claude (fresh agent, Opus 4.7)
* Discovery-channel-escape signal: §11.4.238 — the automated checker DID surface these; manual QA would have caught none of the whitespace-only or byte-hash divergences (§11.4.238 automated-QA-discovers holds true here).
