/**
 * @fileoverview DEPTH a11y tests for the OPTIONS page that the existing a11y
 * suite leaves uncovered — the OPTIONS-specific color-contrast surfaces the
 * sibling did NOT measure, plus reduced-motion (WCAG 2.3.3 / 2.2.2). §11.4 /
 * §11.4.69 anti-bluff covenant.
 *
 * STATUS (2026-06-13): all 5 defects this file originally surfaced — the
 * Save-button gradient contrast (3.66:1), the two hard-coded literals invisible
 * in light theme (~1.40 / ~1.12:1), and the two missing reduced-motion blocks —
 * have been FIXED in src/{options,popup}/styles.css. The tests below now GUARD
 * those fixes (RED→GREEN proven); some inline "DEFECT/kept RED" wording is kept
 * as historical context for what each test originally caught.
 *
 * WHAT THE SIBLINGS ALREADY COVER (deliberately NOT repeated here):
 *   • focus-and-contrast.a11y.test.ts — the POPUP color-contrast matrix, the
 *     self-validated WCAG contrast analyzer, focus management for popup AND
 *     options, AND four OPTIONS token pairs (body text/bg, nav-item/elevated,
 *     field-input/elevated, field-help/bg).
 *   • options.a11y.test.ts / keyboard-nav.a11y.test.ts — roles, names, the
 *     tablist↔tabpanel ARIA pattern, live-regions, arrow-key navigation, roving
 *     tabindex.
 *
 * WHAT THIS FILE ADDS (the genuine OPTIONS-page GAPS):
 *
 *   1. OPTIONS COLOR CONTRAST (WCAG 2.1 SC 1.4.3) for the surfaces the sibling
 *      matrix never touched — computed from the REAL committed
 *      `src/options/styles.css`:
 *        • the PRIMARY SAVE BUTTON text (#fff) over its `--accent`→`--accent-2`
 *          gradient — checked at BOTH gradient endpoints (the lighter half is
 *          the worst case a single-token check would miss);
 *        • the HARD-CODED literal colors the token-only sibling cannot see —
 *          `.field > label` (#d0d0e0) and `.nav-item:hover` (#e0e0e0) — which
 *          DO NOT re-resolve per theme and so collapse in LIGHT mode.
 *      I implement the WCAG relative-luminance + contrast-ratio math here (sRGB
 *      linearization; ratio = (L1+0.05)/(L2+0.05)) with a tiny self-validation
 *      (black/white = 21, identical = 1, a worked mid-grey example) so this
 *      analyzer provably cannot bluff. Where the REAL CSS is below AA 4.5:1 the
 *      test is KEPT RED and reports the computed ratio as a genuine defect — the
 *      threshold is NOT weakened and the CSS is NOT edited.
 *
 *   2. PREFERS-REDUCED-MOTION (WCAG 2.1 SC 2.3.3 Animation from Interactions,
 *      SC 2.2.2 Pause/Stop/Hide). The options CSS ships non-trivial motion (a
 *      `@keyframes fadeIn` panel animation + several `transition`s). WCAG 2.3.3
 *      requires motion-animation triggered by interaction to be disable-able. A
 *      `@media (prefers-reduced-motion: reduce)` block that neutralises that
 *      motion is the standard mechanism. The committed CSS has NO such block —
 *      that is a real a11y gap, surfaced RED with evidence. The popup CSS (which
 *      ships transitions but NO @keyframes) is checked the same way.
 *
 * ANTI-BLUFF (§11.4 / §11.4.69 / §11.4.107): every assertion inspects a
 * user-observable property — a numerically computed contrast ratio against the
 * REAL tokens/literals that ship, or the literal presence/absence of a real CSS
 * @media rule in the committed stylesheet. No absolute wall-clock threshold is
 * used (§11.4.50). The motion-gap tests are written so that ADDING the missing
 * `@media (prefers-reduced-motion: reduce)` block (and the contrast tests so
 * that fixing the offending color) flips them GREEN automatically — they are
 * honest guards, not permanent failures. This suite NEVER edits production CSS.
 *
 * Sources verified 2026-06-13:
 *   WCAG 2.1 SC 1.4.3 Contrast (Minimum) — https://www.w3.org/TR/WCAG21/#contrast-minimum
 *   WCAG 2.1 SC 2.3.3 Animation from Interactions — https://www.w3.org/TR/WCAG21/#animation-from-interactions
 *   WCAG 2.1 SC 2.2.2 Pause, Stop, Hide — https://www.w3.org/TR/WCAG21/#pause-stop-hide
 *   Relative luminance / contrast ratio defs — https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const OPTIONS_CSS_PATH = "src/options/styles.css";
const POPUP_CSS_PATH = "src/popup/styles.css";

// ─────────────────────────────────────────────────────────────────────────────
// WCAG contrast math (SC 1.4.3) — relative luminance + contrast ratio.
//   L = 0.2126*R + 0.7152*G + 0.0722*B with sRGB linearization.
//   ratio = (L_lighter + 0.05) / (L_darker + 0.05).
// Re-implemented locally (NOT imported from the sibling) so this file is a
// self-contained, independently self-validated analyzer per §11.4.107(10).
// ─────────────────────────────────────────────────────────────────────────────

/** Linearize one 0–255 sRGB channel to its WCAG luminance component. */
function linearizeChannel(value8bit: number): number {
  const c = value8bit / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/** Parse a `#rrggbb` (or `#rgb`) hex string into [r,g,b] 0–255. */
function hexToRgb(hex: string): [number, number, number] {
  let h = hex.trim().replace(/^#/, "");
  if (h.length === 3) {
    h = h
      .split("")
      .map((ch) => ch + ch)
      .join("");
  }
  if (!/^[0-9a-fA-F]{6}$/.test(h)) {
    throw new Error(`not a 6-digit hex color: "${hex}"`);
  }
  return [
    Number.parseInt(h.slice(0, 2), 16),
    Number.parseInt(h.slice(2, 4), 16),
    Number.parseInt(h.slice(4, 6), 16),
  ];
}

/** WCAG relative luminance of a hex color. */
function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return (
    0.2126 * linearizeChannel(r) +
    0.7152 * linearizeChannel(g) +
    0.0722 * linearizeChannel(b)
  );
}

/** WCAG contrast ratio between two hex colors (1.0 … 21.0). */
function contrastRatio(fg: string, bg: string): number {
  const l1 = relativeLuminance(fg);
  const l2 = relativeLuminance(bg);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

const AA_NORMAL = 4.5; // WCAG SC 1.4.3 — normal text (every flagged usage is normal-weight ≤ 14px text)

/** Read a CSS file off disk (the stylesheet that actually ships). */
function readCss(path: string): string {
  return readFileSync(path, "utf8");
}

/**
 * Extract the `--token: #value;` declarations from the CSS block whose selector
 * exactly matches `selectorLiteral` (e.g. `:root[data-theme="dark"]`). Returns
 * token-name (no leading `--`) → hex value. Only literal hex values are captured
 * (gradients/rgba are handled explicitly by their own tests below).
 */
function extractTokenBlock(css: string, selectorLiteral: string): Record<string, string> {
  const idx = css.indexOf(selectorLiteral);
  if (idx === -1) throw new Error(`selector "${selectorLiteral}" not found in CSS`);
  const open = css.indexOf("{", idx);
  const close = css.indexOf("}", open);
  if (open === -1 || close === -1) {
    throw new Error(`malformed block for "${selectorLiteral}"`);
  }
  const body = css.slice(open + 1, close);
  const tokens: Record<string, string> = {};
  const re = /--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(body)) !== null) {
    const name = m[1];
    const value = m[2];
    if (name && value) tokens[name] = value;
  }
  return tokens;
}

function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

// ─────────────────────────────────────────────────────────────────────────────
// 0. Self-validation of THIS analyzer (so it cannot bluff). WCAG publishes the
//    reference extremes; if the math drifts these FAIL before any real pair is
//    judged. This intentionally re-pins the analyzer for THIS file rather than
//    trusting the sibling's copy — the analyzer that judges these pairs is the
//    one that must be proven honest.
// ─────────────────────────────────────────────────────────────────────────────

describe("options-contrast analyzer self-validation (golden-good / golden-bad)", () => {
  it("black on white computes WCAG's reference 21:1 (catches: broken luminance math)", () => {
    // 21:1 is WCAG's exact maximum. A drift here means the luminance/ratio math
    // is wrong and every pair verdict below is untrustworthy.
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 1);
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 1); // order-independent
  });

  it("identical colors compute 1:1 (catches: a tautology that would rubber-stamp invisible text)", () => {
    // GOLDEN-BAD: fg==bg is invisible. If the analyzer scored this high it would
    // pass unreadable text — pin it to exactly 1.0, below AA.
    expect(contrastRatio("#808080", "#808080")).toBeCloseTo(1, 5);
    expect(contrastRatio("#808080", "#808080")).toBeLessThan(AA_NORMAL);
  });

  it("a known mid-grey worked example matches its published ratio (catches: wrong sRGB curve)", () => {
    // #767676 on #ffffff ≈ 4.54:1 — the canonical lowest grey-on-white that still
    // passes AA. A wrong sRGB linearization curve drifts this number.
    expect(contrastRatio("#767676", "#ffffff")).toBeCloseTo(4.54, 1);
  });

  it("hexToRgb rejects a non-hex value (catches: silently scoring garbage as a color)", () => {
    expect(() => hexToRgb("linear-gradient(135deg, ...)")).toThrow();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 1a. OPTIONS — PRIMARY SAVE BUTTON text over its GRADIENT background.
//     `.btn-primary` ships `color:#fff` over
//     `linear-gradient(135deg, var(--accent), var(--accent-2))`. A token-only
//     contrast check (like the sibling matrix) cannot evaluate a gradient. WCAG
//     applies to text over EVERY part of the gradient, so the correct test is
//     the WORST endpoint — here the lighter `--accent`. The `--accent`/`--accent-2`
//     tokens are theme-invariant (defined only in `:root`), so one check covers
//     both themes.
// ─────────────────────────────────────────────────────────────────────────────

describe("options primary-button text contrast over its gradient (WCAG 1.4.3)", () => {
  const css = readCss(OPTIONS_CSS_PATH);
  const root = extractTokenBlock(css, ":root {");

  // Extract the ACTUAL color stops of the `.btn-primary` background gradient,
  // resolving any `var(--token)` stop against :root. The button text is #fff and
  // WCAG requires it to pass over EVERY part of the gradient, so we check both
  // resolved endpoints. The button uses a button-LOCAL darker indigo start
  // (#5a6fce, 4.57:1) instead of the global --accent (#667eea, only 3.66:1),
  // because --accent is ALSO `.nav-item.active` text on a dark sidebar where
  // darkening the token would REDUCE that contrast — so the fix is button-local.
  function btnGradientColors(): string[] {
    const m = css.match(
      /\.btn-primary\s*\{[\s\S]*?background:\s*linear-gradient\(([^;]*)\)/,
    );
    if (!m || !m[1]) throw new Error(".btn-primary linear-gradient not found");
    const decl = m[1];
    const colors: string[] = [];
    for (const h of decl.match(/#[0-9a-fA-F]{3,6}/g) ?? []) colors.push(h);
    for (const v of decl.match(/var\(--([a-z0-9-]+)\)/g) ?? []) {
      const name = v.replace(/^var\(--/, "").replace(/\)$/, "");
      const resolved = root[name];
      if (resolved) colors.push(resolved);
    }
    return colors;
  }

  it("sanity: the button gradient declares ≥2 resolvable color stops (catches: broken extraction)", () => {
    const colors = btnGradientColors();
    expect(colors.length).toBeGreaterThanOrEqual(2);
    for (const c of colors) expect(c).toMatch(/^#[0-9a-fA-F]{3,6}$/);
  });

  // FIXED (was a real defect: #fff on --accent #667eea = 3.66:1). This now guards
  // the fix — #fff must clear AA over EVERY stop of the actual button gradient.
  it("#fff button text meets AA 4.5:1 over EVERY stop of the .btn-primary gradient (catches: a too-light gradient endpoint regressing)", () => {
    for (const c of btnGradientColors()) {
      const ratio = contrastRatio("#ffffff", c);
      expect(
        ratio,
        `button text #ffffff on gradient stop ${c} = ${ratio.toFixed(2)}:1 (needs ≥ 4.5 for 14px Save-button text)`,
      ).toBeGreaterThanOrEqual(AA_NORMAL);
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 1b. OPTIONS — HARD-CODED literal text colors (NOT tokens). The sibling matrix
//     only checks `var(--token)` pairs and so is BLIND to the literal `#rrggbb`
//     colors the options CSS hard-codes. Because these literals do NOT re-resolve
//     per theme (unlike the tokens, which flip in `:root[data-theme="light"]`),
//     they keep their dark-theme value over the LIGHT background and collapse.
//       `.field > label`   color: #d0d0e0   (field labels — every settings field)
//       `.nav-item:hover`  color: #e0e0e0   (sidebar tab hover state)
//     Both are computed against BOTH the dark `--bg`/`--border-soft` (where they
//     pass) and the light ones (where they fail) so the asymmetry is explicit.
// ─────────────────────────────────────────────────────────────────────────────

describe("options field-label + nav-hover use theme-aware tokens meeting AA in BOTH themes (WCAG 1.4.3)", () => {
  const css = readCss(OPTIONS_CSS_PATH);
  const dark = extractTokenBlock(css, ':root[data-theme="dark"]');
  const light = extractTokenBlock(css, ':root[data-theme="light"]');

  // These two foreground colors were hard-coded dark-theme literals (#d0d0e0 /
  // #e0e0e0) that never re-resolved for light mode → ~1.40:1 / ~1.12:1 invisible
  // in light theme (a real defect). They are now theme-aware tokens. This block
  // is the §11.4.120-reconciled gate: it asserts the NEW mechanism (a var(--token)
  // color) AND that the resolved token clears AA in BOTH themes — a regression
  // back to a non-theme-aware literal, or a token drifting below AA, FAILs.

  it("sanity: .field > label and .nav-item:hover use a var(--token) color, NOT a hard-coded literal (catches: a regression to a non-theme-aware literal)", () => {
    expect(css).toMatch(/\.field\s*>\s*label\s*\{[\s\S]*?color:\s*var\(--text\)/);
    expect(css).toMatch(/\.nav-item:hover\s*\{[\s\S]*?color:\s*var\(--text-strong\)/);
    // And the old invisible-in-light literals are gone.
    expect(css).not.toMatch(/\.field\s*>\s*label\s*\{[\s\S]*?color:\s*#d0d0e0/);
    expect(css).not.toMatch(/\.nav-item:hover\s*\{[\s\S]*?color:\s*#e0e0e0/);
  });

  it("sanity: both theme token sets parsed from the real CSS (catches: broken token extraction)", () => {
    for (const [name, set] of [
      ["dark", dark],
      ["light", light],
    ] as const) {
      expect(mustExist(set.text, `--text (${name})`)).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(mustExist(set["text-strong"], `--text-strong (${name})`)).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(mustExist(set.bg, `--bg (${name})`)).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(mustExist(set["border-soft"], `--border-soft (${name})`)).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });

  for (const theme of ["dark", "light"] as const) {
    it(`field-label var(--text) on --bg meets AA 4.5:1 in ${theme} theme`, () => {
      const set = theme === "dark" ? dark : light;
      const fg = mustExist(set.text, `--text (${theme})`);
      const bg = mustExist(set.bg, `--bg (${theme})`);
      const ratio = contrastRatio(fg, bg);
      expect(
        ratio,
        `field-label --text ${fg} on --bg ${bg} (${theme}) = ${ratio.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(AA_NORMAL);
    });

    it(`nav-item:hover var(--text-strong) on --border-soft meets AA 4.5:1 in ${theme} theme`, () => {
      const set = theme === "dark" ? dark : light;
      const fg = mustExist(set["text-strong"], `--text-strong (${theme})`);
      const bs = mustExist(set["border-soft"], `--border-soft (${theme})`);
      const ratio = contrastRatio(fg, bs);
      expect(
        ratio,
        `nav-hover --text-strong ${fg} on --border-soft ${bs} (${theme}) = ${ratio.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(AA_NORMAL);
    });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. PREFERS-REDUCED-MOTION (WCAG 2.1 SC 2.3.3 / 2.2.2).
//    A user who sets the OS "reduce motion" preference must be able to suppress
//    non-essential motion. The standard CSS mechanism is a
//    `@media (prefers-reduced-motion: reduce) { ... }` block that zeroes the
//    relevant `animation`/`transition`s. These tests first PROVE the stylesheet
//    actually ships non-trivial motion (so the requirement genuinely applies —
//    not a vacuous pass), then assert a reduced-motion block exists. The options
//    CSS ships a @keyframes panel animation + transitions but NO such block → a
//    real gap surfaced RED. Adding the block flips these GREEN.
// ─────────────────────────────────────────────────────────────────────────────

/** Does this CSS declare a `@media (prefers-reduced-motion: reduce)` block? */
function hasReducedMotionBlock(css: string): boolean {
  // Tolerant of whitespace and an optional `screen and` qualifier.
  return /@media[^{]*prefers-reduced-motion\s*:\s*reduce/.test(css);
}

/** Count the `@keyframes` definitions (the strongest 2.3.3 motion signal). */
function countKeyframes(css: string): number {
  return (css.match(/@keyframes\s+[A-Za-z_-]/g) ?? []).length;
}

/** Count `animation:` shorthand declarations that bind a keyframes animation. */
function countAnimationDecls(css: string): number {
  // Match `animation:` but not `animation-name`/`animation-duration` sub-props,
  // and not the `@keyframes` keyword itself.
  return (css.match(/[^-]animation\s*:/g) ?? []).length;
}

/** Count `transition:` declarations (non-zero motion on state change). */
function countTransitionDecls(css: string): number {
  return (css.match(/[^-]transition\s*:/g) ?? []).length;
}

describe("options prefers-reduced-motion (WCAG 2.3.3 / 2.2.2)", () => {
  const css = readCss(OPTIONS_CSS_PATH);

  it("sanity: the options CSS really ships non-trivial motion (so the requirement is NOT vacuous)", () => {
    // SC 2.3.3 only applies if there IS interaction-triggered motion to gate.
    // The committed options CSS has a `@keyframes fadeIn` panel-reveal animation
    // bound via `animation: fadeIn ...` on `.section.active`, plus transitions.
    // Asserting these makes the reduced-motion test below MEANINGFUL: it is a
    // real obligation, not a "nothing to gate" free pass.
    expect(css).toMatch(/@keyframes\s+fadeIn/);
    expect(css).toMatch(/animation:\s*fadeIn/);
    expect(countKeyframes(css), "options @keyframes count").toBeGreaterThanOrEqual(1);
    expect(countAnimationDecls(css), "options animation: declarations").toBeGreaterThanOrEqual(1);
    expect(countTransitionDecls(css), "options transition: declarations").toBeGreaterThanOrEqual(1);
  });

  // FIXED (was a real gap): the options CSS animates panels (@keyframes fadeIn)
  // + transitions but shipped NO reduced-motion escape hatch. The block was added
  // (2026-06-13); this test now GUARDS its presence (regresses if it is removed).
  it("declares a @media (prefers-reduced-motion: reduce) block to disable that motion (WCAG 2.3.3)", () => {
    // Because the options page animates the panel reveal (`@keyframes fadeIn`
    // triggered every time a settings tab is activated — an interaction) and
    // transitions nav/field/button state, a user with "reduce motion" set has no
    // way to suppress it. WCAG SC 2.3.3 requires that mechanism. The committed
    // stylesheet has no `@media (prefers-reduced-motion: reduce)` block → gap.
    // Adding that block (zeroing animation/transition for the reduce query) flips
    // this GREEN. We do NOT edit production CSS here — this is the finding.
    expect(
      hasReducedMotionBlock(css),
      "src/options/styles.css ships @keyframes fadeIn (panel reveal) + transitions but NO `@media (prefers-reduced-motion: reduce)` block to disable them — a WCAG 2.3.3/2.2.2 gap for motion-sensitive users",
    ).toBe(true);
  });
});

describe("popup prefers-reduced-motion (WCAG 2.3.3 / 2.2.2)", () => {
  const css = readCss(POPUP_CSS_PATH);
  const keyframes = countKeyframes(css);
  const transitions = countTransitionDecls(css);

  it("classifies the popup's motion honestly (no @keyframes; only transitions ship)", () => {
    // Non-vacuous classification: the popup CSS has NO @keyframes (no looping /
    // attention-grabbing animation — the most severe 2.3.3 class) but DOES ship
    // state-change `transition`s. Asserting this fact prevents a silent vacuous
    // pass and documents exactly what motion the popup carries.
    expect(keyframes, "popup @keyframes count").toBe(0);
    expect(transitions, "popup transition: declarations").toBeGreaterThanOrEqual(1);
  });

  // FIXED (was a milder gap than options): the popup has only short state
  // transitions (no keyframes animation) but shipped no reduced-motion escape.
  // The block was added (2026-06-13); this test now GUARDS its presence.
  it("declares a @media (prefers-reduced-motion: reduce) block for its transitions (WCAG 2.3.3)", () => {
    expect(
      hasReducedMotionBlock(css),
      "src/popup/styles.css ships state-change transitions but NO `@media (prefers-reduced-motion: reduce)` block to disable them — a (milder, transition-only) WCAG 2.3.3 gap",
    ).toBe(true);
  });
});
