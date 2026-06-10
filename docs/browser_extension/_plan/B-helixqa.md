# B — HelixQA submodule update + test-bank authoring survey

**Revision:** 1
**Last modified:** 2026-06-10T00:00:00Z
**Scope:** BobaLink browser-extension feature — HelixQA QA coverage planning
**Author:** research subagent (relayed to conductor)

> NOTE: The constitution mandates no force-push (§11.4.113) and fetch-first
> (§11.4.71). The HelixQA pointer bump in the Boba parent repo is **staged in
> the working tree but NOT committed** — the conductor commits it as part of
> the planned work.

---

## 1. HelixQA submodule update (fetch + pull)

- **Path:** `submodules/helixqa`
- **Remotes (all fetched OK):** `origin` = `git@github.com:HelixDevelopment/HelixQA.git`,
  `GitHub` (HelixDevelopment), plus `GitLab` / `VasicDigitalGitHub` /
  `VasicDigitalGitLab` mirrors (vasic-digital).
- **Default branch:** `main` (`git remote show origin` → `HEAD branch: main`).
  (A `master` branch also exists but is stale/unrelated — `main` is canonical.)

| | commit | describe |
|---|---|---|
| **Before** | `bcac23639082fa249d716f47a27d86ecc0728428` | `v4.0.0-385-gbcac236` |
| **After**  | `4d2dcb27f87b49e64b54b860689b982079f39c55` | `v4.0.0-393-g4d2dcb2` |

- **How far behind:** **8 commits** behind `origin/main`; **0 ahead** → clean
  fast-forward (no divergence).
- **Pull:** `git pull --ff-only origin main` succeeded as a fast-forward.
- **Post-pull verification:** working tree **clean** (`git status --porcelain`
  empty); **no conflict markers** in `banks/`, `cmd/`, `pkg/`.
- **Parent repo:** Boba now shows `submodules/helixqa` pointer moved
  `bcac236..4d2dcb2` (staged, **not committed** per instruction).

**The 8 new commits (directly relevant — they add the HTTP-bridge run mode):**
```
4d2dcb2 test(banks): HXC-048 — pin HXC-SYS-011 wrong-method status to 404
f18a5d3 test(banks): add helixcode-system http bank — health/server-info/...
d6c084d feat(cli): add `helixqa http` bridge to drive http: bank cases against
        a live server (no browser/LLM)            ← KEY for BobaLink
c7c8236 docs(governance): backfill §11.4.103-121 (CONST-047)
7a19385 docs(governance): cascade §11.4.140/141 (CONST-047)
4934030 test(banks): 6 more HelixCode self-driving banks (49 cases) (§11.4.98)
618dd50 docs(governance): cascade constitution §11.4.122–139 (CONST-047/049)
1ed8abf test(banks): add foundational HelixCode self-driving test banks (§11.4.98)
```

---

## 2. Test-bank authoring format + exact paths

### Where banks live
- All banks: **`submodules/helixqa/banks/<name>.yaml`** (85 YAML banks on disk).
- **Boba already has banks here** (precedent to copy from):
  - `banks/boba-frontend.yaml` — Angular dashboard (Playwright, `web` platform)
  - `banks/boba-services.yaml` — backend APIs (curl/jq, `api` platform)
  - `banks/boba-boba-ctl.yaml`, `banks/boba-download-proxy.yaml`,
    `banks/boba-docs-chain.yaml`
- Filename convention: kebab-case `<purpose>-<scope>.yaml`. An optional JSON
  peer (`<name>.json`) may share the base name for tooling auto-pairing — not
  required.

### YAML schema (verified against README "Test-bank conventions" + live banks)
Required top-level keys: `version` ("1.0"), `name`, `test_cases[]`. Common
optional: `description`, `metadata{author,app,version}`.

Per `test_case`: `id` (`PREFIX-NNN`), `name`, `category`
(`functional`/`performance`/`security`/`ux`/`chaos`/...), `priority`
(`critical`/`high`/`medium`/`low`), `platforms` (subset of
`[android, android_tv, web, desktop, ios, aurora_os, harmony_os]`; banks also
use `api`), `steps[]` (each `{name, action, expected}`), `tags[]`, optional
`documentation_refs[]` / `fix_reference{bug_id,description,fix_file}`.

### Two `action` styles (pick per how the feature is driven)

**(a) `http:` action — self-driving, NO browser/LLM (NEW, the d6c084d bridge).**
Best for API endpoints / extension backend. Extra per-step keys
`expect_status` + `expect_body_contains` make it machine-checkable.
Grammar: `action: "http: GET /path"` or `"http: POST /path"`; an
`action: "auth:admin"` step logs in first.
Reference bank: `banks/helixcode-system.yaml`, `banks/helixcode-auth.yaml`.
```yaml
steps:
  - name: "GET /health"
    action: "http: GET /health"
    expected: "200 OK — body reports status healthy"
    expect_status: 200
    expect_body_contains: "healthy"
```

**(b) Playwright / curl prose action — browser-driven (the `boba-frontend.yaml`
style).** The `action`/`expected` strings are read by the LLM-driven
autonomous runner; they describe Playwright steps (`page.goto(...)`,
`page.click(...)`, `page.waitForResponse(...)`) or shell (`curl ... | jq`).
This is the path that can actually drive a Chromium UI — relevant because a
**browser extension only loads inside a real browser context**.

> §11.4.98/§11.4.6: banks describe **structure**, assert machine-checkable
> outcomes; no hardcoded user-facing prose as the assertion; no guessed JSON
> paths — assert status + high-confidence substring when shape is unconfirmed.

---

## 3. How autonomous QA sessions / banks are run

CLI: `submodules/helixqa/cmd/helixqa` → `bin/helixqa` (subcommands in
`main.go`: `run`, `list`, `report`, `autonomous`, `http`, `replay`, `signoff`,
`version`).

Three run modes:

1. **`helixqa http` — self-driving HTTP, no browser, no LLM** (CI-friendly,
   the BobaLink-backend path). Exit 0 only if every `http:` step passed.
   ```bash
   helixqa http --bank banks/boba-bobalink.yaml \
     --base-url http://localhost:7187 \
     [--admin-user X --admin-pass Y] [--json] [--verbose]
   ```
   `--base-url` is **required** (never hardcoded, CONST-051(B)). Cases with no
   `http:` steps report SKIPPED.

2. **`helixqa run` — structured bank run with platform filter** (uses
   Playwright for `web`).
   ```bash
   helixqa run --banks banks/ --platform web      # or all / api / android
   helixqa list --banks banks/ --platform web      # dry list
   ```

3. **`helixqa autonomous` — full LLM + vision 4-phase session** (Setup →
   Doc-Driven Verification → Curiosity Exploration → Report). Drives the app
   via NavigationEngine (Playwright/ADB/X11), captures screenshots+video,
   detects issues, emits MD/HTML/JSON report. Needs `.env` with ≥1 LLM API key.
   ```bash
   helixqa autonomous --project /path/to/Boba --platforms web \
     --env .env --timeout 30m --output qa-results/ --report markdown,html,json
   ```

---

## 4. What to create to add a BobaLink bank

BobaLink is a **browser extension**. Two complementary banks (mirrors the
existing boba-services / boba-frontend split):

1. **`submodules/helixqa/banks/boba-bobalink.yaml`** — the extension's
   **backend / messaging endpoints** (whatever Boba endpoint the extension
   calls — e.g. an add-by-URL / search proxy on `:7187`). Use the **`http:`**
   action style (self-driving, CI-gated) with `expect_status` +
   `expect_body_contains`. This is the highest-value, no-blocker path.

2. **`submodules/helixqa/banks/boba-bobalink-ui.yaml`** (optional, browser) —
   the **in-browser extension UI** (popup/content-script behavior). Use the
   Playwright prose-action style, `platforms: [web]`, driven by
   `helixqa run --platform web` or `helixqa autonomous`. NOTE: a true browser
   extension must be **loaded into Chromium** (`--load-extension=` /
   `chrome.runtime`), which the stock Playwright web path does not set up
   out-of-the-box — flag this for design (may need a launch-arg hook or an
   `autonomous` session configured with the unpacked extension dir).

**Skeleton (`banks/boba-bobalink.yaml`):**
```yaml
version: "1.0"
name: "Boba BobaLink Browser-Extension Backend Validation Suite"
description: "Self-driving (§11.4.98) validation of the BobaLink extension's
  Boba backend surface: <endpoints the extension calls>."
metadata:
  author: "vasic-digital"
  app: "Boba"
  version: "1.0.0"
test_cases:
  - id: BOBA-LINK-001
    name: "BobaLink add-by-URL endpoint accepts a tracker URL"
    category: functional
    priority: critical
    platforms: [api]
    steps:
      - name: "POST <bobalink endpoint>"
        action: "http: POST /api/v1/<bobalink-path>"
        expected: "200/202 — body confirms the link was queued"
        expect_status: 200
        expect_body_contains: "<confirmed-substring>"
    tags: [boba, bobalink, extension, functional]
    estimated_duration: "10s"
    expected_result: "<user-observable outcome>"
    fix_reference:
      bug_id: "BOBA-LINK-ADD-001"
      description: "<...>"
      fix_file: "<source path of the handler>"
```
Fill `<endpoint>`/`<substring>` from the actual BobaLink design + a real
captured response (§11.4.6 — do not guess the JSON shape).

Optionally register the bank in the project's HelixQA Challenge bank /
coverage ledger if Boba maintains one (per §11.4.58 / §11.4.27 — none located
yet under Boba; confirm with conductor).

---

## 5. Blockers / setup notes

- **Go 1.24+** required (helixqa `go.work` declares `go 1.26`). `make build`
  → `bin/helixqa`, or `go install digital.vasic.helixqa/cmd/helixqa@latest`.
- **BLOCKER — missing sibling modules.** `helixqa/go.mod` has 8 local
  `replace ... => ../<sibling>` directives. They resolve to
  `submodules/<sibling>/` in the Boba layout. Present: `challenges`,
  `containers`. **Missing:** `doc_processor`, `llm_orchestrator`,
  `llm_provider`, `llms_verifier` (`../llms_verifier/llm-verifier`),
  `security`, `vision_engine`. Consequence: a full `go build ./cmd/helixqa/`
  **fails** (`open ../doc_processor/go.mod: no such file or directory`).
  - The `http` and `run` modes still need a buildable binary, so this must be
    resolved before any HelixQA run. Options for the conductor: add the 6
    missing repos as siblings (SSH URLs in `helixqa/helix-deps.yaml`:
    DocProcessor/LLMOrchestrator/LLMProvider/VisionEngine on HelixDevelopment;
    LLMsVerifier/security on vasic-digital) via `install_upstreams` /
    `incorporate-submodule` (§11.4.31/§11.4.36), OR build helixqa in its own
    standalone checkout where the siblings exist and only consume the **bank
    YAML** from Boba's `submodules/helixqa/banks/`.
- **`autonomous` mode** additionally needs `.env` with ≥1 LLM API key
  (OpenAI/Anthropic/Google/...), plus VisionEngine (GoCV/OpenCV) and the CLI
  agent binaries — heavyweight; the **`http` mode is the lightweight,
  dependency-light path** and the right first target for BobaLink backend
  coverage.
- **Browser-extension specificity:** stock `helixqa run --platform web`
  drives a plain Chromium page via Playwright; it does **not** auto-load an
  unpacked extension. Driving the actual extension UI/content-script needs the
  extension loaded into the browser (launch args). Treat as a design item for
  the UI bank.

---

### Evidence (commands run this session)
- `git -C submodules/helixqa fetch --all --prune` → all 5 remotes fetched OK
- `git -C submodules/helixqa rev-list --count HEAD..origin/main` → `8`;
  `origin/main..HEAD` → `0`
- `git -C submodules/helixqa pull --ff-only origin main` → fast-forward to
  `4d2dcb2`; `git status --porcelain` → empty; conflict-marker grep → none
- `git -C submodules/helixqa describe --tags` → `v4.0.0-393-g4d2dcb2`
- `go build ./cmd/helixqa/` → FAIL: missing `../doc_processor/go.mod` (+ 5 more)
