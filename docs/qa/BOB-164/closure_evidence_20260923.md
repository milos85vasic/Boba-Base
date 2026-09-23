# BOB-164 — closure evidence (re-verification pass, 2026-09-23)

| Field | Value |
|---|---|
| Revision | 1 |
| Last modified | 2026-09-23T15:13:00Z |
| HEAD | `ffe3ed3` |
| Verdict | Fix already landed. No source change needed in this pass. The rendered-DOM oracle is GREEN on the SHIPPED artifact across all 16 palette × mode combinations. The LIVE-service acceptance leg was NOT run because the stack is down. |

## 1. Systematic-debugging outcome (§11.4.102): item is stale-as-open, not broken

- The root-cause fix is commit `5f9a04b` ("fix(BOB-164): contrast failed because a literal cannot
  be correct against a fill that moves with the palette"). It introduced the `accentText` role and
  the `on<Fill>` tokens. The round-2 evidence is in `docs/qa/BOB-164/README.md`.
- The artifact-layer gap that README §9 recorded (a stale `dist/`) was tracked as BOB-183, which is
  now Fixed. The shipped bundle `download-proxy/src/ui/dist/frontend/browser/` was rebuilt on
  2026-09-22. The last commit touching `frontend/src` is `deed8bf` from 2026-09-02, so the bundle
  is newer than its sources. `git status` shows no uncommitted changes under `frontend/src` or
  `download-proxy/src/ui`.
- I made no production change. None was warranted: forcing a change onto an already-fixed defect
  would violate §11.4.6 and §11.4.120.

Shipped bundle fingerprint:
`sha256(main-CLXE6FZU.js) = 44cca2500f975582d4f5b9349de45f09e22e212e6250d026f5850fb989841832`

## 2. The oracle is validated before any result from it is believed (§11.4.107(10) / §11.4.273)

```
$ .venv/bin/python docs/qa/BOB-164/axe_contrast_scan.py --self-check      # rc=0
  golden-bad  #golden-bad-equal    CAUGHT
  golden-bad  #golden-bad-plain    CAUGHT
  neg-control #negative-control  correctly silent

self-check: PASS
```

## 3. RED: the defect re-injected into a scratch copy of the SHIPPED artifact

Mutation (scratch copy only, the repo was not touched): in the shipped `main-CLXE6FZU.js`, the
darcula/dark `accentText:"#ffaebd"` was replaced with the pre-fix `accentText:"#9d001e"`. The
original value occurred exactly once before the replacement and 0 times after it. Mutant
fingerprint: `5421f09e…dbb85`.

```
$ axe_contrast_scan.py --dist <scratch>/dist_red --all-palettes --out <scratch>/scan_RED_mutant.json
rc=1
=== theme darcula/dark: 5 colour-contrast violation node(s), 22 passing node(s) ===
  .brand[_ngcontent-ng-c230444366=""]  fg=#9d001e bg=#3c3f41 12.0pt/700 axe=1.43 py=1.44 floor=4.5 (ratio+floor agree)
  h1                                   fg=#9d001e bg=#3c3f41 18.0pt/700 axe=1.62 py=1.62 floor=3.0 (ratio+floor agree)
  h2                                   fg=#9d001e bg=#3c3f41 16.5pt/700 axe=1.45 py=1.46 floor=3.0 (ratio+floor agree)
  .active.tab                          fg=#9d001e bg=#3c3f41 12.0pt/400 axe=1.44 py=1.44 floor=4.5 (ratio+floor agree)
  .vd-link                             fg=#9d001e bg=#2b2b2b  9.8pt/400 axe=1.8  py=1.79 floor=4.5 (ratio+floor agree)
  [incomplete/FAIL] .stat-item:nth-child(1..3) > .stat-value  fg=#9d001e bg=#2b2b2b py=1.95 floor=3.0
TOTAL colour-contrast violation nodes across 16 theme(s): 5
TOTAL blocking `incomplete` nodes (FAIL / UNDECIDABLE / GLYPH_FAIL): 3
```

This matches the reported pairs exactly: `.brand` at 1.43:1 and `h1` at 1.62:1, `#9d001e` on
`#3c3f41`. So on this exact artifact and code path, the oracle does detect the defect class.

## 4. GREEN: the unmodified shipped artifact

```
$ axe_contrast_scan.py --dist download-proxy/src/ui/dist/frontend/browser --all-palettes --out <scratch>/scan_shipped_all.json
rc=0
... (every theme) 0 colour-contrast violation node(s), 30 passing node(s) ...
TOTAL colour-contrast violation nodes across 16 theme(s): 0
TOTAL blocking `incomplete` nodes (FAIL / UNDECIDABLE / GLYPH_FAIL): 0
TOTAL fenced GLYPH_UNMEASURED nodes (reported, not blocking; SC 1.4.11 unverified): 40
```

Arithmetic (declared-pair) oracles, run individually:

```
$ cd frontend && npx ng test --watch=false \
    --include=src/app/models/palette.contrast.spec.ts --include=src/app/models/style-contrast.spec.ts
 Test Files  2 passed (2)
      Tests  2371 passed (2371)
rc=0
```

## 5. Honest gaps (§11.4.6): why the tracker item is NOT closed

1. **The live-service leg did not run.** The acceptance criterion names
   `tests/ux/test_live_dashboard_accessibility.py` against the running merge service.
   `curl http://localhost:7187/health` returned `000`, so the stack is down. I did not boot it: host
   memory is tight, and `merge_service_live` → `compose_up` would start the whole container stack.
   The GREEN above is ARTIFACT-class evidence: the real shipped bundle, rendered in real Chromium,
   measured by real axe-core, served statically with no backend. It is not the RUNTIME-class
   live-surface flip that §11.4.226 requires for closure. **Owed:** start the stack (`./start.sh`),
   then run `.venv/bin/python -m pytest tests/ux/test_live_dashboard_accessibility.py -v` and confirm
   `test_live_dashboard_axe_scan` passes.
2. **Data-driven nodes** (badges and status pills) are absent from a no-backend render. This is
   tracked as BOB-185. The arithmetic spec covers them.
3. **Icon glyphs**: 40 GLYPH_UNMEASURED nodes, and SC 1.4.11 is unverified for them. This is
   tracked as BOB-184.
4. **§11.4.185 manual QA**: no human has looked at the colours. This is still owed.
5. `/jackett/*` routes were not rendered and scanned in this pass.

## Live-surface addendum (conductor, 2026-09-23 ~18:56 CEST)
Stack recreated from HEAD 69b049a (all four containers healthy). Command: `.venv/bin/python -m pytest tests/ux/test_live_dashboard_accessibility.py --import-mode=importlib -q` -> `3 passed in 3.08s` (rc=0, no skips), including test_live_dashboard_axe_scan against the running dashboard.
The live surface therefore agrees with the artifact-level RED->GREEN above (pre-fix #9d001e failing at 1.43:1 / 1.62:1 in the scratch bundle copy; shipped bundle clean across 16 palette x mode combinations).
Honest boundaries unchanged: a live RED was not produced (the pre-fix bundle is no longer served), icon glyphs unmeasured (BOB-184), status badges need backend data (BOB-185), /jackett/* routes not scanned, manual QA (§11.4.185) owed.
