import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TestBed, ComponentFixture } from '@angular/core/testing';
import { TrackerStatDialogComponent } from './tracker-stat-dialog.component';
import type { TrackerSearchStat } from '../../models/search.model';

function makeStat(over: Partial<TrackerSearchStat> = {}): TrackerSearchStat {
  return {
    name: 'rutracker',
    tracker_url: 'https://rutracker.org',
    status: 'success',
    results_count: 42,
    started_at: '2026-04-19T12:00:00Z',
    completed_at: '2026-04-19T12:00:01Z',
    duration_ms: 1000,
    error: null,
    error_type: null,
    authenticated: true,
    credentials_configured: true,
    attempt: 1,
    http_status: 200,
    category: 'all',
    query: 'ubuntu',
    notes: {},
    ...over,
  };
}

describe('TrackerStatDialogComponent', () => {
  let fx: ComponentFixture<TrackerStatDialogComponent>;
  let cmp: TrackerStatDialogComponent;

  const originalClipboard = (globalThis as any).navigator?.clipboard;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TrackerStatDialogComponent],
    }).compileComponents();
    fx = TestBed.createComponent(TrackerStatDialogComponent);
    cmp = fx.componentInstance;
    fx.detectChanges();
  });

  afterEach(() => {
    // Restore clipboard so we don't leak a navigator object missing prototype
    // getters (e.g. userAgent) to later tests in the same worker.
    try {
      Object.defineProperty(globalThis.navigator, 'clipboard', {
        value: originalClipboard,
        configurable: true,
        writable: true,
      });
    } catch { /* ignore */ }
  });

  it('is hidden by default', () => {
    expect(cmp.visible()).toBe(false);
    expect(cmp.stat()).toBeNull();
    const el = (fx.nativeElement as HTMLElement).querySelector('[data-testid="tracker-stat-dialog"]');
    expect(el).toBeNull();
  });

  it('open(stat) shows the dialog and exposes the stat', () => {
    const stat = makeStat();
    cmp.open(stat);
    fx.detectChanges();
    expect(cmp.visible()).toBe(true);
    expect(cmp.stat()).toEqual(stat);
    const el = (fx.nativeElement as HTMLElement).querySelector('[data-testid="tracker-stat-dialog"]');
    expect(el).toBeTruthy();
  });

  it('renders every identity/timing/result/query field', () => {
    cmp.open(makeStat({ name: 'kinozal', query: 'inception', category: 'movies', http_status: 302 }));
    fx.detectChanges();
    const text = (fx.nativeElement as HTMLElement).textContent || '';
    expect(text).toContain('kinozal');
    expect(text).toContain('inception');
    expect(text).toContain('movies');
    expect(text).toContain('302');
    expect(text).toContain('authenticated');
  });

  it('renders authentication and credential state as two DISTINCT facts', () => {
    // BOB-173: the live defect — credentials configured, login refused by a
    // CAPTCHA wall, no session. The dialog must NOT read as authenticated.
    cmp.open(makeStat({
      name: 'nnmclub',
      status: 'error',
      error_type: 'upstream_captcha',
      authenticated: false,
      credentials_configured: true,
    }));
    fx.detectChanges();
    const root = fx.nativeElement as HTMLElement;
    const auth = root.querySelector('[data-testid="stat-authenticated"]');
    const creds = root.querySelector('[data-testid="stat-credentials-configured"]');
    expect(auth?.textContent).toContain('no');
    expect(auth?.textContent).not.toContain('yes');
    expect(creds?.textContent).toContain('configured');
    expect(creds?.textContent).not.toContain('not configured');
  });

  it('shows the error section only when error is present', () => {
    cmp.open(makeStat({ status: 'error', error: 'boom', error_type: 'RuntimeError' }));
    fx.detectChanges();
    const errEl = (fx.nativeElement as HTMLElement).querySelector('[data-testid="error-section"]');
    expect(errEl).toBeTruthy();
    expect(errEl?.textContent).toContain('RuntimeError');
    expect(errEl?.textContent).toContain('boom');
  });

  it('hides the error section on success', () => {
    cmp.open(makeStat({ status: 'success', error: null, error_type: null }));
    fx.detectChanges();
    const errEl = (fx.nativeElement as HTMLElement).querySelector('[data-testid="error-section"]');
    expect(errEl).toBeNull();
  });

  it('renders raw JSON block with all fields', () => {
    const stat = makeStat({ notes: { stage: 'login' } });
    cmp.open(stat);
    fx.detectChanges();
    const pre = (fx.nativeElement as HTMLElement).querySelector('[data-testid="raw-json"]');
    const json = JSON.parse(pre?.textContent || '');
    expect(json.name).toBe('rutracker');
    expect(json.notes).toEqual({ stage: 'login' });
  });

  it('close() hides the dialog', () => {
    cmp.open(makeStat());
    fx.detectChanges();
    cmp.close();
    fx.detectChanges();
    expect(cmp.visible()).toBe(false);
    const el = (fx.nativeElement as HTMLElement).querySelector('[data-testid="tracker-stat-dialog"]');
    expect(el).toBeNull();
  });

  it('backdrop click closes the dialog', () => {
    cmp.open(makeStat());
    fx.detectChanges();
    const overlay = (fx.nativeElement as HTMLElement).querySelector('[data-testid="tracker-stat-dialog"]') as HTMLElement;
    // Simulate a click whose target is the overlay itself (backdrop).
    overlay.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    // Component handler checks event.target === event.currentTarget — invoke directly.
    const ev = { target: overlay, currentTarget: overlay } as unknown as MouseEvent;
    cmp.onBackdrop(ev);
    expect(cmp.visible()).toBe(false);
  });

  it('Esc keypress closes an open dialog', () => {
    cmp.open(makeStat());
    fx.detectChanges();
    cmp.onEsc();
    expect(cmp.visible()).toBe(false);
  });

  it('Esc is a no-op when not open', () => {
    expect(cmp.visible()).toBe(false);
    cmp.onEsc();
    expect(cmp.visible()).toBe(false);
  });

  it('copyJson writes serialised payload to the clipboard', async () => {
    const writeSpy = vi.fn().mockResolvedValue(undefined);
    // jsdom / happy-dom do not give us a real clipboard — install a shim.
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      value: { writeText: writeSpy },
      configurable: true,
      writable: true,
    });
    cmp.open(makeStat());
    fx.detectChanges();
    cmp.copyJson();
    // Wait a microtask for the promise to resolve.
    await Promise.resolve();
    expect(writeSpy).toHaveBeenCalledTimes(1);
    const payload = writeSpy.mock.calls[0][0];
    const parsed = JSON.parse(payload);
    expect(parsed.name).toBe('rutracker');
  });

  it('copyJson falls back to execCommand when clipboard api is absent', () => {
    const execSpy = vi.fn().mockReturnValue(true);
    document.execCommand = execSpy as any;
    // Kill the clipboard API for this test.
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      value: undefined,
      configurable: true,
      writable: true,
    });
    cmp.open(makeStat());
    fx.detectChanges();
    cmp.copyJson();
    expect(execSpy).toHaveBeenCalled();
  });

  it('formatDuration handles ms/s/m ranges', () => {
    expect(cmp.formatDuration(null)).toBe('-');
    expect(cmp.formatDuration(0)).toBe('0 ms');
    expect(cmp.formatDuration(250)).toBe('250 ms');
    expect(cmp.formatDuration(2500)).toBe('2.50 s');
    expect(cmp.formatDuration(125000)).toContain('2m');
  });

  it('formatTimestamp falls back to - on null', () => {
    expect(cmp.formatTimestamp(null)).toBe('-');
    // Accept any locale string as long as we didn't get back '-'.
    expect(cmp.formatTimestamp('2026-04-19T12:00:00Z')).not.toBe('-');
  });

  it('statusClass is a prefixed token', () => {
    expect(cmp.statusClass('success')).toBe('status-success');
    expect(cmp.statusClass(undefined)).toBe('unknown');
  });

  it('notes section renders entries when present', () => {
    cmp.open(makeStat({ notes: { login_attempt: 'failed', captcha: true } }));
    fx.detectChanges();
    const text = (fx.nativeElement as HTMLElement).textContent || '';
    expect(text).toContain('login_attempt');
    expect(text).toContain('failed');
    expect(text).toContain('captcha');
  });
});
