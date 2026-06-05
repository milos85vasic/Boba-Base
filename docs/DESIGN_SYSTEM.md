# Design System — Runtime Palette

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

The dashboard, admin surfaces, and every embedded app share a single
runtime-switchable colour system. Palettes are applied to
`document.documentElement` as CSS custom properties by
`ThemeService`, so every bit of UI that reads `var(--color-*)` picks
up the change instantly.

<!-- screenshot: dashboard-darcula-dark.png — Darcula dark variant (default) -->
<!-- screenshot: dashboard-darcula-light.png — Darcula light variant -->
<!-- screenshot: picker-open.png — Theme picker dropdown open -->

## Why Darcula + `#9d001e`?

The default palette is **Darcula** (the JetBrains IDE greys) paired
with a blood-red accent extracted directly from
`assets/Logo.jpeg` — the qBittorrent logo. The accent is `#9d001e`.
A warm gold contrast (`#d9a441`) is the secondary accent for badges
and freeleech pills. This pairing keeps the UI distinctly on-brand
while staying neutral enough to remain readable under long sessions.

## Catalogue

Eight palettes ship out of the box. Every palette supplies a **dark**
and a **light** variant. Sources are linked next to each palette name.

### Darcula

JetBrains Darcula greys — paired with the qBittorrent logo's blood-red.
Source: <https://colorshexa.com/palette/darcula-palette>

| Token | Dark | Light |
|---|---|---|
| bgPrimary | `#2b2b2b` | `#ffffff` |
| bgSecondary | `#3c3f41` | `#f2f2f2` |
| bgTertiary | `#4e5254` | `#e4e4e4` |
| border | `#555555` | `#c9c9c9` |
| textPrimary | `#a9b7c6` | `#1c1c1c` |
| textSecondary | `#808080` | `#555555` |
| accent | `#9d001e` | `#9d001e` |
| accentHover | `#c4002a` | `#7d0017` |
| contrast | `#d9a441` | `#b07d1f` |
| success | `#6a8759` | `#0a7b28` |
| danger | `#cc7832` | `#c9302c` |
| warning | `#d9a441` | `#b07d1f` |
| info | `#6897bb` | `#1e6fa8` |
| purple | `#9876aa` | `#6f42c1` |
| shadow | `rgba(0,0,0,0.55)` | `rgba(0,0,0,0.12)` |

### Dracula

Source: <https://draculatheme.com/contribute>

| Token | Dark | Light |
|---|---|---|
| bgPrimary | `#282a36` | `#f8f8f2` |
| bgSecondary | `#343746` | `#eeeeec` |
| bgTertiary | `#44475a` | `#e0e0da` |
| border | `#6272a4` | `#c9c9c0` |
| textPrimary | `#f8f8f2` | `#282a36` |
| textSecondary | `#bfbfbf` | `#6272a4` |
| accent | `#ff79c6` | `#d6336c` |
| accentHover | `#ff92d0` | `#bd255a` |
| contrast | `#bd93f9` | `#7048e8` |
| success | `#50fa7b` | `#2b8a3e` |
| danger | `#ff5555` | `#c92a2a` |
| warning | `#f1fa8c` | `#b08900` |
| info | `#8be9fd` | `#1c7ed6` |
| purple | `#bd93f9` | `#6741d9` |
| shadow | `rgba(0,0,0,0.55)` | `rgba(0,0,0,0.12)` |

### Solarized

Ethan Schoonover's Solarized — precision colours for machines and people.
Source: <https://colorshexa.com/palette/solarized-palette>

| Token | Dark | Light |
|---|---|---|
| bgPrimary | `#002b36` | `#fdf6e3` |
| bgSecondary | `#073642` | `#eee8d5` |
| bgTertiary | `#0a4453` | `#d9d2bf` |
| border | `#586e75` | `#93a1a1` |
| textPrimary | `#93a1a1` | `#073642` |
| textSecondary | `#657b83` | `#657b83` |
| accent | `#268bd2` | `#268bd2` |
| accentHover | `#2aa198` | `#1d70ad` |
| contrast | `#b58900` | `#b58900` |
| success | `#859900` | `#859900` |
| danger | `#dc322f` | `#dc322f` |
| warning | `#b58900` | `#b58900` |
| info | `#268bd2` | `#268bd2` |
| purple | `#6c71c4` | `#6c71c4` |
| shadow | `rgba(0,0,0,0.55)` | `rgba(0,0,0,0.12)` |

### Nord

Arctic, north-bluish clean and elegant.
Source: <https://colorshexa.com/palette/nord-palette>

| Token | Dark | Light |
|---|---|---|
| bgPrimary | `#2e3440` | `#eceff4` |
| bgSecondary | `#3b4252` | `#e5e9f0` |
| bgTertiary | `#434c5e` | `#d8dee9` |
| border | `#4c566a` | `#b8c0ce` |
| textPrimary | `#eceff4` | `#2e3440` |
| textSecondary | `#d8dee9` | `#4c566a` |
| accent | `#88c0d0` | `#5e81ac` |
| accentHover | `#8fbcbb` | `#4c6e95` |
| contrast | `#ebcb8b` | `#d08770` |
| success | `#a3be8c` | `#5b8c3a` |
| danger | `#bf616a` | `#bf616a` |
| warning | `#ebcb8b` | `#b08900` |
| info | `#81a1c1` | `#81a1c1` |
| purple | `#b48ead` | `#b48ead` |
| shadow | `rgba(0,0,0,0.55)` | `rgba(0,0,0,0.12)` |

### Monokai

Wimer Hazenberg's Monokai — the iconic Sublime Text palette.
Source: <https://colorshexa.com/palette/monokai-palette>

| Token | Dark | Light |
|---|---|---|
| bgPrimary | `#272822` | `#fafaf5` |
| bgSecondary | `#383830` | `#ededeb` |
| bgTertiary | `#49483e` | `#dddbcf` |
| border | `#75715e` | `#b0ad9e` |
| textPrimary | `#f8f8f2` | `#272822` |
| textSecondary | `#cfcfc2` | `#75715e` |
| accent | `#f92672` | `#d63384` |
| accentHover | `#ff4890` | `#b5256e` |
| contrast | `#a6e22e` | `#689822` |
| success | `#a6e22e` | `#689822` |
| danger | `#f92672` | `#c02450` |
| warning | `#fd971f` | `#c6660a` |
| info | `#66d9ef` | `#2a9ab4` |
| purple | `#ae81ff` | `#7a4ddb` |
| shadow | `rgba(0,0,0,0.55)` | `rgba(0,0,0,0.12)` |

### Gruvbox

Retro groove colour scheme — warm, earthy, high-contrast.
Source: <https://colorshexa.com/palette/gruvbox-palette>

| Token | Dark | Light |
|---|---|---|
| bgPrimary | `#282828` | `#fbf1c7` |
| bgSecondary | `#3c3836` | `#ebdbb2` |
| bgTertiary | `#504945` | `#d5c4a1` |
| border | `#665c54` | `#bdae93` |
| textPrimary | `#ebdbb2` | `#3c3836` |
| textSecondary | `#a89984` | `#665c54` |
| accent | `#fb4934` | `#9d0006` |
| accentHover | `#cc241d` | `#79111e` |
| contrast | `#fabd2f` | `#b57614` |
| success | `#b8bb26` | `#79740e` |
| danger | `#fb4934` | `#9d0006` |
| warning | `#fabd2f` | `#b57614` |
| info | `#83a598` | `#076678` |
| purple | `#d3869b` | `#8f3f71` |
| shadow | `rgba(0,0,0,0.55)` | `rgba(0,0,0,0.12)` |

### One Dark

Atom One Dark — balanced, signature editor palette.
Source: <https://colorshexa.com/palette/one-dark-palette>

| Token | Dark | Light |
|---|---|---|
| bgPrimary | `#282c34` | `#fafafa` |
| bgSecondary | `#353b45` | `#eaeaeb` |
| bgTertiary | `#3e4451` | `#d3d3d5` |
| border | `#4b5263` | `#a0a1a7` |
| textPrimary | `#abb2bf` | `#383a42` |
| textSecondary | `#7f848e` | `#696c77` |
| accent | `#61afef` | `#4078f2` |
| accentHover | `#4e96d6` | `#2e62cc` |
| contrast | `#e5c07b` | `#986801` |
| success | `#98c379` | `#50a14f` |
| danger | `#e06c75` | `#e45649` |
| warning | `#e5c07b` | `#c18401` |
| info | `#56b6c2` | `#0184bc` |
| purple | `#c678dd` | `#a626a4` |
| shadow | `rgba(0,0,0,0.55)` | `rgba(0,0,0,0.12)` |

### Tokyo Night

Clean, dark urban palette inspired by Tokyo's lights.
Source: <https://colorshexa.com/palette/tokyo-night-palette>

| Token | Dark | Light |
|---|---|---|
| bgPrimary | `#1a1b26` | `#e6e7ed` |
| bgSecondary | `#24283b` | `#d5d6db` |
| bgTertiary | `#2f344d` | `#c4c7d0` |
| border | `#414868` | `#989caf` |
| textPrimary | `#c0caf5` | `#343b58` |
| textSecondary | `#a9b1d6` | `#565a6e` |
| accent | `#7aa2f7` | `#34548a` |
| accentHover | `#6a91e6` | `#2a4471` |
| contrast | `#e0af68` | `#8f5e15` |
| success | `#9ece6a` | `#485e30` |
| danger | `#f7768e` | `#8c4351` |
| warning | `#e0af68` | `#8f5e15` |
| info | `#7dcfff` | `#2a6194` |
| purple | `#bb9af7` | `#5a3e8e` |
| shadow | `rgba(0,0,0,0.55)` | `rgba(0,0,0,0.12)` |

## CSS variables

The 15 tokens surface as CSS custom properties on `<html>`. SCSS and
component templates use these via `var(--color-*)`:

| Token key | CSS variable |
|---|---|
| bgPrimary | `--color-bg-primary` |
| bgSecondary | `--color-bg-secondary` |
| bgTertiary | `--color-bg-tertiary` |
| border | `--color-border` |
| textPrimary | `--color-text-primary` |
| textSecondary | `--color-text-secondary` |
| accent | `--color-accent` |
| accentHover | `--color-accent-hover` |
| contrast | `--color-contrast` |
| success | `--color-success` |
| danger | `--color-danger` |
| warning | `--color-warning` |
| info | `--color-info` |
| purple | `--color-purple` |
| shadow | `--color-shadow` |

`frontend/src/styles.scss` declares Darcula-dark fallbacks on `:root`
so the page is styled even before `ThemeService` runs — no flash of
unstyled content (FOUC) on first paint.

## ThemeService API

Imported from `frontend/src/app/services/theme.service.ts`.

| Member | Kind | Description |
|---|---|---|
| `palette` | `Signal<Palette>` | Current palette object (read-only). |
| `mode` | `Signal<PaletteMode>` | `'light'` or `'dark'` (read-only). |
| `currentTokens` | `Signal<PaletteTokens>` | Active token set; switches with mode. |
| `availablePalettes` | `readonly Palette[]` | Full catalogue. |
| `paletteIds` | `readonly string[]` | Id list (convenience). |
| `setPalette(id)` | method | Switch to a palette. No-op for unknown ids. |
| `setMode(mode)` | method | Force light/dark. Marks the choice as sticky. |
| `toggleMode()` | method | Flip light ↔ dark. |
| `isModeUserChosen()` | method | `true` if user has explicitly chosen mode. |

### Storage key

```json
// key: "qbit.theme"
{
  "paletteId": "darcula",
  "mode": "dark",
  "modeIsUserChosen": true
}
```

- When the store is empty, the service defaults to `DEFAULT_PALETTE_ID`
  (`"darcula"`) and derives `mode` from
  `window.matchMedia('(prefers-color-scheme: dark)')`.
- When the stored id no longer exists in the catalogue, the service
  falls back to the default AND writes the correction back to storage.
- While `modeIsUserChosen === false`, the service listens to
  `prefers-color-scheme` changes and updates `mode` to match. Once the
  user picks a mode explicitly (`setMode` / `toggleMode` / picker), the
  choice becomes sticky.

### Side effects per change

On every `setPalette` / `setMode` / `toggleMode`, the service:

1. Writes every one of the 15 tokens to
   `document.documentElement.style.setProperty(--color-*, ...)`.
2. Sets `color-scheme` on the documentElement (for native UI controls).
3. Sets `data-palette` and `data-mode` attributes on `<html>`.
4. Persists the full state to `localStorage['qbit.theme']`.

These are observable, which is how the tests verify behaviour without
false positives — see `frontend/src/app/services/theme.service.spec.ts`
and `tests/e2e/test_theme_runtime.py`.

## Theme picker UI

`frontend/src/app/components/theme-picker/` ships the corner widget
used in the dashboard header. It is a standalone Angular component; any
other app can drop `<app-theme-picker>` into its template. The picker
renders:

- a light/dark mode toggle button,
- a dropdown listing every palette,
- four colour swatches per palette (accent, contrast, bg, text),
- an active-state marker (`.active` + `aria-checked="true"`) on the
  current palette.

## Adding a new palette

1. Edit `frontend/src/app/models/palette.model.ts` and add an entry to
   `PALETTES`. Provide both `light` and `dark` variants with every one
   of the 15 tokens.
2. Make sure each token is a valid CSS colour (`#RRGGBB` or
   `rgba(r, g, b, a)`).
3. Run the catalogue parametric validator:

   ```bash
   python3 -m pytest tests/unit/test_palette_catalog.py -v --no-cov
   ```

4. Run the wiring guard + frontend specs:

   ```bash
   python3 -m pytest tests/unit/test_theme_wiring.py -v --no-cov
   npx --prefix frontend ng test --watch=false
   ```

5. Rebuild and restart the merge service (see
   CLAUDE.md's **REBUILD AND REBOOT** constraint). If Playwright is
   installed, run:

   ```bash
   python3 -m pytest tests/e2e/test_theme_runtime.py -v --no-cov
   ```

The e2e test will loudly fail (not skip) when the served bundle does
not include the new palette, which is the project's "no false
positives" guarantee.

## Files

- `frontend/src/app/models/palette.model.ts` — catalogue + types
- `frontend/src/app/services/theme.service.ts` — runtime controller
- `frontend/src/app/components/theme-picker/` — picker component
- `frontend/src/styles.scss` — global CSS variable fallbacks
- `frontend/src/app/components/dashboard/dashboard.component.scss` —
  dashboard stylesheet using `var(--color-*)`
- `frontend/src/app/components/tracker-stat-dialog/tracker-stat-dialog.component.scss`
  — dialog stylesheet using `var(--color-*)`
- `tests/unit/test_palette_catalog.py` — parametric catalogue validator
- `tests/unit/test_theme_wiring.py` — wiring integration guard
- `tests/e2e/test_theme_runtime.py` — Playwright runtime verification
