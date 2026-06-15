# DRAFT — Universal constitution rule: docs/features Status set with video-recording confirmation

**Revision:** 1
**Last modified:** 2026-06-15T00:00:00Z
**Status:** DRAFT — NOT applied. Constitution edits require the §11.4.26 fetch-first workflow + §11.4.142 independent review, run by the main agent.

---

## CRITICAL FINDING — the requested rule is ALREADY in the constitution (near-total overlap)

Before drafting a new anchor, I reconciled the operator's PART 1 request against the existing
constitution (`constitution/Constitution.md`). The request is **already covered, almost verbatim**, by
three anchors that were all added TODAY (2026-06-15):

- **§11.4.153** — "Comprehensive per-feature Status + Status_Summary document set with mandatory
  video-recording confirmation". Mandates a `docs/features/` Status + Status_Summary set covering
  EVERY system component, EVERY client app/binary/surface (TUI/CLI/Web/desktop/mobile/API/gRPC/library/
  submodule/infra), and EVERY feature (incl. features ported from incorporated CLI-agents / submodule
  catalogue). Per-feature fields: **Component, Feature, Category, Implementation, Wiring, Real-use,
  Tests-coverage, Validation (PASS/FAIL/SKIP/PENDING_FORENSICS/OPERATOR-BLOCKED), and Video-recording
  confirmation** (path to captured real-use video). Clause (4) is the **video-analysis remediation
  loop** (analyse → systematic-debug → fix → retest → re-record). Clause (5) is docs_chain + §11.4.86
  fingerprint always-in-sync. Clause (6) is **HTML + PDF + DOCX** four-format export.
- **§11.4.154** — Window-scoped capture (NOT whole-screen) + fresh-corpus rotation (remove own prior
  in-scope recordings when a new run starts).
- **§11.4.155** — Project-name-prefixed recording filenames (`<PREFIX>---<scope>---<run-id>.<ext>`),
  prefix resolved via `HELIX_RELEASE_PREFIX` env (`.env`) → fallback lowercased snake_case repo-dir name.

**Mapping of the operator's PART 1 request to existing anchors:**

| Operator's PART 1 ask | Already covered by |
|---|---|
| Status + Status_Summary under `docs/features` for ALL components/client-apps/features | §11.4.153 (1)(7) |
| Columns: development / wiring / real-use / tests-coverage / validation / verification | §11.4.153 (2) — Implementation/Wiring/Real-use/Tests-coverage/Validation |
| MANDATORY video-recording-confirmation column | §11.4.153 (2)(3) — "Video-recording confirmation" field |
| Real use-case playthrough recorded | §11.4.153 (3) + §11.4.154 (window-scoped) |
| Analyzed by an AI ensemble, problems fixed/retested | §11.4.153 (4) — video-analysis remediation loop |
| Exported to PDF/DOCX/HTML | §11.4.153 (6) — four-format export (adds DOCX) |
| Tightly wired via docs_chain so no feature missed | §11.4.153 (5) — docs_chain + §11.4.86 fingerprint |

**Conclusion (recommendation to the main agent):** Do **NOT** add a duplicate §11.4.156. Per §11.4.17
classification discipline and the constitution's own no-duplication principle, a new universal anchor
restating §11.4.153/.154/.155 would be redundant and a maintenance hazard.

The only genuinely-new element in the operator's phrasing vs. the existing text is the explicit
**"verification" column as distinct from "validation"**, and the explicit naming of the **"AI ensemble"**
(the existing §11.4.153 (4) says "analysed" + §11.4.102 loop but does not name an ensemble). These are
small deltas. Two options for the main agent (recommend Option A):

- **Option A (RECOMMENDED) — project-side instantiation only, no new universal anchor.**
  §11.4.153 already says (per §11.4.35) "the consuming project supplies its concrete `docs/features/`
  layout, feature roster source, recording path, and DOCX exporter". So Boba should just INSTANTIATE
  §11.4.153/.154/.155 in its own `docs/features/` + `CLAUDE.md`/`AGENTS.md` project layer — including
  naming the HelixAgent ensemble as its concrete video-analysis mechanism and adding a separate
  "Verification" column if the operator wants validation/verification split. No constitution change.

- **Option B — tiny refinement to §11.4.153 only (NOT a new §11.4.156).** If the operator insists the
  universal text must (i) split Validation vs Verification into two columns and (ii) explicitly name an
  AI-ensemble video-analysis layer, add ONE sentence to §11.4.153 clause (2) and clause (4). This is a
  §11.4.73 secondary/revision-level refinement, not a primary new anchor. Draft sentence below.

---

## DRAFT refinement sentence for §11.4.153 (Option B only — apply via §11.4.26 workflow)

> Clause (2) addendum: each feature row's evidence axis MAY be split into a **Validation** column
> (the test/gate verdict — PASS/FAIL/SKIP/PENDING_FORENSICS/OPERATOR-BLOCKED per §11.4.45) AND a
> distinct **Verification** column (independent confirmation the feature works for the end user via
> captured real-use evidence per §11.4.69/§11.4.107 — the video-recording confirmation IS the primary
> verification artefact); a project that maintains both columns MUST keep them consistent (a Validation
> PASS with a Verification FAIL is a §11.4.4 test-interrupt, never a confirmed row).
>
> Clause (4) addendum: the per-video analysis MAY be performed by an AI-ensemble video-analysis layer
> (e.g. an incorporated `vasic-digital`/`HelixDevelopment` HelixAgent ensemble per §11.4.74) so the
> recognition of the video's presented data is itself multi-model and anti-bluff; the ensemble's verdict
> is captured evidence per §11.4.5/§11.4.69 and any defect it surfaces drives the §11.4.102 → fix →
> §11.4.146 retest → re-record loop to a clean GO per §11.4.134. The ensemble layer COMPLEMENTS, never
> replaces, the §11.4.107 liveness battery + §11.4.137 content-correctness oracle the row also cites.

Classification (per §11.4.17): **universal** — generic across any project; references no project-specific
hardware/vendor. But it is a REFINEMENT of §11.4.153, not a standalone new anchor → it stays inside
§11.4.153, bumping the Constitution `Revision` (§11.4.73 secondary-version bump), NOT consuming the next
free anchor number.

---

## Next free anchor number (if Option B is rejected and the operator truly wants a NEW anchor)

Latest existing anchor in `constitution/Constitution.md` = **§11.4.155**. The next free number is
**§11.4.156**. (Drafting a full §11.4.156 is intentionally NOT done here because it would duplicate
§11.4.153 — see the conclusion above. If the operator confirms they want a standalone anchor anyway,
the main agent should draft §11.4.156 in the §11.4.153 house style, opening with a verbatim forensic
anchor, composing §11.4.45/.56/.86/.106/.107/.128/.143/.153/.154/.155, with a `CM-COVENANT-114-156-PROPAGATION`
gate + recommended functional gate + paired §1.1 mutation, and explicitly stating in its own text how
it differs from §11.4.153 to avoid a no-op duplicate.)

---

## DRAFT short mirror paragraph for CLAUDE.md / AGENTS.md / QWEN.md

Use this ONLY if Option B (the §11.4.153 refinement) is applied; the §11.4.153/.154/.155 mirror
paragraphs already belong in the consumer files. This is the project-layer instantiation note Boba
should add regardless (Option A):

> **§11.4.153/.154/.155 project instantiation (Boba).** Boba maintains its feature ledger under
> `docs/features/Status.md` + `Status_Summary.md` (+ HTML/PDF/DOCX), covering every component
> (download-proxy, merge service, boba-jackett, qBittorrent-go proxy, webui-bridge, plugins) and every
> client surface (Angular `frontend/` web dashboard, FastAPI Jinja2 dashboard :7187, `cmd/boba-ctl` CLI,
> `extension/` BobaLink browser extension). Each user-visible feature's confirmation cites a window-scoped
> (§11.4.154) real-use recording under `/Volumes/T7/Downloads/Recordings`, filename prefixed `boba---…`
> (§11.4.155 — `HELIX_RELEASE_PREFIX` unset → fallback lowercased repo-dir name `boba`), analysed by the
> HelixAgent ensemble (`/Volumes/T7/Projects/helix_code/submodules/helix_agent`, per §11.4.74) with the
> §11.4.102→fix→§11.4.146→re-record loop. Always-synced via docs_chain (§11.4.106) + §11.4.86 fingerprint.
> **Blocker:** neither the HelixAgent ensemble nor docs_chain is currently a Boba submodule — both must
> be incorporated per §11.4.74/§11.4.36 before the ensemble-analysis + docs_chain clauses can be honoured.
