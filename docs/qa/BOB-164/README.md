# BOB-164 — WCAG AA colour-contrast failures on the live dashboard

**Revision:** 2
**Last modified:** 2026-08-25T18:20:00Z

Round 2. Round 1's fix was correct at the token layer and introduced a
regression at the *background* layer that neither oracle could see. This
document records the fix for that regression, the oracle change that
makes the whole class visible, and the corrections owed to round 1's
claims. Every number below was produced by a command in this directory
or by `npx ng test` in `frontend/`; none is carried over unmeasured.

---

## 1. What round 1 got wrong, precisely

Round 1 raised `--color-text-secondary` for legibility as TEXT. That
token is also painted as a BACKGROUND, and a change safe for one role is
a regression in the other.

| node | role of the token | pre-fix | after round 1 |
|---|---|---|---|
| `.status.unknown` (`color: #ccc`) | fill | 2.46:1 | **1.09:1** |
| `.type-badge.unknown` | fill | 1.93:1 | 1.13:1 |
| `.quality-badge.unknown` | fill | 1.93:1 | 1.13:1 |

**Framing correction (§11.4.6).** These were not passing nodes that the
fix broke. All three were *already below the floor* before round 1 —
`.status.unknown` at 2.46:1, both badges at 1.93:1. Round 1 made an
existing, unseen defect substantially worse; it did not create it. The
distinction matters because it locates the real failure in DISCOVERY,
not in the round-1 edit.

**Measurement correction.** The round-2 review reported the badges as
"white on that background, 3.95 → 1.74". The rendered foreground is not
white. Measured in a real headless Chromium against the shipped bundle
(`measure_rendered_cascade.py`), `.type-badge.unknown` resolves to
`rgb(169,183,198)` — `--color-text-primary`, inherited through
`html, body` in `styles.scss` — giving 1.93:1, not 3.95:1. The class the
review identified is real and its severity was understated.

## 2. Why both oracles were blind, and what changed

Neither blindness was an oversight; both were structural.

- **The arithmetic oracle** asserted text tokens against
  `SURFACES = [bgPrimary, bgSecondary, bgTertiary]`. A token used as a
  BACKGROUND was outside its pair set *by construction*.
- **The rendered-DOM oracle** scans a static dist with no backend, so the
  results table and the hooks list render EMPTY. The nodes simply were
  not on the page it measured.

Patching the four ratios would have fixed one instance. The class is
removed instead: **`frontend/src/app/models/style-contrast.spec.ts`**
reads the real stylesheets, extracts every declared
`(foreground, background)` pair — resolving inherited foregrounds through
the SCSS ancestor chain, same-file sibling rules, and the global
`html, body` default — and asserts each across all sixteen palette × mode
combinations. A token used as a fill is now inside the pair set by
construction, and a fill added tomorrow is picked up without editing the
spec.

Its honest boundary is stated in the file header and repeated here: it is
a static extractor, not a CSS cascade engine; it holds every pair to
4.5:1 rather than inferring the 3:1 large-text exemption from CSS; and
unresolvable values (`color-mix`, `rgba`, gradients) are SKIPPED, counted,
and surfaced rather than silently passed.

## 3. The fix

The root cause is a ROLE error, not four bad numbers: a literal (`#fff`,
`#ccc`, `#333`) cannot be correct against a fill that changes with the
palette. Round 1 had already established the remedy for one fill with
`onAccent`; round 2 generalises it.

| new token | fill it sits on |
|---|---|
| `onAccentHover` | `accentHover` |
| `onSuccess` / `onInfo` / `onWarning` / `onDanger` / `onPurple` | the semantic fills |
| `onMuted` | `textSecondary`-as-a-fill |
| `onBorder` | `border`-as-a-fill |

Every value is pure black or pure white — whichever contrasts more with
that palette's fill. That always clears 4.5:1: `contrast(#000,F)` and
`contrast(#fff,F)` are equal only where BOTH equal 4.58, so their maximum
never drops below 4.58 and **no fill colour had to move**.

Also added: **`contrastText`**, an AA-pinned, hue-preserving text variant
of `contrast`. The secondary brand gold was serving as the `code`
foreground in the Jackett tables and measured 2.47:1 on nord/light — the
same brand-as-text confusion round 1 fixed for `accent`, missed because
no scan renders those tables.

Static badge fills (`.movie`, `.tv`, …) previously *inherited*
`--color-text-primary`, which varies per palette; they now declare a
palette-independent literal chosen against their own static fill.

## 4. RED → GREEN, measured like-for-like

Round 1 reported RED `74 failed / 479 passed (553)` against GREEN
`652 passed (652)`. Those were produced by **different versions of the
spec**, so the pair did not measure one change — the matching `479
passed` is what made it look continuous. Re-measured here with the FINAL
oracle against the pre-fix sources (`git show HEAD:` for every non-spec
file, specs kept current):

```
RED    Test Files   1 failed | 31 passed (32)          [+ 1 more failing file]
       Tests      878 failed | 1736 passed (2614)
GREEN  Test Files  32 passed (32)
       Tests     2742 passed (2742)                     exit 0
```

The RED total breaks down as (counted from the per-test FAIL lines, not
from assertion text, which vitest prints twice):

| count | class |
|---|---|
| 192 | `accentText` / `dangerText` / `warningText` / `contrastText` absent at HEAD (4 tokens × 16 themes × 3 surfaces) |
| **25** | genuine sub-floor DECLARED TOKEN pairs — 23 `textSecondary`, 2 `textPrimary` |
| 4 | catalogue-level tests (runtime wiring, hue family, on-fill, no-hardcoded-foreground) |
| 657 | declared FOREGROUND-ON-FILL pairs (`style-contrast.spec.ts`, new this round) |

The **25** reproduces the reviewer's independent count exactly. My total
differs from the reviewer's 173 by 48 — precisely the `contrastText`
assertions this round adds (16 themes × 3 surfaces).

**The totals differ (2614 vs 2742) and that is expected**, not hidden: the
fix adds tokens, and new tokens create new test cases. A test count is
not a like-for-like axis; the failure classes above are.

## 5. Rendered-DOM verification of the nodes the scan cannot reach

`measure_rendered_cascade.py` injects the exact markup
`dashboard.component.html` emits, with the component's Angular
style-scoping attribute, and reads `getComputedStyle` — a real cascade,
not a static inference.

```
PRE-FIX  (shipped bundle)          9 of 11 measured nodes below their floor
POST-FIX (fresh build, same theme) 0 of 11 measured nodes below their floor
```

Full transcripts: `cascade_PREFIX_darcula_dark.txt`,
`cascade_POSTFIX_darcula_dark.txt`.

## 6. The scanner was blind to axe's `incomplete` channel

`_summarise()` read only `violations`. axe reports `incomplete` when its
own heuristics decline to decide — and a white-on-white node at 1.0:1,
the most flagrant failure a contrast oracle can face, lands there with
`messageKey: equalRatio`. Round 1 scored it as a PASS. That is a
§11.4.201(6) false-null living inside the contrast oracle itself.

The channel is now read, adjudicated from the same WCAG formula, and
counted in the exit code. axe abstaining does not mean the page is fine;
where the colours resolve, this script decides.

`--self-check` proves the oracle can SEE before any clean run is
believed (§11.4.107(10)):

```
  golden-bad  #golden-bad-equal    CAUGHT      (white on white, via `incomplete`)
  golden-bad  #golden-bad-plain    CAUGHT      (ordinary sub-floor, via `violations`)
  neg-control #negative-control    correctly silent
self-check: PASS
```

**Glyph nodes, decided honestly.** Post-fix the channel holds 40 nodes
across 16 themes for three icon-glyph controls (`.bridge-retry`,
`.theme-toggle`, `.caret`) where axe resolves NEITHER foreground NOR
background, so no oracle here can compute a ratio. Reporting them as
failures would be a §11.4.201(1) false-positive refusal; dropping them
silently would rebuild the false-null. They are a NAMED class,
`GLYPH_UNMEASURED`: printed every run, recorded in the JSON, excluded
from the exit code, and **fenced** — a glyph node outside the checked-in
allow-list still BLOCKS. Their SC 1.4.11 3:1 obligation remains genuinely
unproven and is tracked as **BOB-184**, not claimed clean.

Whole-catalogue result on a fresh build:

```
TOTAL colour-contrast violation nodes across 16 theme(s): 0
TOTAL blocking `incomplete` nodes (FAIL / UNDECIDABLE / GLYPH_FAIL): 0
TOTAL fenced GLYPH_UNMEASURED nodes (reported, not blocking): 40
```

## 7. Paired §1.1 mutations — every one caught

| # | mutation | result |
|---|---|---|
| R2A | `.status.unknown` reverted to `color: #ccc` | CAUGHT — 13 failed |
| R2B | `onMuted` → a mid-grey that clears nothing | CAUGHT — 3 failed |
| R2C | extractor reads only `background-color`, dropping the shorthand | CAUGHT — control needle fired: 7 failed |
| R2D | `non-text` exclusion pointed at `.status`, a real text node | CAUGHT — the fence rejects a class the CSS does not support |
| R2E | a `code` site reverted to `var(--color-contrast)` | CAUGHT — 5 failed |
| R2F | scanner ignores the `incomplete` channel (round-1 behaviour) | CAUGHT — `#golden-bad-equal` MISSED → self-check FAIL |
| R2G | `.caret` removed from the glyph fence | CAUGHT — exit 1, 2 blocking nodes |
| R2H | footer token `--color-accent-text` → `--color-accent-typo` | CAUGHT *after* strengthening — see §8 |

R2C is the load-bearing one: a blinded extractor is reported as BLIND, not
as clean. R2D closes the fence's real risk, which is not a stale entry but
a false one.

Round 1's own mutation set was re-run against the CHANGED oracle to
confirm it still bites (the round-1 review's `R1`–`R4` labels appear in no
artifact in this repository, so the set re-run is the one round 1
documented as `M1`–`M4`; stated rather than guessed):

| # | mutation | result |
|---|---|---|
| M1 | `accentText` → `#9d001e` (the fix undone) | CAUGHT — 1 failed |
| M2 | `accentText` → `#c4c4c4` (a grey that clears the ratio) | CAUGHT — hue guard, 1 failed |
| M3 | `onAccent` → `#000000` | CAUGHT — 1 failed |
| M4 | `textSecondary` → `#808080` | CAUGHT — **3** failed |

M4 now trips three assertions rather than one: reverting the token is
caught by the surface-pair oracle as before, and additionally by the new
fill-pair oracle, which is exactly the coverage that was missing.

Exit statuses were read directly from `$?` with no pipe in between
(§11.4.201(12)).

## 8. Corrections owed to round 1's claims

- **"NEW failures introduced by the fix: 0"** (round 1 §5) — **false as
  stated**. The fix drove `.status.unknown` from 2.46:1 to 1.09:1. The
  claim was true only *within the 30 nodes axe rendered*, and it was
  written without that scope. Scope now stated everywhere it appears.
- **"Previously-passing nodes now reported failing: 0"** (round 1 §7) —
  true only of the same 30-node scanned view, which excluded every
  data-driven node. Re-stated with its scope.
- **"TWO INDEPENDENT ORACLES (§11.4.245 structural independence)"** —
  **overstated for the DOM path.** `axe_contrast_scan.py` takes
  `fgColor` / `bgColor` / `shadowColor` FROM axe and re-does only the
  arithmetic; that is *arithmetic* independence, not *measurement*
  independence, and a wrong colour read by axe would be reproduced
  faithfully by the Python side. The vitest spec IS genuinely independent
  for declared pairs — it resolves colours from the palette source, never
  from a browser. The file header now says exactly this.
- **The `accentHover` sub-floor finding** (round 1, recorded unfixed in
  four palettes) is **fixed**, not filed: `onAccentHover` covers that fill
  and the generalised on-fill test asserts it in all 16 combinations. The
  round-1 note claiming otherwise is removed with it.
- **The footer regex** `var\(--color-accent[a-z-]*\)` accepted tokens that
  do not exist. Narrowing it to a closed alternation was *not enough* —
  the paired mutation still passed, because a valid sibling token
  satisfied an "at least one" check. The gate now asserts that **every**
  `--color-*` the footer references is a real key in `TOKEN_CSS_VAR`;
  R2H then fails as it should.

## 9. What this evidence does NOT cover

- **Legibility is not contrast.** No human has looked at these colours.
  §11.4.185 manual QA is unaffected and still owed.
- **The served bundle is still stale.** `download-proxy/src/ui/dist/`
  carries the pre-fix defect verbatim; `scripts/install.sh:133` checks
  only that the directory EXISTS, never that it is newer than its
  sources, and `dist/` is gitignored so the divergence never shows in a
  diff. §11.4.108 layer 2 is **not** closed. Tracked as **BOB-183**;
  deliberately not rebuilt here (a sibling stream owns that tree).
- **Data-driven nodes are arithmetic-only in a rendered DOM.** The badge
  and status nodes are asserted by `style-contrast.spec.ts` and were
  measured once by `measure_rendered_cascade.py`, but the standing scan
  still cannot see them. Tracked as **BOB-185**.
- **Icon glyphs are unmeasured**, per §6. Tracked as **BOB-184**.
- **Resting state only.** Hover states are now covered where a stylesheet
  declares them (`onAccentHover`), but focus, active and error states were
  not rendered.
- **`/jackett/*` was not scanned in a rendered DOM**; its tokens are
  covered by the arithmetic oracles only.

## 10. Reproducing

```bash
# both arithmetic oracles
cd frontend && npx ng test --watch=false          # 2742 passed, exit 0

# the rendered-DOM oracle, validated before use
.venv/bin/python docs/qa/BOB-164/axe_contrast_scan.py --self-check
cd frontend && npx ng build --output-path=/tmp/dist_r2 && cd ..
.venv/bin/python docs/qa/BOB-164/axe_contrast_scan.py \
    --dist /tmp/dist_r2/browser --all-palettes \
    --out docs/qa/BOB-164/scan_GREEN_round2_all_palettes.json   # exit 0

# the rendered cascade for nodes the scan cannot reach
.venv/bin/python docs/qa/BOB-164/measure_rendered_cascade.py --dist /tmp/dist_r2/browser
```

## Files

| File | What |
|---|---|
| `axe_contrast_scan.py` | rendered-DOM oracle; reads `violations` AND `incomplete`; `--self-check` validates it against golden-good/golden-bad fixtures |
| `measure_rendered_cascade.py` | measures the real cascade for badge/status nodes the scan cannot render |
| `cascade_PREFIX_darcula_dark.txt` / `cascade_POSTFIX_darcula_dark.txt` | those measurements, 9/11 failing → 0/11 |
| `scan_GREEN_round2_all_palettes.json` | post-fix, all 16 themes — 0 violations, 0 blocking incomplete |
| `scan_RED_shipped.json` / `scan_RED_all_palettes.json` | round-1 pre-fix scans, retained |
| `scan_GREEN_darcula.json` / `scan_GREEN_all_palettes.json` | round-1 post-fix scans, retained |
| `frontend/src/app/models/palette.contrast.spec.ts` | declared TOKEN-PAIR oracle (text on surfaces, on-fill tokens, hue guard) |
| `frontend/src/app/models/style-contrast.spec.ts` | declared FILL-PAIR oracle — closes the background-role blindness |
