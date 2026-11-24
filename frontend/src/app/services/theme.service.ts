import { Injectable, computed, inject, signal } from '@angular/core';
import {
  DEFAULT_PALETTE_ID,
  Palette,
  PALETTES,
  PALETTE_TOKEN_KEYS,
  PaletteMode,
  PaletteTokens,
  TOKEN_CSS_VAR,
  findPalette,
} from '../models/palette.model';
import { ApiTokenService } from './api-token.service';

/**
 * localStorage shape for the persisted theme choice.
 */
export interface StoredTheme {
  paletteId: string;
  mode: PaletteMode;
  /**
   * `true` if the user has explicitly picked `mode` via the UI. When
   * `false`, the service follows `prefers-color-scheme` changes. When
   * `true`, system-preference changes are ignored (the user wins).
   */
  modeIsUserChosen: boolean;
}

const STORAGE_KEY = 'qbit.theme';

/** Shared-state REST endpoints (Phase A of CROSS_APP_THEME_PLAN.md). */
const THEME_ENDPOINT = '/api/v1/theme';
const THEME_STREAM_ENDPOINT = '/api/v1/theme/stream';

/** PUTs are debounced so rapid toggles collapse into the last value. */
const PUT_DEBOUNCE_MS = 200;

interface ThemeApiPayload {
  paletteId: string;
  mode: PaletteMode;
  updatedAt?: string;
}

@Injectable({ providedIn: 'root' })
export class ThemeService {
  /** Full palette catalogue — exposed for the picker. */
  readonly availablePalettes: readonly Palette[];

  /** Re-exported convenience for consumers that want to read the id list. */
  readonly paletteIds: readonly string[];

  private readonly _palette = signal<Palette>(findPalette(DEFAULT_PALETTE_ID)!);
  private readonly _mode = signal<PaletteMode>('dark');
  private _modeIsUserChosen = false;

  readonly palette = this._palette.asReadonly();
  readonly mode = this._mode.asReadonly();

  /** Active token set (derived from palette + mode). */
  readonly currentTokens = computed<PaletteTokens>(() => {
    const p = this._palette();
    return this._mode() === 'dark' ? p.dark : p.light;
  });

  private readonly apiToken = inject(ApiTokenService);
  private readonly documentRef: Document | null;
  private readonly storageRef: Storage | null;
  private readonly mediaQuery: MediaQueryList | null;
  private readonly mediaListener: ((e: MediaQueryListEvent) => void) | null;

  // Cross-app sync plumbing (Phase B).
  private _eventSource: EventSource | null = null;
  private _putTimer: ReturnType<typeof setTimeout> | null = null;
  private _lastUpdatedAt: string | null = null;
  /**
   * Set to true while we are adopting a server-originated update, so
   * the helper `persist()` inside setPalette/setMode doesn't kick off
   * another PUT and cause a loop.
   */
  private _suppressPut = false;

  constructor() {
    this.availablePalettes = PALETTES;
    this.paletteIds = PALETTES.map((p) => p.id);
    this.documentRef = typeof document !== 'undefined' ? document : null;
    this.storageRef = this.safeLocalStorage();
    this.mediaQuery = this.resolveMediaQuery();

    const initial = this.resolveInitialState();
    this._palette.set(initial.palette);
    this._mode.set(initial.mode);
    this._modeIsUserChosen = initial.modeIsUserChosen;

    // Persist in case we fell back to defaults (corrects stale ids).
    this.persist();
    this.apply();

    if (this.mediaQuery) {
      this.mediaListener = (event: MediaQueryListEvent) => {
        if (this._modeIsUserChosen) return;
        this._mode.set(event.matches ? 'dark' : 'light');
        this.persist();
        this.apply();
        this.scheduleServerSync();
      };
      // Prefer modern API; fall back to deprecated addListener for jsdom.
      if (typeof this.mediaQuery.addEventListener === 'function') {
        this.mediaQuery.addEventListener('change', this.mediaListener);
      } else if (typeof (this.mediaQuery as MediaQueryList).addListener === 'function') {
        (this.mediaQuery as MediaQueryList).addListener(this.mediaListener);
      }
    } else {
      this.mediaListener = null;
    }

    // Pull shared state from the backend if localStorage was empty.
    this.bootstrapFromServer(initial.hadStoredState);
    // Subscribe to live updates so palette swaps in other tabs /
    // apps propagate here without a manual refresh.
    this.openEventStream();
  }

  /** Swap to a different palette by id. No-op if id is unknown. */
  setPalette(id: string): void {
    const next = findPalette(id);
    if (!next) return;
    if (next.id === this._palette().id) return;
    this._palette.set(next);
    this.persist();
    this.apply();
    this.scheduleServerSync();
  }

  /** Set explicit light/dark mode (marks the user choice as sticky). */
  setMode(mode: PaletteMode): void {
    if (mode !== 'light' && mode !== 'dark') return;
    this._mode.set(mode);
    this._modeIsUserChosen = true;
    this.persist();
    this.apply();
    this.scheduleServerSync();
  }

  /** Flip between light and dark. */
  toggleMode(): void {
    this.setMode(this._mode() === 'dark' ? 'light' : 'dark');
  }

  /** Mostly for tests: whether the user has chosen a mode explicitly. */
  isModeUserChosen(): boolean {
    return this._modeIsUserChosen;
  }

  /** For tests and cleanup — remove any listeners we installed. */
  dispose(): void {
    if (this.mediaQuery && this.mediaListener) {
      if (typeof this.mediaQuery.removeEventListener === 'function') {
        this.mediaQuery.removeEventListener('change', this.mediaListener);
      } else if (typeof (this.mediaQuery as MediaQueryList).removeListener === 'function') {
        (this.mediaQuery as MediaQueryList).removeListener(this.mediaListener);
      }
    }
    if (this._eventSource) {
      try { this._eventSource.close(); } catch { /* swallow */ }
      this._eventSource = null;
    }
    if (this._putTimer) {
      clearTimeout(this._putTimer);
      this._putTimer = null;
    }
  }

  // ----------------------------------------------------------------- internals

  private safeLocalStorage(): Storage | null {
    try {
      if (typeof localStorage === 'undefined') return null;
      // Touch it once to catch sandboxed throws.
      localStorage.getItem(STORAGE_KEY);
      return localStorage;
    } catch {
      return null;
    }
  }

  private resolveMediaQuery(): MediaQueryList | null {
    try {
      if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
        return null;
      }
      return window.matchMedia('(prefers-color-scheme: dark)');
    } catch {
      return null;
    }
  }

  private resolveInitialState(): {
    palette: Palette;
    mode: PaletteMode;
    modeIsUserChosen: boolean;
    hadStoredState: boolean;
  } {
    const stored = this.readStored();
    if (stored) {
      const palette = findPalette(stored.paletteId) ?? findPalette(DEFAULT_PALETTE_ID)!;
      const mode: PaletteMode = stored.mode === 'light' || stored.mode === 'dark' ? stored.mode : 'dark';
      return {
        palette,
        mode,
        modeIsUserChosen: !!stored.modeIsUserChosen,
        hadStoredState: true,
      };
    }
    // No persisted theme — respect system preference.
    const systemDark = this.mediaQuery ? this.mediaQuery.matches : true;
    return {
      palette: findPalette(DEFAULT_PALETTE_ID)!,
      mode: systemDark ? 'dark' : 'light',
      modeIsUserChosen: false,
      hadStoredState: false,
    };
  }

  private readStored(): StoredTheme | null {
    if (!this.storageRef) return null;
    const raw = this.storageRef.getItem(STORAGE_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as Partial<StoredTheme>;
      if (!parsed || typeof parsed !== 'object' || typeof parsed.paletteId !== 'string') {
        return null;
      }
      return {
        paletteId: parsed.paletteId,
        mode: (parsed.mode === 'light' ? 'light' : 'dark'),
        modeIsUserChosen: !!parsed.modeIsUserChosen,
      };
    } catch {
      return null;
    }
  }

  private persist(): void {
    if (!this.storageRef) return;
    const payload: StoredTheme = {
      paletteId: this._palette().id,
      mode: this._mode(),
      modeIsUserChosen: this._modeIsUserChosen,
    };
    try {
      this.storageRef.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch {
      /* storage full or sandboxed — swallow */
    }
  }

  private apply(): void {
    const doc = this.documentRef;
    if (!doc || !doc.documentElement) return;
    const root = doc.documentElement;
    const tokens = this.currentTokens();
    for (const key of PALETTE_TOKEN_KEYS) {
      const varName = TOKEN_CSS_VAR[key];
      root.style.setProperty(varName, tokens[key]);
    }
    root.style.setProperty('color-scheme', this._mode());
    root.setAttribute('data-palette', this._palette().id);
    root.setAttribute('data-mode', this._mode());
  }

  // ----------------------------------------------------- Phase B: sync

  /**
   * Pull the server-side theme when we have no persisted choice yet.
   * When the browser already has a local state we keep ours and let
   * setPalette/setMode push it to the server.
   */
  private bootstrapFromServer(hadStoredState: boolean): void {
    if (hadStoredState) return;
    if (typeof fetch !== 'function') return;
    try {
      fetch(THEME_ENDPOINT, { credentials: 'omit' })
        .then((r) => (r && r.ok ? r.json() : null))
        .then((payload: ThemeApiPayload | null) => this.adoptServerState(payload))
        .catch(() => { /* offline — keep defaults */ });
    } catch {
      /* fetch threw synchronously on this environment */
    }
  }

  /**
   * Open a persistent EventSource to the theme-stream endpoint so we
   * react to palette changes from other tabs / the qBittorrent WebUI.
   */
  private openEventStream(): void {
    if (typeof EventSource !== 'function') return;
    try {
      const es = new EventSource(THEME_STREAM_ENDPOINT);
      this._eventSource = es;
      es.addEventListener('theme', (ev) => {
        try {
          const payload = JSON.parse((ev as MessageEvent).data) as ThemeApiPayload;
          this.adoptServerState(payload);
        } catch {
          /* ignore malformed event */
        }
      });
    } catch {
      this._eventSource = null;
    }
  }

  private adoptServerState(state: ThemeApiPayload | null): void {
    if (!state || typeof state.paletteId !== 'string') return;
    if (state.mode !== 'light' && state.mode !== 'dark') return;
    const palette = findPalette(state.paletteId);
    if (!palette) return;

    // De-dupe by updatedAt to avoid re-applying the echo of our own PUT.
    if (state.updatedAt && this._lastUpdatedAt && state.updatedAt === this._lastUpdatedAt) {
      return;
    }
    this._lastUpdatedAt = state.updatedAt ?? this._lastUpdatedAt;

    const changed = palette.id !== this._palette().id || state.mode !== this._mode();
    if (!changed) return;

    this._suppressPut = true;
    try {
      this._palette.set(palette);
      this._mode.set(state.mode);
      this.persist();
      this.apply();
    } finally {
      this._suppressPut = false;
    }
  }

  private scheduleServerSync(): void {
    if (this._suppressPut) return;
    if (typeof fetch !== 'function') return;
    if (this._putTimer) {
      clearTimeout(this._putTimer);
    }
    this._putTimer = setTimeout(() => {
      this._putTimer = null;
      this.putSharedState();
    }, PUT_DEBOUNCE_MS);
  }

  private putSharedState(): void {
    const body = JSON.stringify({
      paletteId: this._palette().id,
      mode: this._mode(),
    });
    const headers: Record<string, string> = { 'content-type': 'application/json' };
    const token = this.apiToken.token();
    if (token) {
      headers['X-Boba-Token'] = token;
    }
    try {
      fetch(THEME_ENDPOINT, {
        method: 'PUT',
        headers,
        body,
        credentials: 'omit',
      })
        .then((r) => (r && r.ok ? r.json() : null))
        .then((payload: ThemeApiPayload | null) => {
          if (payload && payload.updatedAt) {
            this._lastUpdatedAt = payload.updatedAt;
          }
        })
        .catch(() => { /* offline — local state still applied */ });
    } catch {
      /* fetch threw synchronously — nothing to do */
    }
  }
}
