/**
 * @fileoverview DEPTH a11y tests for the two areas the existing a11y suite
 * leaves PENDING — focus management and color contrast — for the REAL committed
 * popup + options UI. §11.4 / §11.4.69 anti-bluff covenant.
 *
 * The sibling suites already cover roles, accessible names, the tablist↔tabpanel
 * relationship, live-regions (popup.a11y / options.a11y) and arrow-key tablist
 * navigation + roving tabindex (keyboard-nav.a11y). This file deliberately does
 * NOT re-prove any of those. It targets the two remaining WCAG areas:
 *
 *   A. FOCUS MANAGEMENT (WCAG 2.1 — SC 2.4.3 Focus Order, SC 2.4.7 Focus
 *      Visible, SC 2.1.2 No Keyboard Trap)
 *        • a focus-visible INDICATOR is actually declared in the shipped CSS
 *        • the first reachable element under natural Tab order is sensible /
 *          really focusable (document.activeElement after .focus())
 *        • focus order is logical — no positive tabindex, every interactive
 *          control reachable, none unexpectedly removed from the Tab sequence
 *        • the options tablist restores focus to the newly-selected tab when the
 *          user roves with the keyboard (the roving-tabindex focus RESTORE)
 *
 *   B. COLOR CONTRAST (WCAG 2.1 — SC 1.4.3 Contrast (Minimum)). The threshold is
 *      WCAG's: normal text ≥ 4.5:1, large text ≥ 3:1
 *      (https://www.w3.org/TR/WCAG21/#contrast-minimum, verified 2026-06-13).
 *      We parse the REAL color tokens out of the committed CSS, implement the
 *      WCAG relative-luminance + contrast-ratio formula, and compute the ACTUAL
 *      numeric ratio for each declared foreground/background TEXT pair, in BOTH
 *      the light and dark theme token sets.
 *
 * ANTI-BLUFF: every assertion inspects a user-observable property (a real CSS
 * rule that ships, document.activeElement, a tabindex value, a numerically
 * computed contrast ratio against the real tokens). The contrast helper is
 * self-checked against WCAG's own published reference ratios (black/white = 21,
 * identical = 1) so the analyzer itself provably cannot bluff. Where the REAL
 * CSS fails WCAG AA, the test is KEPT RED and reports the computed ratio as a
 * genuine defect — the threshold is NOT weakened to paint green.
 */
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OPTIONS_HTML_PATH, POPUP_HTML_PATH } from "./load-html";

const POPUP_CSS_PATH = "src/popup/styles.css";
const OPTIONS_CSS_PATH = "src/options/styles.css";

// ─────────────────────────────────────────────────────────────────────────────
// WCAG contrast math (SC 1.4.3) — relative luminance + contrast ratio.
//   https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
//   https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio
// L = 0.2126*R + 0.7152*G + 0.0722*B with sRGB linearization.
// ratio = (L_lighter + 0.05) / (L_darker + 0.05).
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

const AA_NORMAL = 4.5; // WCAG SC 1.4.3 — normal text (all flagged usages are normal text)

// ─────────────────────────────────────────────────────────────────────────────
// CSS token extraction — read the REAL committed token values, not a copy.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Extract the `--token: #value;` declarations from a single CSS block whose
 * selector exactly matches `selectorLiteral` (e.g. `:root[data-theme="light"]`).
 * Returns a map of token-name (without leading `--`) → hex value. Only hex
 * values are captured (gradients/rgba are out of scope for a precise contrast
 * computation and are documented as such in the tests below).
 */
function extractTokenBlock(css: string, selectorLiteral: string): Record<string, string> {
  // Find the selector, then the first `{ ... }` after it.
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

/** Read a CSS file off disk (the file that actually ships). */
function readCss(path: string): string {
  return readFileSync(path, "utf8");
}

/** Parse a real entrypoint <body> into the ambient jsdom document. */
function loadBody(htmlPath: string): void {
  const html = readFileSync(htmlPath, "utf8");
  const bodyMatch = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html);
  document.body.innerHTML = bodyMatch ? (bodyMatch[1] ?? "") : html;
}

function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

/** Dispatch a real keydown for `key` on `el`. */
function pressKey(el: Element, key: string): KeyboardEvent {
  const ev = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  el.dispatchEvent(ev);
  return ev;
}

// ─────────────────────────────────────────────────────────────────────────────
// 0. Self-validation of the contrast analyzer (so the analyzer can't bluff).
//    WCAG publishes the reference extremes; if our math drifts, these FAIL.
// ─────────────────────────────────────────────────────────────────────────────

describe("contrast analyzer self-validation (golden-good / golden-bad)", () => {
  it("black on white computes WCAG's reference 21:1 (catches: broken luminance math)", () => {
    // The maximum possible WCAG contrast ratio is exactly 21:1.
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 1);
    // Order-independent: (lighter+0.05)/(darker+0.05) is symmetric.
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 1);
  });

  it("identical colors compute 1:1 (catches: a tautology that would pass anything)", () => {
    // GOLDEN-BAD: a fg==bg pair is invisible. If the analyzer returned a high
    // number here it would rubber-stamp unreadable text — this pins it to 1.0.
    expect(contrastRatio("#777777", "#777777")).toBeCloseTo(1, 5);
    expect(contrastRatio("#777777", "#777777")).toBeLessThan(AA_NORMAL);
  });

  it("a known mid-grey pair matches an independently computed ratio (catches: wrong sRGB curve)", () => {
    // #767676 on #ffffff is a canonical WCAG worked example ≈ 4.54:1 (the lowest
    // grey on white that still passes AA). If our sRGB linearization is wrong the
    // number drifts away from this published value.
    expect(contrastRatio("#767676", "#ffffff")).toBeCloseTo(4.54, 1);
  });

  it("hexToRgb rejects a non-hex token (catches: silently scoring garbage as a color)", () => {
    expect(() => hexToRgb("rgba(0,0,0,0.5)")).toThrow();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// A. FOCUS MANAGEMENT — popup
// ─────────────────────────────────────────────────────────────────────────────

describe("popup focus management (WCAG 2.4.3 / 2.4.7 / 2.1.2)", () => {
  const css = readCss(POPUP_CSS_PATH);

  beforeEach(() => {
    document.body.innerHTML = "";
    loadBody(POPUP_HTML_PATH);
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("the shipped CSS declares a :focus-visible indicator for buttons + links (catches: invisible focus)", () => {
    // SC 2.4.7 Focus Visible: a keyboard user must SEE where focus is. The popup
    // CSS must carry a real `:focus-visible { outline … }` rule. If that rule is
    // deleted, keyboard focus becomes invisible and this assertion fails.
    expect(css).toMatch(/:focus-visible/);
    // It must set a non-`none` outline (an `outline: none` with nothing else is
    // the classic focus-killer this guards against).
    const focusRules = css.match(/:focus-visible[\s\S]*?\{[\s\S]*?\}/g) ?? [];
    expect(focusRules.length).toBeGreaterThan(0);
    const declaresOutline = focusRules.some((rule) => /outline\s*:\s*[^;]*solid/.test(rule));
    expect(declaresOutline, "a :focus-visible rule must set a visible outline").toBe(true);
  });

  it("the first interactive control is genuinely focusable (catches: a non-focusable lead control)", () => {
    // SC 2.4.3 Focus Order: opening the popup, the user's first Tab should land
    // on a real, focusable control. The first non-disabled interactive control in
    // DOM order is Refresh (Send-All ships disabled). Prove it accepts focus —
    // document.activeElement becomes it after .focus(). A <div>-as-button or a
    // control hidden from the tab order would NOT become activeElement here.
    const refresh = mustExist(document.getElementById("btn-refresh"), "btn-refresh");
    refresh.focus();
    expect(document.activeElement).toBe(refresh);
  });

  it("focus order follows DOM order with NO positive tabindex (catches: tabindex>0 reordering focus)", () => {
    // SC 2.4.3: a positive tabindex jumps the control to the front of the Tab
    // sequence, scrambling logical order. None may exist.
    const controls = Array.from(
      document.querySelectorAll<HTMLElement>("button, a[href], input, select, [tabindex]"),
    );
    const positive = controls
      .filter((el) => {
        const raw = el.getAttribute("tabindex");
        if (raw === null) return false;
        const n = Number.parseInt(raw, 10);
        return Number.isFinite(n) && n > 0;
      })
      .map((el) => `${el.tagName}#${el.id || "(no-id)"}[tabindex=${el.getAttribute("tabindex")}]`);
    expect(positive, "popup controls with a positive tabindex").toEqual([]);
  });

  it("no popup control is removed from the Tab order with tabindex=-1 at rest (catches: unreachable control)", () => {
    // SC 2.1.1 / 2.4.3: every shipped interactive control should be keyboard
    // reachable. The popup ships no roving widget, so NONE of its buttons/links
    // should carry tabindex="-1". (Disabled Send-All is correctly skipped by the
    // platform without needing tabindex=-1.) A control roved out here would be a
    // keyboard user's dead end.
    const rovedOut = Array.from(
      document.querySelectorAll<HTMLElement>("button, a[href]"),
    )
      .filter((el) => el.getAttribute("tabindex") === "-1")
      .map((el) => `${el.tagName}#${el.id || "(no-id)"}`);
    expect(rovedOut, "popup controls removed from Tab order").toEqual([]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// A. FOCUS MANAGEMENT — options (focus-visible + roving-tabindex focus RESTORE)
// ─────────────────────────────────────────────────────────────────────────────

describe("options focus management (WCAG 2.4.3 / 2.4.7)", () => {
  const css = readCss(OPTIONS_CSS_PATH);

  it("the shipped CSS declares :focus-visible for nav tabs AND :focus for fields (catches: invisible focus)", () => {
    // SC 2.4.7: tabs use `:focus-visible { outline … }`; text fields use a
    // `:focus { box-shadow … }` ring. Both must be present in the committed CSS.
    expect(css).toMatch(/\.nav-item:focus-visible/);
    const navFocus = css.match(/\.nav-item:focus-visible[\s\S]*?\{[\s\S]*?\}/g) ?? [];
    expect(navFocus.some((r) => /outline\s*:\s*[^;]*solid/.test(r))).toBe(true);
    // Fields get a visible focus ring (box-shadow) even though they reset the
    // default outline — that combination is the intentional, accessible pattern.
    const fieldFocus = css.match(/\.field\s+input:focus[\s\S]*?\{[\s\S]*?\}/g) ?? [];
    expect(fieldFocus.length).toBeGreaterThan(0);
    expect(fieldFocus.some((r) => /box-shadow\s*:/.test(r))).toBe(true);
  });

  describe("roving-tabindex focus restore (driving the REAL options logic)", () => {
    beforeEach(async () => {
      delete (globalThis as { chrome?: unknown }).chrome;
      document.body.innerHTML = "";
      vi.resetModules();
      loadBody(OPTIONS_HTML_PATH);
      const { initOptions } = await import("../../src/options/options");
      await initOptions(document);
    });

    afterEach(() => {
      document.body.innerHTML = "";
    });

    it("ArrowRight RESTORES focus + the Tab sequence to the newly-selected tab (catches: focus left behind)", () => {
      // SC 2.4.3 + WAI-ARIA roving tabindex: after keyboard navigation, the newly
      // active tab is the single tabbable one AND has DOM focus, while the prior
      // tab is roved OUT. If the handler updated aria-selected but forgot to move
      // focus/tabindex, a keyboard user would Tab away from a stale element — this
      // catches that desync.
      const server = mustExist(
        document.querySelector<HTMLElement>('[role="tab"][data-tab="server"]'),
        "server tab",
      );
      const download = mustExist(
        document.querySelector<HTMLElement>('[role="tab"][data-tab="download"]'),
        "download tab",
      );
      server.focus();
      expect(document.activeElement).toBe(server);

      pressKey(server, "ArrowRight");

      // Focus restored onto the newly-selected tab.
      expect(document.activeElement).toBe(download);
      // Roving tabindex: exactly the active tab is in the Tab sequence.
      expect(download.tabIndex).toBe(0);
      expect(server.tabIndex).toBe(-1);
    });

    it("after End→Home the FIRST tab regains focus and is the only tabbable one (catches: orphaned focus)", () => {
      const first = mustExist(
        document.querySelector<HTMLElement>('[role="tab"][data-tab="server"]'),
        "server tab",
      );
      first.focus();
      pressKey(first, "End"); // jump to last (security)
      const last = mustExist(
        document.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]'),
        "selected tab",
      );
      expect(last.getAttribute("data-tab")).toBe("security");
      expect(document.activeElement).toBe(last);

      pressKey(last, "Home"); // jump back to first
      // Focus restored to the first tab, and it is the single tabbable tab.
      expect((document.activeElement as HTMLElement).getAttribute("data-tab")).toBe("server");
      const tabbable = Array.from(
        document.querySelectorAll<HTMLElement>('[role="tab"][data-tab]'),
      ).filter((t) => {
        const raw = t.getAttribute("tabindex");
        return raw === null || Number.parseInt(raw, 10) >= 0;
      });
      expect(tabbable.length).toBe(1);
      expect(tabbable[0]?.getAttribute("data-tab")).toBe("server");
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// B. COLOR CONTRAST — WCAG SC 1.4.3, computed against the REAL CSS tokens.
//    Both light and dark token sets are checked.
// ─────────────────────────────────────────────────────────────────────────────

interface TextPair {
  /** Human description used in the failure message. */
  what: string;
  /** Token name (no `--`) for the foreground text color. */
  fg: string;
  /** Token name (no `--`) for the background behind that text. */
  bg: string;
  /** WCAG threshold for this pair: normal text 4.5, large text 3.0. */
  min: number;
}

/** Resolve a TextPair's tokens to a concrete ratio against a token map. */
function pairRatio(tokens: Record<string, string>, p: TextPair): number {
  const fg = mustExist(tokens[p.fg], `--${p.fg}`);
  const bg = mustExist(tokens[p.bg], `--${p.bg}`);
  return contrastRatio(fg, bg);
}

describe("popup color contrast (WCAG 1.4.3)", () => {
  const css = readCss(POPUP_CSS_PATH);
  const dark = extractTokenBlock(css, ':root[data-theme="dark"]');
  const light = extractTokenBlock(css, ':root[data-theme="light"]');

  // Foreground/background TEXT pairs that the real popup renders. Each maps a
  // CSS rule in styles.css to its token pair:
  //   body text         → color:var(--text)        on background:var(--bg)
  //   .torrent-meta     → color:var(--text-muted)  on the row/bg
  //   .btn-secondary    → color:var(--text)        on background:var(--secondary)
  //   .options-link     → color:var(--link)        on var(--bg-elevated) (footer)
  // `.section-title` / `.torrent-hash` use --text-faint (font-size 11px = normal
  // text → AA 4.5 applies; NOT large-text).
  const PASSING: TextPair[] = [
    { what: "body text on background", fg: "text", bg: "bg", min: AA_NORMAL },
    { what: "muted meta text on background", fg: "text-muted", bg: "bg", min: AA_NORMAL },
    { what: "secondary-button text on secondary bg", fg: "text", bg: "secondary", min: AA_NORMAL },
    { what: "options link on elevated (footer) bg", fg: "link", bg: "bg-elevated", min: AA_NORMAL },
  ];

  it("sanity: both theme token sets were parsed from the real CSS (catches: broken token extraction)", () => {
    // If extraction silently returned {} the contrast tests below would vacuously
    // pass — this guards the parser itself.
    expect(Object.keys(dark).length).toBeGreaterThan(5);
    expect(Object.keys(light).length).toBeGreaterThan(5);
    expect(dark.bg).toBeTruthy();
    expect(light.bg).toBeTruthy();
  });

  for (const p of PASSING) {
    it(`DARK: ${p.what} meets AA ${p.min}:1 (catches: a token darkened below the floor)`, () => {
      const ratio = pairRatio(dark, p);
      expect(ratio, `${p.what} (dark) = ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(p.min);
    });
    it(`LIGHT: ${p.what} meets AA ${p.min}:1 (catches: a token lightened below the floor)`, () => {
      const ratio = pairRatio(light, p);
      expect(ratio, `${p.what} (light) = ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(p.min);
    });
  }
});

describe("options color contrast (WCAG 1.4.3)", () => {
  const css = readCss(OPTIONS_CSS_PATH);
  const dark = extractTokenBlock(css, ':root[data-theme="dark"]');
  const light = extractTokenBlock(css, ':root[data-theme="light"]');

  //   body text       → color:var(--text)        on background:var(--bg)
  //   .nav-item       → color:var(--text-muted)  on .sidebar background:var(--bg-elevated)
  //   .field input    → color:var(--text-strong) on background:var(--bg-elevated)
  //   .field-help     → color:var(--text-muted)  on background:var(--bg)
  const PASSING: TextPair[] = [
    { what: "body text on background", fg: "text", bg: "bg", min: AA_NORMAL },
    { what: "nav-item label on sidebar (elevated) bg", fg: "text-muted", bg: "bg-elevated", min: AA_NORMAL },
    { what: "field input text on elevated input bg", fg: "text-strong", bg: "bg-elevated", min: AA_NORMAL },
    { what: "field-help text on background", fg: "text-muted", bg: "bg", min: AA_NORMAL },
  ];

  it("sanity: both theme token sets were parsed from the real CSS (catches: broken token extraction)", () => {
    expect(Object.keys(dark).length).toBeGreaterThan(3);
    expect(Object.keys(light).length).toBeGreaterThan(3);
    expect(dark.text).toBeTruthy();
    expect(light.text).toBeTruthy();
  });

  for (const p of PASSING) {
    it(`DARK: ${p.what} meets AA ${p.min}:1`, () => {
      const ratio = pairRatio(dark, p);
      expect(ratio, `${p.what} (dark) = ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(p.min);
    });
    it(`LIGHT: ${p.what} meets AA ${p.min}:1`, () => {
      const ratio = pairRatio(light, p);
      expect(ratio, `${p.what} (light) = ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(p.min);
    });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// B. GENUINE DEFECT SURFACING — these are REAL WCAG AA failures in the committed
//    CSS. They are intentionally KEPT RED (the threshold is NOT lowered) so the
//    defect is surfaced with its computed ratio, not painted green. Per the task:
//    a real failing pair is a finding worth reporting. The conductor decides the
//    CSS fix — this suite does not touch production CSS.
//
//    NOTE: if/when the CSS is fixed (token lightened/darkened to ≥ 4.5:1), these
//    flip GREEN automatically — they are honest guards, not permanent failures.
// ─────────────────────────────────────────────────────────────────────────────

describe("DEFECT: real popup color-contrast failures (WCAG 1.4.3) — kept RED", () => {
  const css = readCss(POPUP_CSS_PATH);
  const dark = extractTokenBlock(css, ':root[data-theme="dark"]');
  const light = extractTokenBlock(css, ':root[data-theme="light"]');

  // `--text-faint` paints `.section-title` (11px uppercase), `.torrent-hash`
  // (11px), `.empty`/meta secondary text — all NORMAL text (< 18.66px, not
  // 14pt-bold), so WCAG AA requires ≥ 4.5:1. Computed: dark 4.07, light 3.14.
  it("DARK: --text-faint on --bg must meet AA 4.5:1 (real ratio surfaced)", () => {
    const ratio = contrastRatio(
      mustExist(dark["text-faint"], "--text-faint (dark)"),
      mustExist(dark.bg, "--bg (dark)"),
    );
    expect(
      ratio,
      `--text-faint #${dark["text-faint"]} on --bg #${dark.bg} = ${ratio.toFixed(2)}:1 (needs ≥ 4.5:1 for 11px section-title/hash text)`,
    ).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it("LIGHT: --text-faint on --bg must meet AA 4.5:1 (real ratio surfaced)", () => {
    const ratio = contrastRatio(
      mustExist(light["text-faint"], "--text-faint (light)"),
      mustExist(light.bg, "--bg (light)"),
    );
    expect(
      ratio,
      `--text-faint #${light["text-faint"]} on --bg #${light.bg} = ${ratio.toFixed(2)}:1 (needs ≥ 4.5:1)`,
    ).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  // `.connection-warning` text uses --warning-text at 12px (normal text). The
  // LIGHT theme pair computes 4.40:1 — just under the 4.5 AA floor.
  it("LIGHT: --warning-text on --warning-bg must meet AA 4.5:1 (real ratio surfaced)", () => {
    const ratio = contrastRatio(
      mustExist(light["warning-text"], "--warning-text (light)"),
      mustExist(light["warning-bg"], "--warning-bg (light)"),
    );
    expect(
      ratio,
      `--warning-text #${light["warning-text"]} on --warning-bg #${light["warning-bg"]} = ${ratio.toFixed(2)}:1 (needs ≥ 4.5:1 for 12px warning text)`,
    ).toBeGreaterThanOrEqual(AA_NORMAL);
  });
});
