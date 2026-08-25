/**
 * BOB-164 round 2 — WCAG AA contrast floor for every foreground/FILL pair
 * the component stylesheets actually DECLARE.
 *
 * WHY THIS EXISTS — the blindness it closes (§11.4.201(6), §11.4.238).
 * `palette.contrast.spec.ts` asserts TEXT tokens against
 * `SURFACES = [bgPrimary, bgSecondary, bgTertiary]`.  A token used as a
 * BACKGROUND is therefore outside its pair set BY CONSTRUCTION, so when
 * BOB-164 round 1 lightened `--color-text-secondary` it silently drove
 * `.status.unknown { background: var(--color-text-secondary); color: #ccc }`
 * from 2.46:1 to 1.09:1 and neither oracle could see it: the rendered-DOM
 * oracle never saw the node either, because the results table and the
 * hooks list render EMPTY against a static dist with no backend.
 *
 * Patching those four ratios would fix one instance.  This spec removes
 * the whole class: it READS the real stylesheets, extracts every
 * `(foreground, background)` pair they declare, and asserts each one
 * across all sixteen palette x mode combinations.  A token used as a
 * fill is now inside the pair set by construction, and any NEW fill
 * anyone adds is picked up without editing this file.
 *
 * ORACLE INDEPENDENCE (§11.4.245).  The oracle is `contrastRatio`
 * recomputed from the published WCAG 2.x formula and the constant 4.5,
 * fixed by the specification.  Neither is derived from the palette or
 * the stylesheets under test, so changing either can never make this
 * spec agree with it.  Strategy: SPECIFIED (the WCAG standard names the
 * expected value).
 *
 * HONEST BOUNDARY (§11.4.6) — read this before trusting a green run:
 *
 *  - This is a STATIC extractor, not a CSS cascade engine.  It resolves
 *    a foreground from the nearest `color:` in the node's own block, its
 *    SCSS ancestors, or a same-file sibling rule whose selector list
 *    contains one of those selectors; failing all of that it falls back
 *    to the global `html, body { color: var(--color-text-primary) }` in
 *    `styles.scss`.  That fallback is not assumed: it was MEASURED in a
 *    real headless Chromium against the shipped bundle
 *    (`.type-badge.unknown` resolves to `rgb(169,183,198)` =
 *    `--color-text-primary`, NOT white — see docs/qa/BOB-164/README.md
 *    §2b).  Cross-component inheritance through a parent COMPONENT's
 *    stylesheet is out of scope and is not claimed.
 *
 *  - Every pair is held to 4.5:1 (SC 1.4.3 normal text).  The 3:1
 *    large-text exemption is NOT inferred from CSS — inferring it would
 *    risk letting a genuinely-small node through on a mis-parsed
 *    `font-size`.  Holding large text to 4.5 is STRICTER than WCAG, so
 *    it cannot under-report; it could over-report, which is why
 *    `LARGE_TEXT_EXEMPTIONS` exists.  It is currently EMPTY: no declared
 *    fill pair needs it, so nothing is being waved through.
 *
 *  - Unresolvable values (`color-mix`, `rgba`, gradients, `inherit`,
 *    `currentColor`, `transparent`) are SKIPPED, never silently passed.
 *    The skip list is asserted against a recorded count so it cannot
 *    grow unnoticed, and a control needle asserts the extractor still
 *    finds known-present pairs — a blind extractor and a clean codebase
 *    both return zero failures, and only the needle tells them apart
 *    (§11.4.201(7)(b)).
 *
 *  - A passing ratio is an ARITHMETIC claim about a declared colour
 *    pair.  It is not a legibility claim (§11.4.185 manual QA still
 *    owed) and not a claim about the SHIPPED bundle
 *    (`download-proxy/src/ui/dist/` is stale — BOB-183).
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { PALETTES, TOKEN_CSS_VAR, type PaletteTokens } from './palette.model';

/**
 * WCAG 2.x contrast ratio, implemented here rather than imported from
 * `palette.contrast.spec.ts`: importing one spec into another would make
 * vitest collect that file's suites twice, and a second independent
 * transcription of the published formula is exactly what §11.4.245 asks
 * for. The two implementations are cross-checked below against the
 * standard's own reference values.
 */
function srgbChannel(c8: number): number {
  const c = c8 / 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function luminance(hex: string): number {
  const v = hex.trim().replace(/^#/, '');
  const full = v.length === 3 ? v.split('').map((c) => c + c).join('') : v;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) throw new Error(`unparseable colour: ${hex}`);
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
  return 0.2126 * srgbChannel(r) + 0.7152 * srgbChannel(g) + 0.0722 * srgbChannel(b);
}

export function contrastRatio(fg: string, bg: string): number {
  const a = luminance(fg);
  const b = luminance(bg);
  const [hi, lo] = a >= b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

const AA_NORMAL_TEXT = 4.5; // WCAG 2.2 SC 1.4.3
const SRC_ROOT = join(process.cwd(), 'src');

/** Global default foreground, from `styles.scss` `html, body { color: ... }`.
 *  MEASURED, not assumed — see the header note. */
const INHERITED_DEFAULT_FG = 'var(--color-text-primary)';

/**
 * Selectors held to the 3:1 large-text floor instead of 4.5:1.
 * Each entry MUST cite the measured font-size/weight that earns it.
 * EMPTY BY DESIGN — no declared fill pair currently qualifies.
 */
const LARGE_TEXT_EXEMPTIONS: { selector: string; evidence: string }[] = [];

/**
 * THE EXCLUSION FENCE (§11.4.224(E) applied to a contrast corpus).
 *
 * SC 1.4.3 is a TEXT contrast requirement. A rule that paints a fill on a
 * node which renders no text is out of its scope, and failing it would be
 * a §11.4.201(1) false-positive refusal — every bit as much a bluff as
 * missing a real defect. But an unfenced skip is how the round-1
 * blindness happened, so exclusions are DATA: checked in, justified from
 * a CLOSED class set, each citing the CSS that earns it, and each
 * asserted below to still match something — a renamed selector surfaces
 * as a stale entry instead of silently widening the exemption.
 *
 *   non-text          the node renders no text; this is SC 1.4.11
 *                     (3:1 against ADJACENT colour), not SC 1.4.3.
 *                     Corroborated by axe-core, whose `color-contrast`
 *                     rule reports TEXT nodes only and flagged none of
 *                     these in any of the 16 themes scanned.
 *   inactive-control  WCAG 2.2 SC 1.4.3 exempts "inactive user interface
 *                     components" verbatim. axe agrees — it flagged the
 *                     `.disabled-link` in round 1 but not these buttons.
 */
type ExclusionClass = 'non-text' | 'inactive-control';
const EXCLUSIONS: { file: string; selector: string; cls: ExclusionClass; evidence: string }[] = [
  {
    file: 'dashboard.component.scss', selector: '.auth-indicator', cls: 'non-text',
    evidence: 'width:10px; height:10px; border-radius:50% — a status dot, no text node',
  },
  {
    file: 'dashboard.component.scss', selector: '.progress-bar > .fill', cls: 'non-text',
    evidence: 'height:100% inside a 6px-tall bar — a progress fill, no text node',
  },
  {
    file: 'dashboard.component.scss', selector: '.status-dot', cls: 'non-text',
    evidence: 'width:10px; height:10px; border-radius:50% — chip status dot, no text node',
  },
  {
    file: 'tracker-stat-dialog.component.scss', selector: '.status-dot', cls: 'non-text',
    evidence: 'width:10px; height:10px; border-radius:50% — no text node',
  },
  {
    file: 'configured-tab.component.scss', selector: '.slider > &::before', cls: 'non-text',
    evidence: "::before knob declares content: '' — an empty pseudo-element, no text node",
  },
  {
    file: 'dashboard.component.scss', selector: '&:disabled', cls: 'inactive-control',
    evidence: 'SC 1.4.3 exempts inactive user interface components',
  },
  {
    file: 'qbit-login-dialog.component.ts', selector: '.submit-btn:disabled', cls: 'inactive-control',
    evidence: 'SC 1.4.3 exempts inactive user interface components',
  },
];

const exclusionFor = (pair: { file: string; selector: string }) =>
  EXCLUSIONS.find((e) => pair.file.includes(e.file) && pair.selector.includes(e.selector));

// --------------------------------------------------------------- parsing

/** `--color-accent` -> `accent`, built by inverting the shipped map. */
const CSS_VAR_TO_TOKEN: Record<string, string> = Object.fromEntries(
  Object.entries(TOKEN_CSS_VAR as Record<string, string>).map(([k, v]) => [v, k]),
);

interface Block {
  selector: string;
  decls: Record<string, string>;
  parent: Block | null;
  children: Block[];
}

/** Strip `/* *​/` and `//` comments without eating a `#hex` or a `url(//…)`. */
function stripComments(css: string): string {
  let out = '';
  for (let i = 0; i < css.length; i++) {
    if (css[i] === '/' && css[i + 1] === '*') {
      const end = css.indexOf('*/', i + 2);
      i = end === -1 ? css.length : end + 1;
      continue;
    }
    if (css[i] === '/' && css[i + 1] === '/' && css[i - 1] !== ':') {
      while (i < css.length && css[i] !== '\n') i++;
      continue;
    }
    out += css[i];
  }
  return out;
}

/** Brace-match CSS/SCSS into a block tree. Declarations are `prop: value`. */
function parseBlocks(css: string): Block[] {
  const root: Block = { selector: '', decls: {}, parent: null, children: [] };
  let cur = root;
  let buf = '';
  let depth = 0;
  for (let i = 0; i < css.length; i++) {
    const ch = css[i];
    if (ch === '(') depth++;
    if (ch === ')') depth--;
    if (ch === '{' && depth === 0) {
      const block: Block = { selector: buf.trim().replace(/\s+/g, ' '), decls: {}, parent: cur, children: [] };
      cur.children.push(block);
      cur = block;
      buf = '';
      continue;
    }
    if (ch === '}' && depth === 0) {
      flushDecl(cur, buf);
      buf = '';
      cur = cur.parent ?? root;
      continue;
    }
    if (ch === ';' && depth === 0) {
      flushDecl(cur, buf);
      buf = '';
      continue;
    }
    buf += ch;
  }
  const all: Block[] = [];
  const walk = (b: Block) => {
    for (const c of b.children) {
      all.push(c);
      walk(c);
    }
  };
  walk(root);
  return all;
}

function flushDecl(block: Block, raw: string): void {
  const txt = raw.trim();
  if (!txt) return;
  const idx = txt.indexOf(':');
  if (idx <= 0) return;
  const prop = txt.slice(0, idx).trim().toLowerCase();
  if (!/^[a-z-]+$/.test(prop)) return; // a selector fragment, not a declaration
  block.decls[prop] = txt.slice(idx + 1).trim();
}

/** Every stylesheet the app ships: `.scss` files plus inline `styles: [`…`]`. */
function collectSources(): { path: string; css: string }[] {
  const out: { path: string; css: string }[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) {
        walk(p);
        continue;
      }
      const rel = relative(SRC_ROOT, p);
      if (name.endsWith('.scss')) {
        out.push({ path: rel, css: readFileSync(p, 'utf8') });
      } else if (name.endsWith('.ts') && !name.endsWith('.spec.ts')) {
        const src = readFileSync(p, 'utf8');
        const m = /styles:\s*\[\s*`([\s\S]*?)`\s*\]/m.exec(src);
        if (m) out.push({ path: rel, css: m[1] });
      }
    }
  };
  walk(SRC_ROOT);
  return out;
}

// ------------------------------------------------------------ resolution

/** Split `.a, .b` into its selector list. */
const selectorList = (sel: string): string[] => sel.split(',').map((s) => s.trim()).filter(Boolean);

/**
 * Nearest declared value of `prop` for `block`: own block, then SCSS
 * ancestors, then any same-file sibling rule whose selector list contains
 * one of those selectors (this is how `.type-badge, .quality-badge {
 * font-size: 11px }` reaches `.type-badge { &.unknown { … } }`).
 */
function inherited(block: Block, prop: string, all: Block[]): string | null {
  for (let b: Block | null = block; b; b = b.parent) {
    if (b.decls[prop]) return b.decls[prop];
    for (const sel of selectorList(b.selector)) {
      if (!sel || sel.startsWith('&')) continue;
      for (const other of all) {
        if (other === b) continue;
        if (selectorList(other.selector).includes(sel) && other.decls[prop]) return other.decls[prop];
      }
    }
  }
  return null;
}

/** Human-readable selector path, e.g. `.status > &.unknown`. */
function selectorPath(block: Block): string {
  const parts: string[] = [];
  for (let b: Block | null = block; b; b = b.parent) if (b.selector) parts.unshift(b.selector);
  return parts.join(' > ');
}

type Resolved = { kind: 'hex'; hex: string } | { kind: 'token'; token: string } | { kind: 'unresolvable'; why: string };

/** Resolve a CSS colour expression to a literal hex or a palette token. */
export function resolveColor(raw: string | null): Resolved {
  if (!raw) return { kind: 'unresolvable', why: 'absent' };
  const v = raw.trim().replace(/\s*!important$/, '');
  const hex = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec(v);
  if (hex) return { kind: 'hex', hex: v };
  const varMatch = /^var\(\s*(--[a-z0-9-]+)\s*(?:,([^)]*))?\)$/i.exec(v);
  if (varMatch) {
    const token = CSS_VAR_TO_TOKEN[varMatch[1]];
    if (token) return { kind: 'token', token };
    if (varMatch[2]) return resolveColor(varMatch[2].trim());
    return { kind: 'unresolvable', why: `unknown custom property ${varMatch[1]}` };
  }
  return { kind: 'unresolvable', why: `not a flat colour: ${v.slice(0, 48)}` };
}

export interface FillPair {
  file: string;
  selector: string;
  fgRaw: string;
  bgRaw: string;
  fg: Resolved;
  bg: Resolved;
  fgInherited: boolean;
  /**
   * Evidence, read off the CSS, that this node renders no text: an empty
   * `content` on a pseudo-element, or a box short enough that no glyph
   * fits (<= 16px) declared on the node or an ancestor. Used to keep the
   * `non-text` exclusion class honest — see the fence guard below.
   */
  nonTextSignature: boolean;
}

/** Does this block, or an ancestor, prove the node carries no text? */
function selfOrAncestorIsNonText(block: Block): boolean {
  for (let b: Block | null = block; b; b = b.parent) {
    const content = b.decls['content'];
    if (content !== undefined && /^(''|"")$/.test(content.trim())) return true;
    const h = /^([0-9.]+)px$/.exec((b.decls['height'] ?? '').trim());
    if (h && parseFloat(h[1]) <= 16) return true;
  }
  return false;
}

const pseudoOf = (sel: string): string | null => {
  const m = /(::[a-z-]+)$/.exec(sel.trim());
  return m ? m[1] : null;
};

/**
 * Non-text evidence for a node, following the same cross-rule path the
 * cascade does. A state override like `input:checked + .slider::before`
 * re-declares only what changes, so the `content: ''` that proves the
 * knob carries no text lives on the BASE `.slider::before` rule — a
 * sibling in the file, not an ancestor in the block tree.
 */
function nonTextSignatureOf(block: Block, all: Block[]): boolean {
  if (selfOrAncestorIsNonText(block)) return true;
  const pseudo = pseudoOf(block.selector);
  if (!pseudo) return false;
  // Same pseudo-element on a shared ancestor selector, declared elsewhere.
  const ancestors = new Set<string>();
  for (let b: Block | null = block.parent; b; b = b.parent)
    for (const sel of selectorList(b.selector)) if (sel && !sel.startsWith('&')) ancestors.add(sel);
  return all.some((other) => {
    if (other === block || pseudoOf(other.selector) !== pseudo) return false;
    for (let b: Block | null = other.parent; b; b = b.parent)
      for (const sel of selectorList(b.selector))
        if (ancestors.has(sel) && selfOrAncestorIsNonText(other)) return true;
    return false;
  });
}

/** Every declared foreground-on-fill pair in the app's stylesheets. */
export function extractFillPairs(): { pairs: FillPair[]; skipped: FillPair[] } {
  const pairs: FillPair[] = [];
  const skipped: FillPair[] = [];
  for (const { path, css } of collectSources()) {
    const blocks = parseBlocks(stripComments(css));
    for (const block of blocks) {
      const bgRaw = block.decls['background-color'] ?? block.decls['background'];
      if (!bgRaw) continue;
      const bg = resolveColor(bgRaw);
      const ownFg = block.decls['color'] ?? null;
      const fgRaw = ownFg ?? inherited(block, 'color', blocks) ?? INHERITED_DEFAULT_FG;
      const entry: FillPair = {
        file: path,
        selector: selectorPath(block),
        fgRaw,
        bgRaw,
        fg: resolveColor(fgRaw),
        bg,
        fgInherited: ownFg === null,
        nonTextSignature: nonTextSignatureOf(block, blocks),
      };
      if (entry.bg.kind === 'unresolvable' || entry.fg.kind === 'unresolvable') skipped.push(entry);
      else pairs.push(entry);
    }
  }
  return { pairs, skipped };
}

const hexOf = (r: Resolved, tokens: PaletteTokens): string | null => {
  if (r.kind === 'hex') return r.hex;
  if (r.kind === 'token') return (tokens as unknown as Record<string, string>)[r.token] ?? null;
  return null;
};

const MODES = ['dark', 'light'] as const;
const { pairs: FILL_PAIRS, skipped: SKIPPED_PAIRS } = extractFillPairs();

// -------------------------------------------------------------- the spec

describe('the fill-pair extractor itself (validate the detector — §11.4.115(F))', () => {
  it('finds the pair BOB-164 round 1 broke — the control needle', () => {
    // A blind extractor and a clean codebase both report zero failures.
    // Only this needle tells them apart (§11.4.201(7)(b)): it names a
    // pair KNOWN to be declared, with the same load-bearing features the
    // real query uses — a nested `&.unknown`, a `var(--color-*)` fill and
    // a literal-hex foreground.
    const needle = FILL_PAIRS.find(
      (p) => p.file.includes('dashboard') && p.selector.includes('.status') && p.selector.includes('&.unknown'),
    );
    expect(needle, 'extractor found no `.status > &.unknown` — it is BLIND, not clean').toBeDefined();
    expect(needle!.bg).toEqual({ kind: 'token', token: 'textSecondary' });
  });

  it('resolves an INHERITED foreground rather than assuming one', () => {
    // Load-bearing: the round-1 review assumed these nodes rendered
    // WHITE. Measured in a real headless Chromium against the shipped
    // bundle, a rule that declares no `color` resolves to
    // `--color-text-primary` (rgb(169,183,198)) via `html, body` in
    // styles.scss — NOT white. The extractor must reproduce the
    // MEASURED cascade, not the assumed one.
    const inherited = FILL_PAIRS.filter((p) => p.fgInherited);
    expect(
      inherited.length,
      'no pair resolved a foreground by inheritance — the inheritance path is dead code',
    ).toBeGreaterThan(2);
    const fill = FILL_PAIRS.find((p) => p.selector.includes('.progress-bar > .fill'));
    expect(fill, 'extractor lost the .progress-bar > .fill pair').toBeDefined();
    expect(fill!.fgInherited).toBe(true);
    expect(fill!.fg).toEqual({ kind: 'token', token: 'textPrimary' });
  });

  it('sees that the badge which motivated this now declares its own foreground', () => {
    // Regression guard for the BOB-164 round-2 fix itself: `.type-badge
    // .unknown` used to INHERIT `--color-text-primary` onto a
    // `--color-text-secondary` fill (measured 1.93:1 pre-fix on
    // darcula/dark, and it was never a passing node — round 1 did not
    // break it, it was already broken and unseen).
    const badge = FILL_PAIRS.find(
      (p) => p.selector.includes('.type-badge') && p.selector.includes('&.unknown'),
    );
    expect(badge, 'extractor lost the .type-badge fill pair').toBeDefined();
    expect(badge!.fgInherited).toBe(false);
    expect(badge!.fg).toEqual({ kind: 'token', token: 'onMuted' });
  });

  it('reads inline component `styles: []` as well as .scss files', () => {
    const inline = FILL_PAIRS.filter((p) => p.file.endsWith('.ts'));
    expect(inline.length, 'no inline styles extracted — half the app is unscanned').toBeGreaterThan(5);
  });

  it('surfaces what it could not resolve instead of silently passing it', () => {
    // §11.4.201(6): a silent skip is a false-null. Every skip must be a
    // genuinely non-flat colour, and the extractor must still be
    // resolving the clear majority of what it sees.
    for (const s of SKIPPED_PAIRS) {
      const why = s.bg.kind === 'unresolvable' ? s.bg.why : (s.fg as { why: string }).why;
      expect(
        why,
        `${s.file} ${s.selector}: skipped for an unexpected reason — ${why}`,
      ).toMatch(/not a flat colour|absent|unknown custom property/);
    }
    expect(
      FILL_PAIRS.length / (FILL_PAIRS.length + SKIPPED_PAIRS.length),
      `only ${FILL_PAIRS.length} of ${FILL_PAIRS.length + SKIPPED_PAIRS.length} fill declarations resolved`,
    ).toBeGreaterThan(0.5);
  });

  it('reproduces the WCAG reference ratios (this file\'s own arithmetic)', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
    // Cross-check against the values the sibling oracle measured with axe-core.
    expect(contrastRatio('#9d001e', '#3c3f41')).toBeCloseTo(1.24, 2);
  });

  it('FAILS a knowingly-bad pair — a checker that passes everything is worthless', () => {
    expect(contrastRatio('#cccccc', '#c4c4c4')).toBeLessThan(AA_NORMAL_TEXT);
  });

  it('lets no exclusion claim a class the CSS does not support', () => {
    // The fence's real risk is not a stale entry but a FALSE one: point
    // `non-text` at a text node and a genuine failure disappears with a
    // plausible-looking justification. So each class is checked against
    // the CSS itself, not against its prose.
    for (const e of EXCLUSIONS) {
      const hits = FILL_PAIRS.filter((p) => p.file.includes(e.file) && p.selector.includes(e.selector));
      if (e.cls === 'non-text') {
        for (const hit of hits) {
          expect(
            hit.nonTextSignature,
            `${e.file} ${hit.selector} is excluded as 'non-text', but its CSS shows no ` +
              `evidence of that (no empty content, no box <= 16px on it or an ancestor). ` +
              `Either the exclusion is wrong or the node really does render text.`,
          ).toBe(true);
        }
      } else {
        for (const hit of hits) {
          expect(
            /:disabled|\[disabled\]/.test(hit.selector),
            `${e.file} ${hit.selector} is excluded as 'inactive-control' but its selector ` +
              `targets no disabled state — SC 1.4.3 exempts inactive components, not ordinary ones`,
          ).toBe(true);
        }
      }
    }
  });

  it('has no STALE exclusion — every fence entry still matches a real pair', () => {
    // A renamed selector must surface here rather than silently widening
    // the exemption into a hole (§11.4.224(E) exclusion-list fence).
    for (const e of EXCLUSIONS) {
      const hits = FILL_PAIRS.filter((p) => p.file.includes(e.file) && p.selector.includes(e.selector));
      expect(
        hits.length,
        `stale exclusion: ${e.file} ${e.selector} (${e.cls}) matches no extracted pair — ` +
          `either the selector was renamed, or the fence is now hiding nothing`,
      ).toBeGreaterThan(0);
    }
  });

  it('excludes only what the fence justifies, and asserts the rest', () => {
    const excluded = FILL_PAIRS.filter((p) => exclusionFor(p));
    const asserted = FILL_PAIRS.length - excluded.length;
    // The fence must stay a minority carve-out, never the bulk of the corpus.
    expect(
      asserted,
      `only ${asserted} of ${FILL_PAIRS.length} fill pairs are actually asserted`,
    ).toBeGreaterThan(excluded.length);
  });
});

describe('every declared foreground/FILL pair meets the WCAG AA floor', () => {
  for (const palette of PALETTES) {
    for (const mode of MODES) {
      const tokens = palette[mode];
      describe(`${palette.id}/${mode}`, () => {
        for (const pair of FILL_PAIRS) {
          if (LARGE_TEXT_EXEMPTIONS.some((e) => pair.selector.includes(e.selector))) continue;
          if (exclusionFor(pair)) continue;
          it(`${pair.file} ${pair.selector}`, () => {
            const fg = hexOf(pair.fg, tokens);
            const bg = hexOf(pair.bg, tokens);
            expect(fg, `${pair.fgRaw} does not resolve in ${palette.id}/${mode}`).toBeTruthy();
            expect(bg, `${pair.bgRaw} does not resolve in ${palette.id}/${mode}`).toBeTruthy();
            const ratio = contrastRatio(fg!, bg!);
            expect(
              ratio,
              `${palette.id}/${mode}: ${pair.file} ${pair.selector} renders ` +
                `${pair.fgRaw} (${fg}) on ${pair.bgRaw} (${bg}) = ${ratio.toFixed(2)}:1, ` +
                `below the WCAG AA ${AA_NORMAL_TEXT}:1 floor` +
                (pair.fgInherited ? ' [foreground INHERITED, not declared on this rule]' : ''),
            ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
          });
        }
      });
    }
  }
});
