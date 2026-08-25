/**
 * BOB-164 — WCAG AA contrast floor for every palette token pair the UI
 * actually renders.
 *
 * WHY THIS EXISTS (§11.4.224 test-first, §11.4.245 oracle independence):
 * the rendered-DOM oracle (axe-core, driven by
 * `docs/qa/BOB-164/axe_contrast_scan.py`) can only see the palette that
 * happens to be active on the page it scans — one of sixteen
 * palette x mode combinations.  This spec is the SECOND, independent
 * oracle: it recomputes the WCAG 2.x contrast ratio straight from the
 * published formula over the WHOLE catalogue, so a palette nobody
 * screenshotted cannot silently ship below the floor.
 *
 * The oracle is structurally independent of the code under test: the
 * expected values are the WCAG constants 4.5 (normal text) and 3.0
 * (large text / non-text), fixed by the specification — never derived
 * from whatever `palette.model.ts` currently declares.  Changing a
 * palette can therefore never make this spec agree with it.
 *
 * PAIRS ASSERTED are the ones MEASURED in the rendered dashboard
 * (docs/qa/BOB-164/scan_RED_shipped.json), not an assumed cross product:
 *   textPrimary   on bgPrimary / bgSecondary / bgTertiary
 *   textSecondary on bgPrimary / bgSecondary / bgTertiary
 *   accentText    on bgPrimary / bgSecondary / bgTertiary
 *
 * HONEST BOUNDARY (§11.4.6): a passing ratio proves the ARITHMETIC floor
 * is met for the declared token pair.  It does NOT prove the rendered UI
 * is legible — font weight, size, anti-aliasing, opacity applied by
 * component CSS, and any background image are all outside a colour-pair
 * ratio.  Those are the rendered-DOM oracle's job, and neither oracle
 * substitutes for the other.
 */

import { describe, expect, it } from 'vitest';
import { PALETTES, PALETTE_TOKEN_KEYS, TOKEN_CSS_VAR, type PaletteTokens } from './palette.model';

/** WCAG 2.x per-channel linearisation. */
function srgbChannel(c8: number): number {
  const c = c8 / 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function parseHex(value: string): [number, number, number] {
  const v = value.trim().replace(/^#/, '');
  const full = v.length === 3 ? v.split('').map((c) => c + c).join('') : v;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) throw new Error(`unparseable colour: ${value}`);
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ];
}

/** WCAG 2.x relative luminance. */
export function relativeLuminance(hex: string): number {
  const [r, g, b] = parseHex(hex);
  return 0.2126 * srgbChannel(r) + 0.7152 * srgbChannel(g) + 0.0722 * srgbChannel(b);
}

/** WCAG 2.x contrast ratio (L1 + 0.05) / (L2 + 0.05), L1 the lighter. */
export function contrastRatio(fg: string, bg: string): number {
  const a = relativeLuminance(fg);
  const b = relativeLuminance(bg);
  const [hi, lo] = a >= b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

const AA_NORMAL_TEXT = 4.5; // WCAG 2.2 SC 1.4.3
const AA_LARGE_TEXT = 3.0; // WCAG 2.2 SC 1.4.3 (>=18pt, or >=14pt bold)

const SURFACES: (keyof PaletteTokens)[] = ['bgPrimary', 'bgSecondary', 'bgTertiary'];

// Read through a string index so this spec COMPILES against a catalogue
// that does not yet declare `accentText` — the RED must fail on the
// CONTRAST arithmetic (the real defect), never on a type error, which
// would prove nothing about colour (§11.4.115).
const TEXT_TOKENS = ['textPrimary', 'textSecondary', 'accentText', 'dangerText', 'warningText', 'contrastText'] as const;
const tokenValue = (t: PaletteTokens, key: string): string =>
  (t as unknown as Record<string, string>)[key];
const MODES = ['dark', 'light'] as const;

describe('WCAG contrast arithmetic (the oracle itself)', () => {
  // §11.4.115(F) / §11.4.201 — validate the detector before trusting it.
  it('reproduces the WCAG reference ratios for black/white', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
  });

  it('is symmetric in its arguments', () => {
    expect(contrastRatio('#9d001e', '#3c3f41')).toBeCloseTo(contrastRatio('#3c3f41', '#9d001e'), 10);
  });

  it('reproduces the BOB-164 measured pairs (cross-checked against axe-core 4.13.0)', () => {
    // Values captured in docs/qa/BOB-164/scan_RED_shipped.json.
    expect(contrastRatio('#9d001e', '#3c3f41')).toBeCloseTo(1.24, 2); // accent on card
    expect(contrastRatio('#808080', '#3c3f41')).toBeCloseTo(2.69, 2); // muted on card
    expect(contrastRatio('#a9b7c6', '#4e5254')).toBeCloseTo(3.86, 2); // body on chip
  });

  it('FAILS a knowingly-bad pair — a checker that passes everything is worthless', () => {
    expect(contrastRatio('#808080', '#7f7f7f')).toBeLessThan(AA_NORMAL_TEXT);
    expect(contrastRatio('#9d001e', '#3c3f41')).toBeLessThan(AA_LARGE_TEXT);
  });
});

describe('palette catalogue meets the WCAG AA contrast floor', () => {
  for (const palette of PALETTES) {
    for (const mode of MODES) {
      const tokens = palette[mode];

      describe(`${palette.id}/${mode}`, () => {
        for (const text of TEXT_TOKENS) {
          for (const surface of SURFACES) {
            it(`${text} on ${surface} >= ${AA_NORMAL_TEXT}:1`, () => {
              const fg = tokenValue(tokens, text);
              const bg = tokens[surface];
              expect(fg, `${palette.id}/${mode} is missing token '${text}'`).toBeTruthy();
              const ratio = contrastRatio(fg, bg);
              expect(
                ratio,
                `${palette.id}/${mode}: ${text} ${fg} on ${surface} ${bg} = ` +
                  `${ratio.toFixed(2)}:1, below the WCAG AA ${AA_NORMAL_TEXT}:1 ` +
                  `floor for normal-size text`,
              ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
            });
          }
        }

        // NEGATIVE CONTROL (§11.4.201(1)) — a pair that is comfortably
        // legible must NOT be reported as failing.  Without this, a
        // checker that flags every pair would look "correct".
        it('textPrimary on bgPrimary is comfortably above the floor (negative control)', () => {
          const ratio = contrastRatio(tokens.textPrimary, tokens.bgPrimary);
          expect(ratio).toBeGreaterThan(AA_NORMAL_TEXT);
        });

        // The muted tier must stay visibly muted; raising contrast must
        // not flatten the type hierarchy into one brightness.
        it('textSecondary stays dimmer than textPrimary against bgPrimary', () => {
          const primary = contrastRatio(tokens.textPrimary, tokens.bgPrimary);
          const secondary = contrastRatio(tokens.textSecondary, tokens.bgPrimary);
          expect(
            secondary,
            `${palette.id}/${mode}: textSecondary (${secondary.toFixed(2)}:1) must read ` +
              `as MUTED relative to textPrimary (${primary.toFixed(2)}:1)`,
          ).toBeLessThan(primary);
        });
      });
    }
  }

  it('every text-role token is wired for runtime application', () => {
    // §11.4.216 — a value that never reaches a CSS custom property is a
    // token in name only.  ThemeService iterates PALETTE_TOKEN_KEYS.
    const expected: Record<string, string> = {
      accentText: '--color-accent-text',
      dangerText: '--color-danger-text',
      warningText: '--color-warning-text',
      contrastText: '--color-contrast-text',
      onAccent: '--color-on-accent',
      onAccentHover: '--color-on-accent-hover',
      onSuccess: '--color-on-success',
      onInfo: '--color-on-info',
      onWarning: '--color-on-warning',
      onDanger: '--color-on-danger',
      onPurple: '--color-on-purple',
      onMuted: '--color-on-muted',
      onBorder: '--color-on-border',
    };
    for (const [key, cssVar] of Object.entries(expected)) {
      expect(PALETTE_TOKEN_KEYS as readonly string[]).toContain(key);
      expect((TOKEN_CSS_VAR as Record<string, string>)[key]).toBe(cssVar);
    }
  });

  it('leaves the decorative brand + semantic tokens untouched', () => {
    // §11.4.217: brand / semantic / accent-text are DISJOINT roles. The
    // Darcula blood-red is brand-locked (tests/unit/test_palette_catalog.py)
    // and must keep serving fills / focus rings / borders unchanged, and
    // raising text contrast must never repaint a semantic state colour.
    const darcula = PALETTES.find((p) => p.id === 'darcula');
    expect(darcula?.dark.accent).toBe('#9d001e');
    expect(darcula?.light.accent).toBe('#9d001e');
    expect(darcula?.dark.danger).toBe('#cc7832');
    expect(darcula?.dark.warning).toBe('#d9a441');
  });

  it('every on<Fill> token clears the floor against the FILL it sits on', () => {
    // These sites previously hardcoded `color: #fff` / `#ccc` / `#333`
    // against a runtime-switchable background — a pair that cannot be
    // guaranteed by construction. Measured worst cases before the fix:
    // 2.00:1 (white on Nord's #88c0d0 accent) and, after round 1
    // lightened textSecondary, 1.09:1 for `.status.unknown`.
    //
    // Round 2 generalised `onAccent` to every fill a stylesheet paints
    // text on, INCLUDING `accentHover` — which round 1 measured below
    // the floor in four palettes and recorded as unfixed. It is fixed
    // here rather than left as prose, so the note that claimed
    // otherwise is gone with it.
    const FILL_PAIRS: [on: string, fill: string][] = [
      ['onAccent', 'accent'],
      ['onAccentHover', 'accentHover'],
      ['onSuccess', 'success'],
      ['onInfo', 'info'],
      ['onWarning', 'warning'],
      ['onDanger', 'danger'],
      ['onPurple', 'purple'],
      ['onMuted', 'textSecondary'],
      ['onBorder', 'border'],
    ];
    for (const palette of PALETTES) {
      for (const mode of MODES) {
        const t = palette[mode] as unknown as Record<string, string>;
        for (const [on, fill] of FILL_PAIRS) {
          const ratio = contrastRatio(t[on], t[fill]);
          expect(
            ratio,
            `${palette.id}/${mode}: ${on} ${t[on]} on ${fill} fill ` +
              `${t[fill]} = ${ratio.toFixed(2)}:1`,
          ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
        }
      }
    }
  });

  it('no component stylesheet may hardcode a foreground on a token fill', () => {
    // The regression this guards: `color: #fff` against
    // `background: var(--color-accent)` passes on the default palette
    // and fails on seven others, so a single-theme audit cannot see it.
    // Kept as a token-level invariant here; the file-level scan lives in
    // docs/qa/BOB-164/axe_contrast_scan.py against the rendered DOM.
    for (const palette of PALETTES) {
      for (const mode of MODES) {
        const t = palette[mode] as unknown as Record<string, string>;
        for (const on of ['onAccent', 'onAccentHover', 'onSuccess', 'onInfo', 'onWarning',
                          'onDanger', 'onPurple', 'onMuted', 'onBorder']) {
          expect(['#ffffff', '#000000'], `${palette.id}/${mode}: ${on}`).toContain(t[on]);
        }
      }
    }
  });

  it('keeps every text-role token in its base token\'s hue family', () => {
    // A grey passes any contrast floor — and destroys the meaning of an
    // "error" or "brand" colour.  Guard the hue, not just the ratio.
    const hue = (hex: string): number => {
      const v = hex.replace('#', '');
      const [r, g, b] = [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16) / 255);
      const max = Math.max(r, g, b);
      const min = Math.min(r, g, b);
      if (max === min) return NaN; // achromatic
      const d = max - min;
      let h: number;
      if (max === r) h = ((g - b) / d) % 6;
      else if (max === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      return ((h * 60) + 360) % 360;
    };
    for (const palette of PALETTES) {
      for (const mode of MODES) {
        const t = palette[mode] as unknown as Record<string, string>;
        for (const [base, text] of [
          ['accent', 'accentText'],
          ['danger', 'dangerText'],
          ['warning', 'warningText'],
          ['contrast', 'contrastText'],
        ]) {
          const hb = hue(t[base]);
          const ht = hue(t[text]);
          expect(
            Number.isNaN(ht),
            `${palette.id}/${mode}: ${text} ${t[text]} went achromatic — a grey ` +
              `clears the contrast floor while erasing the state it encodes`,
          ).toBe(false);
          const delta = Math.min(Math.abs(hb - ht), 360 - Math.abs(hb - ht));
          expect(
            delta,
            `${palette.id}/${mode}: ${text} ${t[text]} (hue ${ht.toFixed(0)}) drifted ` +
              `from ${base} ${t[base]} (hue ${hb.toFixed(0)})`,
          ).toBeLessThanOrEqual(2);
        }
      }
    }
  });
});
