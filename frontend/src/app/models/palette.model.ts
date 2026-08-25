/**
 * Palette catalogue for the runtime-switchable theme system.
 *
 * Every palette ships a `light` and `dark` token set. Tokens are applied
 * to `document.documentElement` as CSS custom properties by
 * `ThemeService` so every app / dashboard / embedded surface picks them
 * up without hardcoded colours.
 *
 * Darcula's accent is the blood-red extracted from
 * `assets/Logo.jpeg` (`#9d001e`). The palette is based on the JetBrains
 * Darcula greys catalogued at https://colorshexa.com/palette/darcula-palette.
 *
 * When adding a palette:
 *   1. Keep every token a valid CSS colour (hex `#RRGGBB` or rgba(...)).
 *   2. Run `tests/unit/test_palette_catalog.py`.
 *   3. Run `tests/unit/test_theme_wiring.py`.
 *   4. Run `npx --prefix frontend ng test --watch=false`.
 */

export interface PaletteTokens {
  /** App background (main surface) */
  bgPrimary: string;
  /** Card / panel background */
  bgSecondary: string;
  /** Input / chip background (one step lighter than secondary in dark, darker in light) */
  bgTertiary: string;
  /** Borders + dividers */
  border: string;
  /** Primary readable text */
  textPrimary: string;
  /** Muted secondary text */
  textSecondary: string;
  /** Primary brand accent — DECORATIVE role only: fills, focus rings,
   *  borders, hover states.  NEVER use it as a text colour; see
   *  `accentText` (§11.4.217 — brand and accent-text are disjoint roles). */
  accent: string;
  /** Darker accent for hover */
  accentHover: string;
  /**
   * Readable, WCAG-AA-pinned variant of `accent`, for accent-coloured
   * TEXT (headings, active tabs, links).  Same hue as `accent`, shifted
   * in lightness until it clears 4.5:1 against `bgPrimary`,
   * `bgSecondary` AND `bgTertiary`.
   *
   * BOB-164: the brand red rendered as heading text measured 1.24:1
   * against `bgSecondary` (1.43-1.62:1 once the text-shadow token is
   * counted as the effective backdrop).  Splitting the role fixes
   * legibility without touching the brand colour itself, which stays
   * locked (tests/unit/test_palette_catalog.py asserts Darcula's dark
   * accent is the logo blood-red `#9d001e`).
   */
  accentText: string;
  /**
   * Foreground for text/icons sitting ON an `accent` FILL (CTA buttons,
   * the current nav pill).  Pure black or white, whichever clears
   * 4.5:1 against that palette's accent.
   *
   * BOB-164: these sites hardcoded `color: #fff` against a
   * runtime-switchable background, so the pair could never be
   * guaranteed — measured 2.00:1 on Nord's light-blue accent.
   * Round 2 note: round 1 pinned this against the RESTING `accent` fill
   * only and recorded four palettes below 4.5 against `accentHover` as
   * a measured-but-unfixed finding. `onAccentHover` now covers that
   * fill, so the gap is closed rather than documented.
   */
  onAccent: string;
  /** Secondary brand accent (e.g. Darcula uses a warm gold next to the blood-red) */
  contrast: string;
  /**
   * WCAG-AA-pinned TEXT variant of `contrast`, same hue and saturation,
   * lightness-shifted by the minimum amount that clears 4.5:1 against
   * `bgPrimary`, `bgSecondary` AND `bgTertiary`.
   *
   * BOB-164 round 2: `contrast` is the DECORATIVE secondary brand accent
   * (badges, chips). It was also being used as the `code` foreground in
   * the Jackett tables, where it measured 2.47:1 on nord/light — the same
   * brand-serving-a-text-role confusion round 1 fixed for `accent`,
   * missed here because no scan ever rendered those tables.
   *
   * Four dark palettes need no shift (their gold already clears the
   * floor); the value is still declared so the ROLE is explicit at every
   * call site rather than depending on which palette is active.
   */
  contrastText: string;
  success: string;
  /** Error / destructive state — DECORATIVE role (badge + toast fills,
   *  status borders).  For error TEXT use `dangerText`. */
  danger: string;
  /** Caution state — DECORATIVE role (badge + toast fills, borders).
   *  For caution TEXT use `warningText`. */
  warning: string;
  /**
   * WCAG-AA-pinned text variants of `danger` / `warning`, same hue,
   * lightness-shifted until they clear 4.5:1 on every surface token.
   *
   * BOB-164: the raw semantic tokens are tuned to carry WHITE text as a
   * badge fill, which makes them too saturated to BE text on the app's
   * own surfaces (measured: danger #cc7832 on bgTertiary = 2.37:1).
   */
  dangerText: string;
  warningText: string;
  info: string;
  purple: string;
  /**
   * Foregrounds for text sitting ON a non-accent FILL — the same role
   * `onAccent` serves for the accent fill, generalised to every other
   * token a stylesheet paints text on top of.
   *
   * BOB-164 round 2: round 1 raised `textSecondary` for legibility as
   * TEXT, and silently broke the places it is painted as a BACKGROUND —
   * `.status.unknown { background: var(--color-text-secondary);
   * color: #ccc }` fell from 2.46:1 to 1.09:1 on the default theme.
   * The root cause was not the four ratios but the ROLE: a hardcoded
   * literal (`#fff`, `#ccc`, `#333`) cannot be correct against a fill
   * that changes with the palette. These tokens make the pair
   * guaranteed by construction instead of by coincidence.
   *
   * Every value is pure black or pure white — whichever contrasts more
   * with that palette's fill. That always clears 4.5:1: contrast(#000,F)
   * and contrast(#fff,F) are equal only where BOTH equal 4.58, so their
   * maximum never drops below 4.58 and no fill colour has to move.
   *
   * `onMuted` sits on `textSecondary`-as-a-fill and `onBorder` on
   * `border`-as-a-fill; both are neutral chips, not new palette colours.
   */
  onAccentHover: string;
  onSuccess: string;
  onInfo: string;
  onWarning: string;
  onDanger: string;
  onPurple: string;
  onMuted: string;
  onBorder: string;
  /** Shadow rgba */
  shadow: string;
}

export type PaletteMode = 'light' | 'dark';

export interface Palette {
  id: string;
  name: string;
  description: string;
  /** Reference URL for the colour extraction source. */
  source: string;
  light: PaletteTokens;
  dark: PaletteTokens;
}

export const PALETTE_TOKEN_KEYS: readonly (keyof PaletteTokens)[] = [
  'bgPrimary',
  'bgSecondary',
  'bgTertiary',
  'border',
  'textPrimary',
  'textSecondary',
  'accent',
  'accentHover',
  'accentText',
  'onAccent',
  'onAccentHover',
  'onSuccess',
  'onInfo',
  'onWarning',
  'onDanger',
  'onPurple',
  'onMuted',
  'onBorder',
  'contrast',
  'contrastText',
  'success',
  'danger',
  'warning',
  'dangerText',
  'warningText',
  'info',
  'purple',
  'shadow',
] as const;

/** Mapping from the camelCase palette token to the CSS custom property. */
export const TOKEN_CSS_VAR: Record<keyof PaletteTokens, string> = {
  bgPrimary: '--color-bg-primary',
  bgSecondary: '--color-bg-secondary',
  bgTertiary: '--color-bg-tertiary',
  border: '--color-border',
  textPrimary: '--color-text-primary',
  textSecondary: '--color-text-secondary',
  accent: '--color-accent',
  accentHover: '--color-accent-hover',
  accentText: '--color-accent-text',
  onAccent: '--color-on-accent',
  onAccentHover: '--color-on-accent-hover',
  onSuccess: '--color-on-success',
  onInfo: '--color-on-info',
  onWarning: '--color-on-warning',
  onDanger: '--color-on-danger',
  onPurple: '--color-on-purple',
  onMuted: '--color-on-muted',
  onBorder: '--color-on-border',
  contrast: '--color-contrast',
  contrastText: '--color-contrast-text',
  success: '--color-success',
  danger: '--color-danger',
  warning: '--color-warning',
  dangerText: '--color-danger-text',
  warningText: '--color-warning-text',
  info: '--color-info',
  purple: '--color-purple',
  shadow: '--color-shadow',
};

export const PALETTES: Palette[] = [
  {
    id: 'darcula',
    name: 'Darcula',
    description: 'JetBrains Darcula greys — paired with the blood-red from the qBittorrent logo.',
    source: 'https://colorshexa.com/palette/darcula-palette',
    dark: {
      bgPrimary:     '#2b2b2b',
      bgSecondary:   '#3c3f41',
      bgTertiary:    '#4e5254',
      border:        '#555555',
      textPrimary:   '#c8d1da',
      textSecondary: '#c4c4c4',
      accent:        '#9d001e',   // logo blood-red
      accentHover:   '#c4002a',
      accentText:    '#ffaebd',
      onAccent:      '#ffffff',
      onAccentHover: '#ffffff',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#000000',
      onPurple:      '#000000',
      onMuted:       '#000000',
      onBorder:      '#ffffff',
      contrast:      '#d9a441',   // warm gold for secondary accent / badges
      contrastText: '#e4bf79',
      success:       '#6a8759',
      danger:        '#cc7832',
      warning:       '#d9a441',
      dangerText:    '#e6bc99',
      warningText:   '#e4bf79',
      info:          '#6897bb',
      purple:        '#9876aa',
      shadow:        'rgba(0,0,0,0.55)',
    },
    light: {
      bgPrimary:     '#ffffff',
      bgSecondary:   '#f2f2f2',
      bgTertiary:    '#e4e4e4',
      border:        '#c9c9c9',
      textPrimary:   '#1c1c1c',
      textSecondary: '#555555',
      accent:        '#9d001e',
      accentHover:   '#7d0017',
      accentText:    '#9d001e',
      onAccent:      '#ffffff',
      onAccentHover: '#ffffff',
      onSuccess:     '#ffffff',
      onInfo:        '#ffffff',
      onWarning:     '#000000',
      onDanger:      '#ffffff',
      onPurple:      '#ffffff',
      onMuted:       '#ffffff',
      onBorder:      '#000000',
      contrast:      '#b07d1f',
      contrastText: '#865f18',
      success:       '#0a7b28',
      danger:        '#c9302c',
      warning:       '#b07d1f',
      dangerText:    '#c02e2a',
      warningText:   '#865f18',
      info:          '#1e6fa8',
      purple:        '#6f42c1',
      shadow:        'rgba(0,0,0,0.12)',
    },
  },
  {
    id: 'dracula',
    name: 'Dracula',
    description: 'Popular Dracula community palette.',
    source: 'https://draculatheme.com/contribute',
    dark: {
      bgPrimary:     '#282a36',
      bgSecondary:   '#343746',
      bgTertiary:    '#44475a',
      border:        '#6272a4',
      textPrimary:   '#f8f8f2',
      textSecondary: '#bfbfbf',
      accent:        '#ff79c6',
      accentHover:   '#ff92d0',
      accentText:    '#ff93d1',
      onAccent:      '#000000',
      onAccentHover: '#000000',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#000000',
      onPurple:      '#000000',
      onMuted:       '#000000',
      onBorder:      '#ffffff',
      contrast:      '#bd93f9',
      contrastText: '#c9a7fa',
      success:       '#50fa7b',
      danger:        '#ff5555',
      warning:       '#f1fa8c',
      dangerText:    '#ff9a9a',
      warningText:   '#f1fa8c',
      info:          '#8be9fd',
      purple:        '#bd93f9',
      shadow:        'rgba(0,0,0,0.55)',
    },
    light: {
      bgPrimary:     '#f8f8f2',
      bgSecondary:   '#eeeeec',
      bgTertiary:    '#e0e0da',
      border:        '#c9c9c0',
      textPrimary:   '#282a36',
      textSecondary: '#536290',
      accent:        '#d6336c',
      accentHover:   '#bd255a',
      accentText:    '#ba2559',
      onAccent:      '#ffffff',
      onAccentHover: '#ffffff',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#ffffff',
      onPurple:      '#ffffff',
      onMuted:       '#ffffff',
      onBorder:      '#000000',
      contrast:      '#7048e8',
      contrastText: '#6a40e7',
      success:       '#2b8a3e',
      danger:        '#c92a2a',
      warning:       '#b08900',
      dangerText:    '#bd2828',
      warningText:   '#7b6000',
      info:          '#1c7ed6',
      purple:        '#6741d9',
      shadow:        'rgba(0,0,0,0.12)',
    },
  },
  {
    id: 'solarized',
    name: 'Solarized',
    description: "Ethan Schoonover's Solarized — precision colours for machines and people.",
    source: 'https://colorshexa.com/palette/solarized-palette',
    dark: {
      bgPrimary:     '#002b36',
      bgSecondary:   '#073642',
      bgTertiary:    '#0a4453',
      border:        '#586e75',
      textPrimary:   '#aeb8b8',
      textSecondary: '#9bacb2',
      accent:        '#268bd2',
      accentHover:   '#2aa198',
      accentText:    '#66b0e3',
      onAccent:      '#000000',
      onAccentHover: '#000000',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#ffffff',
      onPurple:      '#000000',
      onMuted:       '#000000',
      onBorder:      '#ffffff',
      contrast:      '#b58900',
      contrastText: '#d4a100',
      success:       '#859900',
      danger:        '#dc322f',
      warning:       '#b58900',
      dangerText:    '#ec8f8d',
      warningText:   '#d4a100',
      info:          '#268bd2',
      purple:        '#6c71c4',
      shadow:        'rgba(0,0,0,0.55)',
    },
    light: {
      bgPrimary:     '#fdf6e3',
      bgSecondary:   '#eee8d5',
      bgTertiary:    '#d9d2bf',
      border:        '#93a1a1',
      textPrimary:   '#073642',
      textSecondary: '#4d5d63',
      accent:        '#268bd2',
      accentHover:   '#1d70ad',
      accentText:    '#1a5f90',
      onAccent:      '#000000',
      onAccentHover: '#ffffff',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#ffffff',
      onPurple:      '#000000',
      onMuted:       '#ffffff',
      onBorder:      '#000000',
      contrast:      '#b58900',
      contrastText: '#735700',
      success:       '#859900',
      danger:        '#dc322f',
      warning:       '#b58900',
      dangerText:    '#b0201e',
      warningText:   '#735700',
      info:          '#268bd2',
      purple:        '#6c71c4',
      shadow:        'rgba(0,0,0,0.12)',
    },
  },
  {
    id: 'nord',
    name: 'Nord',
    description: 'Arctic, north-bluish clean and elegant colour palette.',
    source: 'https://colorshexa.com/palette/nord-palette',
    dark: {
      bgPrimary:     '#2e3440',
      bgSecondary:   '#3b4252',
      bgTertiary:    '#434c5e',
      border:        '#4c566a',
      textPrimary:   '#eceff4',
      textSecondary: '#d8dee9',
      accent:        '#88c0d0',
      accentHover:   '#8fbcbb',
      accentText:    '#8fc4d3',
      onAccent:      '#000000',
      onAccentHover: '#000000',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#000000',
      onPurple:      '#000000',
      onMuted:       '#000000',
      onBorder:      '#ffffff',
      contrast:      '#ebcb8b',
      contrastText: '#ebcb8b',
      success:       '#a3be8c',
      danger:        '#bf616a',
      warning:       '#ebcb8b',
      dangerText:    '#dfb0b4',
      warningText:   '#ebcb8b',
      info:          '#81a1c1',
      purple:        '#b48ead',
      shadow:        'rgba(0,0,0,0.55)',
    },
    light: {
      bgPrimary:     '#eceff4',
      bgSecondary:   '#e5e9f0',
      bgTertiary:    '#d8dee9',
      border:        '#b8c0ce',
      textPrimary:   '#2e3440',
      textSecondary: '#4c566a',
      accent:        '#5e81ac',
      accentHover:   '#4c6e95',
      accentText:    '#476489',
      onAccent:      '#000000',
      onAccentHover: '#ffffff',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#000000',
      onPurple:      '#000000',
      onMuted:       '#ffffff',
      onBorder:      '#000000',
      contrast:      '#d08770',
      contrastText: '#9a4b33',
      success:       '#5b8c3a',
      danger:        '#bf616a',
      warning:       '#b08900',
      dangerText:    '#a3424b',
      warningText:   '#795f00',
      info:          '#81a1c1',
      purple:        '#b48ead',
      shadow:        'rgba(0,0,0,0.12)',
    },
  },
  {
    id: 'monokai',
    name: 'Monokai',
    description: "Wimer Hazenberg's Monokai — the iconic Sublime Text palette.",
    source: 'https://colorshexa.com/palette/monokai-palette',
    dark: {
      bgPrimary:     '#272822',
      bgSecondary:   '#383830',
      bgTertiary:    '#49483e',
      border:        '#75715e',
      textPrimary:   '#f8f8f2',
      textSecondary: '#cfcfc2',
      accent:        '#f92672',
      accentHover:   '#ff4890',
      accentText:    '#fc97bb',
      onAccent:      '#000000',
      onAccentHover: '#000000',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#000000',
      onPurple:      '#000000',
      onMuted:       '#000000',
      onBorder:      '#ffffff',
      contrast:      '#a6e22e',
      contrastText: '#a6e22e',
      success:       '#a6e22e',
      danger:        '#f92672',
      warning:       '#fd971f',
      dangerText:    '#fc97bb',
      warningText:   '#fda134',
      info:          '#66d9ef',
      purple:        '#ae81ff',
      shadow:        'rgba(0,0,0,0.55)',
    },
    light: {
      bgPrimary:     '#fafaf5',
      bgSecondary:   '#ededeb',
      bgTertiary:    '#dddbcf',
      border:        '#b0ad9e',
      textPrimary:   '#272822',
      textSecondary: '#646050',
      accent:        '#d63384',
      accentHover:   '#b5256e',
      accentText:    '#b2246a',
      onAccent:      '#ffffff',
      onAccentHover: '#ffffff',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#ffffff',
      onPurple:      '#ffffff',
      onMuted:       '#ffffff',
      onBorder:      '#000000',
      contrast:      '#689822',
      contrastText: '#486a18',
      success:       '#689822',
      danger:        '#c02450',
      warning:       '#c6660a',
      dangerText:    '#b7224c',
      warningText:   '#954d08',
      info:          '#2a9ab4',
      purple:        '#7a4ddb',
      shadow:        'rgba(0,0,0,0.12)',
    },
  },
  {
    id: 'gruvbox',
    name: 'Gruvbox',
    description: 'Retro groove colour scheme — warm, earthy, high-contrast.',
    source: 'https://colorshexa.com/palette/gruvbox-palette',
    dark: {
      bgPrimary:     '#282828',
      bgSecondary:   '#3c3836',
      bgTertiary:    '#504945',
      border:        '#665c54',
      textPrimary:   '#ebdbb2',
      textSecondary: '#c2b8a9',
      accent:        '#fb4934',
      accentHover:   '#cc241d',
      accentText:    '#fda196',
      onAccent:      '#000000',
      onAccentHover: '#ffffff',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#000000',
      onPurple:      '#000000',
      onMuted:       '#000000',
      onBorder:      '#ffffff',
      contrast:      '#fabd2f',
      contrastText: '#fabd2f',
      success:       '#b8bb26',
      danger:        '#fb4934',
      warning:       '#fabd2f',
      dangerText:    '#fda196',
      warningText:   '#fabd2f',
      info:          '#83a598',
      purple:        '#d3869b',
      shadow:        'rgba(0,0,0,0.55)',
    },
    light: {
      bgPrimary:     '#fbf1c7',
      bgSecondary:   '#ebdbb2',
      bgTertiary:    '#d5c4a1',
      border:        '#bdae93',
      textPrimary:   '#3c3836',
      textSecondary: '#5a514a',
      accent:        '#9d0006',
      accentHover:   '#79111e',
      accentText:    '#9d0006',
      onAccent:      '#ffffff',
      onAccentHover: '#ffffff',
      onSuccess:     '#ffffff',
      onInfo:        '#ffffff',
      onWarning:     '#000000',
      onDanger:      '#ffffff',
      onPurple:      '#ffffff',
      onMuted:       '#ffffff',
      onBorder:      '#000000',
      contrast:      '#b57614',
      contrastText: '#724a0d',
      success:       '#79740e',
      danger:        '#9d0006',
      warning:       '#b57614',
      dangerText:    '#9d0006',
      warningText:   '#724a0d',
      info:          '#076678',
      purple:        '#8f3f71',
      shadow:        'rgba(0,0,0,0.12)',
    },
  },
  {
    id: 'one-dark',
    name: 'One Dark',
    description: 'Atom One Dark — balanced, signature editor palette.',
    source: 'https://colorshexa.com/palette/one-dark-palette',
    dark: {
      bgPrimary:     '#282c34',
      bgSecondary:   '#353b45',
      bgTertiary:    '#3e4451',
      border:        '#4b5263',
      textPrimary:   '#b9bec9',
      textSecondary: '#adb1b7',
      accent:        '#61afef',
      accentHover:   '#4e96d6',
      accentText:    '#70b7f1',
      onAccent:      '#000000',
      onAccentHover: '#000000',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#000000',
      onPurple:      '#000000',
      onMuted:       '#000000',
      onBorder:      '#ffffff',
      contrast:      '#e5c07b',
      contrastText: '#e5c07b',
      success:       '#98c379',
      danger:        '#e06c75',
      warning:       '#e5c07b',
      dangerText:    '#ea9ba1',
      warningText:   '#e5c07b',
      info:          '#56b6c2',
      purple:        '#c678dd',
      shadow:        'rgba(0,0,0,0.55)',
    },
    light: {
      bgPrimary:     '#fafafa',
      bgSecondary:   '#eaeaeb',
      bgTertiary:    '#d3d3d5',
      border:        '#a0a1a7',
      textPrimary:   '#383a42',
      textSecondary: '#595b65',
      accent:        '#4078f2',
      accentHover:   '#2e62cc',
      accentText:    '#0f4ed9',
      onAccent:      '#000000',
      onAccentHover: '#ffffff',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#000000',
      onPurple:      '#ffffff',
      onMuted:       '#ffffff',
      onBorder:      '#000000',
      contrast:      '#986801',
      contrastText: '#7b5401',
      success:       '#50a14f',
      danger:        '#e45649',
      warning:       '#c18401',
      dangerText:    '#af261a',
      warningText:   '#7b5401',
      info:          '#0184bc',
      purple:        '#a626a4',
      shadow:        'rgba(0,0,0,0.12)',
    },
  },
  {
    id: 'tokyo-night',
    name: 'Tokyo Night',
    description: "Clean, dark urban palette inspired by Tokyo's lights.",
    source: 'https://colorshexa.com/palette/tokyo-night-palette',
    dark: {
      bgPrimary:     '#1a1b26',
      bgSecondary:   '#24283b',
      bgTertiary:    '#2f344d',
      border:        '#414868',
      textPrimary:   '#c0caf5',
      textSecondary: '#a9b1d6',
      accent:        '#7aa2f7',
      accentHover:   '#6a91e6',
      accentText:    '#7aa2f7',
      onAccent:      '#000000',
      onAccentHover: '#000000',
      onSuccess:     '#000000',
      onInfo:        '#000000',
      onWarning:     '#000000',
      onDanger:      '#000000',
      onPurple:      '#000000',
      onMuted:       '#000000',
      onBorder:      '#ffffff',
      contrast:      '#e0af68',
      contrastText: '#e0af68',
      success:       '#9ece6a',
      danger:        '#f7768e',
      warning:       '#e0af68',
      dangerText:    '#f7768e',
      warningText:   '#e0af68',
      info:          '#7dcfff',
      purple:        '#bb9af7',
      shadow:        'rgba(0,0,0,0.55)',
    },
    light: {
      bgPrimary:     '#e6e7ed',
      bgSecondary:   '#d5d6db',
      bgTertiary:    '#c4c7d0',
      border:        '#989caf',
      textPrimary:   '#343b58',
      textSecondary: '#4f5365',
      accent:        '#34548a',
      accentHover:   '#2a4471',
      accentText:    '#345389',
      onAccent:      '#ffffff',
      onAccentHover: '#ffffff',
      onSuccess:     '#ffffff',
      onInfo:        '#ffffff',
      onWarning:     '#ffffff',
      onDanger:      '#ffffff',
      onPurple:      '#ffffff',
      onMuted:       '#ffffff',
      onBorder:      '#000000',
      contrast:      '#8f5e15',
      contrastText: '#734b11',
      success:       '#485e30',
      danger:        '#8c4351',
      warning:       '#8f5e15',
      dangerText:    '#823e4b',
      warningText:   '#734b11',
      info:          '#2a6194',
      purple:        '#5a3e8e',
      shadow:        'rgba(0,0,0,0.12)',
    },
  },
];

export const DEFAULT_PALETTE_ID = 'darcula';

/** Lookup by id, returning `undefined` if not found. */
export function findPalette(id: string): Palette | undefined {
  return PALETTES.find((p) => p.id === id);
}
