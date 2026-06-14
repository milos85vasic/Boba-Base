import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { Subject } from 'rxjs';
import { DashboardComponent } from './dashboard.component';
import { SseService } from '../../services/sse.service';
import { DialogService } from '../../services/dialog.service';
import { ToastService } from '../../services/toast.service';
import type { SearchResult, Source, TrackerSearchStat } from '../../models/search.model';

function makeResult(over: Partial<SearchResult> = {}): SearchResult {
  return {
    name: 'Ubuntu 22.04 LTS',
    size: '3.5 GB',
    seeds: 100,
    leechers: 2,
    download_urls: ['magnet:?xt=urn:btih:abc'],
    quality: 'full_hd',
    content_type: 'software',
    sources: [{ tracker: 'rutracker', seeds: 100, leechers: 2 }],
    metadata: null,
    freeleech: false,
    ...over,
  };
}

describe('DashboardComponent', () => {
  let http: HttpTestingController;
  let sse: Pick<SseService, 'connect' | 'disconnect' | 'events'>;
  let sseEvents: Subject<{ event: string; data: any }> | null;
  let connectSpy: ReturnType<typeof vi.fn>;
  let disconnectSpy: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    connectSpy = vi.fn();
    disconnectSpy = vi.fn();
    // Use a real Subject so the component can .subscribe() with either
    // an observer literal OR a bare callback — and the spec can call
    // .next() to push events of both shapes.
    sseEvents = new Subject<{ event: string; data: any }>();

    const sseStub = {
      connect: connectSpy,
      disconnect: disconnectSpy,
      events: sseEvents.asObservable(),
    };
    sse = sseStub as any;

    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: SseService, useValue: sseStub },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    try { http.verify(); } catch { /* some tests deliberately leave requests open */ }
  });

  /** Create the component and drain the requests kicked off by ngOnInit. */
  function bootstrap(): ReturnType<typeof TestBed.createComponent<DashboardComponent>> {
    const fx = TestBed.createComponent(DashboardComponent);
    fx.detectChanges();
    // ngOnInit fires: getStats, getAuthStatus, getBridgeHealth, getConfig
    http.expectOne('/api/v1/stats').flush({ active_searches: 0, completed_searches: 0, trackers_count: 0, trackers: [] });
    http.expectOne('/api/v1/auth/status').flush({ trackers: {} });
    http.expectOne('/api/v1/bridge/health').flush({ healthy: true });
    http.expectOne('/api/v1/config').flush({ qbittorrent_url: 'http://localhost:7186' });
    fx.detectChanges();
    return fx;
  }

  describe('creation / default state', () => {
    it('creates the component with default signals', () => {
      const fx = bootstrap();
      const c = fx.componentInstance;
      expect(c).toBeTruthy();
      expect(c.query()).toBe('');
      expect(c.isSearching()).toBe(false);
      expect(c.activeTab()).toBe('results');
      expect(c.sortColumn()).toBe('seeds');
      expect(c.sortDirection()).toBe('desc');
      expect(c.qbitAuthenticated()).toBe(false);
      expect(c.stats().trackers_count).toBe(0);
    });

    it('renders service-links header', () => {
      const fx = bootstrap();
      const links = (fx.nativeElement as HTMLElement).querySelectorAll('.service-links a');
      expect(links.length).toBeGreaterThanOrEqual(4);
    });

    it('renders the qBit Login chip when not authenticated', () => {
      const fx = bootstrap();
      const chip = (fx.nativeElement as HTMLElement).querySelector('.auth-chip');
      expect(chip?.textContent).toContain('qBit Login');
    });

    it('renders "qBit Connected" when authenticated', () => {
      const fx = TestBed.createComponent(DashboardComponent);
      fx.detectChanges();
      http.expectOne('/api/v1/stats').flush({ active_searches: 0, completed_searches: 0, trackers_count: 0, trackers: [] });
      http.expectOne('/api/v1/auth/status').flush({ trackers: { qbittorrent: { has_session: true, username: 'admin' } } });
      http.expectOne('/api/v1/bridge/health').flush({ healthy: true });
      http.expectOne('/api/v1/config').flush({ qbittorrent_url: '' });
      fx.detectChanges();
      const chip = (fx.nativeElement as HTMLElement).querySelector('.auth-chip.qbit-chip');
      expect(chip?.textContent).toContain('qBit Connected');
      // Username must be displayed in the chip now.
      expect(chip?.textContent).toContain('admin');
    });

    it('renders a chip per tracker returned by auth-status', () => {
      const fx = TestBed.createComponent(DashboardComponent);
      fx.detectChanges();
      http.expectOne('/api/v1/stats').flush({ active_searches: 0, completed_searches: 0, trackers_count: 0, trackers: [] });
      http.expectOne('/api/v1/auth/status').flush({
        trackers: {
          qbittorrent: { has_session: true, username: 'admin' },
          rutracker: { has_session: true, base_url: 'https://rutracker.org', username: 'ruuser' },
          kinozal: { has_session: false, base_url: '' },
          nnmclub: { has_session: false, base_url: '' },
          iptorrents: { has_session: true, base_url: 'https://iptorrents.com' },
        },
      });
      http.expectOne('/api/v1/bridge/health').flush({ healthy: true });
      http.expectOne('/api/v1/config').flush({ qbittorrent_url: '' });
      fx.detectChanges();
      const trackerChipEls = (fx.nativeElement as HTMLElement).querySelectorAll('.auth-chip.tracker-chip');
      // One per non-qbittorrent tracker.
      expect(trackerChipEls.length).toBe(4);
      // Chip for rutracker should include username.
      const chips = fx.componentInstance.trackerChips();
      const ruchip = chips.find(c => c.name === 'rutracker');
      expect(ruchip?.has_session).toBe(true);
      expect(ruchip?.username).toBe('ruuser');
    });

    it('marks WebUI Bridge link disabled when bridge is down', () => {
      const fx = TestBed.createComponent(DashboardComponent);
      fx.detectChanges();
      http.expectOne('/api/v1/stats').flush({ active_searches: 0, completed_searches: 0, trackers_count: 0, trackers: [] });
      http.expectOne('/api/v1/auth/status').flush({ trackers: {} });
      http.expectOne('/api/v1/bridge/health').flush({ healthy: false });
      http.expectOne('/api/v1/config').flush({ qbittorrent_url: '' });
      fx.detectChanges();
      const bridgeLink = (fx.nativeElement as HTMLElement).querySelector('a[href="http://localhost:7188"]');
      expect(bridgeLink?.classList.contains('disabled-link')).toBe(true);
      expect(bridgeLink?.textContent).toContain('down');
    });

    it('starts with bridgeHealthy=null (probing) and flips to true on first success', () => {
      const fx = TestBed.createComponent(DashboardComponent);
      // Signal defaults to null — initial render shows the "checking…" affordance.
      expect(fx.componentInstance.bridgeHealthy()).toBeNull();
      fx.detectChanges();
      http.expectOne('/api/v1/stats').flush({ active_searches: 0, completed_searches: 0, trackers_count: 0, trackers: [] });
      http.expectOne('/api/v1/auth/status').flush({ trackers: {} });
      http.expectOne('/api/v1/bridge/health').flush({ healthy: true });
      http.expectOne('/api/v1/config').flush({ qbittorrent_url: '' });
      fx.detectChanges();
      expect(fx.componentInstance.bridgeHealthy()).toBe(true);
    });

    it('retryBridgeProbe re-fires /api/v1/bridge/health', () => {
      const fx = bootstrap();
      expect(fx.componentInstance.bridgeHealthy()).toBe(true);
      fx.componentInstance.bridgeHealthy.set(false);
      const stopSpy = vi.fn();
      const prevSpy = vi.fn();
      fx.componentInstance.retryBridgeProbe({ stopPropagation: stopSpy, preventDefault: prevSpy } as any);
      http.expectOne('/api/v1/bridge/health').flush({ healthy: true });
      expect(fx.componentInstance.bridgeHealthy()).toBe(true);
      expect(stopSpy).toHaveBeenCalled();
      expect(prevSpy).toHaveBeenCalled();
    });

    it('onBridgeLinkClick re-probes when marked down and suppresses the nav', () => {
      const fx = bootstrap();
      fx.componentInstance.bridgeHealthy.set(false);
      const prevSpy = vi.fn();
      fx.componentInstance.onBridgeLinkClick({ preventDefault: prevSpy } as any);
      http.expectOne('/api/v1/bridge/health').flush({ healthy: false });
      expect(prevSpy).toHaveBeenCalled();
    });

    it('onBridgeLinkClick lets the anchor navigate when bridge is healthy', () => {
      const fx = bootstrap();
      fx.componentInstance.bridgeHealthy.set(true);
      const prevSpy = vi.fn();
      fx.componentInstance.onBridgeLinkClick({ preventDefault: prevSpy } as any);
      // No new HTTP call, and preventDefault must NOT be called.
      expect(prevSpy).not.toHaveBeenCalled();
    });
  });

  describe('loadStats / loadAuthStatus / loadDownloads / loadSchedules / loadHooks', () => {
    it('loadStats() updates stats + trackers signals', () => {
      const fx = bootstrap();
      fx.componentInstance.loadStats();
      http.expectOne('/api/v1/stats').flush({
        active_searches: 5,
        completed_searches: 10,
        trackers_count: 3,
        trackers: [{ name: 'rutracker', url: 'https://rutracker.org', enabled: true, health_status: 'healthy' }],
      });
      expect(fx.componentInstance.stats().active_searches).toBe(5);
      expect(fx.componentInstance.trackers()).toHaveLength(1);
    });

    it('loadAuthStatus() treats "authenticated" flag as session', () => {
      const fx = bootstrap();
      fx.componentInstance.loadAuthStatus();
      http.expectOne('/api/v1/auth/status').flush({ trackers: { qbittorrent: { authenticated: true } } });
      expect(fx.componentInstance.qbitAuthenticated()).toBe(true);
    });

    it('loadDownloads() updates activeDownloads', () => {
      const fx = bootstrap();
      fx.componentInstance.loadDownloads();
      http.expectOne('/api/v1/downloads/active').flush({ downloads: [{ name: 'x', size: 100, progress: 50, dlspeed: 1024, upspeed: 0, state: 'downloading', hash: 'abc', eta: 60 }], count: 1 });
      expect(fx.componentInstance.activeDownloads()).toHaveLength(1);
    });

    it('loadSchedules() updates schedules', () => {
      const fx = bootstrap();
      fx.componentInstance.loadSchedules();
      http.expectOne('/api/v1/schedules').flush({ schedules: [{ id: '1', name: 'daily', query: 'ubuntu', interval_minutes: 60, status: 'active' }] });
      expect(fx.componentInstance.schedules()).toHaveLength(1);
    });

    it('loadHooks() updates hooks', () => {
      const fx = bootstrap();
      fx.componentInstance.loadHooks();
      http.expectOne('/api/v1/hooks').flush({ hooks: [{ hook_id: 'h1', name: 'n', event: 'download_complete', script_path: '/s', enabled: true }], count: 1 });
      expect(fx.componentInstance.hooks()).toHaveLength(1);
    });
  });

  describe('doSearch', () => {
    it('no-ops on blank query', () => {
      const fx = bootstrap();
      fx.componentInstance.query.set('   ');
      fx.componentInstance.doSearch();
      http.expectNone('/api/v1/search');
      expect(fx.componentInstance.isSearching()).toBe(false);
    });

    it('starts a search, stores results, and clears isSearching on completion', () => {
      const fx = bootstrap();
      fx.componentInstance.query.set('ubuntu');
      fx.componentInstance.doSearch();
      expect(fx.componentInstance.isSearching()).toBe(true);

      const tr = http.expectOne('/api/v1/search');
      expect(tr.request.body).toEqual({ query: 'ubuntu', limit: 50, sort_by: 'seeds', sort_order: 'desc' });
      tr.flush({
        search_id: 's1',
        query: 'ubuntu',
        status: 'completed',
        results: [makeResult()],
        total_results: 1,
        merged_results: 0,
        trackers_searched: ['rutracker'],
        started_at: 'now',
      });

      expect(fx.componentInstance.searchId()).toBe('s1');
      expect(fx.componentInstance.results()).toHaveLength(1);
      expect(fx.componentInstance.totalResults()).toBe(1);
      expect(fx.componentInstance.isSearching()).toBe(false);
    });

    it('connects to SSE when status!=completed or results empty', () => {
      const fx = bootstrap();
      fx.componentInstance.query.set('ubuntu');
      fx.componentInstance.doSearch();
      http.expectOne('/api/v1/search').flush({
        search_id: 's2',
        query: 'ubuntu',
        status: 'running',
        results: [],
        total_results: 0,
        merged_results: 0,
        trackers_searched: [],
        started_at: 'now',
        stream_token: 'tok-s2',
      });
      // The per-search SSE bearer token (CONTINUATION #6) is threaded from
      // the search response through to the stream connection.
      expect(connectSpy).toHaveBeenCalledWith('s2', 'tok-s2');
    });

    it('shows error toast on failure', () => {
      const toast = TestBed.inject(ToastService);
      const errSpy = vi.spyOn(toast, 'error');
      const fx = bootstrap();
      fx.componentInstance.query.set('x');
      fx.componentInstance.doSearch();
      http.expectOne('/api/v1/search').flush({ detail: 'nope' }, { status: 500, statusText: 'Server Error' });
      expect(errSpy).toHaveBeenCalled();
      expect(fx.componentInstance.isSearching()).toBe(false);
      expect(fx.componentInstance.searchStatus()).toBe('Search failed');
    });

    it('aborts when called while already searching', () => {
      const fx = bootstrap();
      fx.componentInstance.isSearching.set(true);
      fx.componentInstance.searchId.set('s9');
      fx.componentInstance.doSearch();
      http.expectOne('/api/v1/search/s9/abort').flush({ search_id: 's9', status: 'aborted' });
      expect(fx.componentInstance.isSearching()).toBe(false);
      expect(disconnectSpy).toHaveBeenCalled();
    });
  });

  describe('SSE event handling', () => {
    function primeSearch(fx: ReturnType<typeof bootstrap>): void {
      fx.componentInstance.query.set('ubuntu');
      fx.componentInstance.doSearch();
      http.expectOne('/api/v1/search').flush({
        search_id: 's1',
        query: 'ubuntu',
        status: 'running',
        results: [],
        total_results: 0,
        merged_results: 0,
        trackers_searched: [],
        started_at: 'now',
      });
    }

    it('result_found appends a normalized live result', () => {
      const fx = bootstrap();
      primeSearch(fx);
      sseEvents?.next({ event: 'result_found', data: { name: 'Ubuntu', size: '3 GB', seeds: 10, leechers: 1, tracker: 'rutracker', link: 'https://x' } });
      expect(fx.componentInstance.liveResults()).toHaveLength(1);
      expect(fx.componentInstance.liveResults()[0].download_urls).toEqual(['https://x']);
    });

    it('results_update updates searchStatus', () => {
      const fx = bootstrap();
      primeSearch(fx);
      sseEvents?.next({ event: 'results_update', data: { total_results: 42 } });
      expect(fx.componentInstance.searchStatus()).toContain('42');
    });

    it('search_complete with results triggers a full load + disconnects', () => {
      const fx = bootstrap();
      primeSearch(fx);
      sseEvents?.next({ event: 'search_complete', data: { total_results: 1, merged_results: 0 } });
      http.expectOne('/api/v1/search/s1').flush({
        search_id: 's1',
        query: 'ubuntu',
        status: 'completed',
        results: [makeResult()],
        total_results: 1,
        merged_results: 0,
        trackers_searched: [],
        started_at: 'now',
      });
      expect(fx.componentInstance.isSearching()).toBe(false);
      expect(fx.componentInstance.results()).toHaveLength(1);
      expect(disconnectSpy).toHaveBeenCalled();
    });

    it('search_complete with 0 results shows empty message', () => {
      const fx = bootstrap();
      primeSearch(fx);
      sseEvents?.next({ event: 'search_complete', data: { total_results: 0, merged_results: 0 } });
      expect(fx.componentInstance.searchStatus()).toBe('No results found.');
    });

    it('error event warns and disconnects', () => {
      const toast = TestBed.inject(ToastService);
      const warnSpy = vi.spyOn(toast, 'warning');
      const fx = bootstrap();
      primeSearch(fx);
      sseEvents?.next({ event: 'error', data: {} });
      expect(warnSpy).toHaveBeenCalled();
      expect(fx.componentInstance.isSearching()).toBe(false);
    });
  });

  describe('abortSearch', () => {
    it('POSTs abort and emits info toast', () => {
      const toast = TestBed.inject(ToastService);
      const infoSpy = vi.spyOn(toast, 'info');
      const fx = bootstrap();
      fx.componentInstance.searchId.set('abc');
      fx.componentInstance.abortSearch();
      http.expectOne('/api/v1/search/abc/abort').flush({ search_id: 'abc', status: 'aborted' });
      expect(infoSpy).toHaveBeenCalledWith('Search cancelled');
      expect(fx.componentInstance.isSearching()).toBe(false);
    });

    it('does nothing API-wise when there is no search id', () => {
      const fx = bootstrap();
      fx.componentInstance.abortSearch();
      // No HTTP call expected.
      expect(fx.componentInstance.isSearching()).toBe(false);
    });
  });

  describe('addLiveResult', () => {
    it('fills defaults for missing fields', () => {
      const fx = bootstrap();
      fx.componentInstance.addLiveResult({});
      const r = fx.componentInstance.liveResults()[0];
      expect(r.name).toBe('Unknown');
      expect(r.seeds).toBe(0);
      expect(r.tracker).toBe('unknown');
      expect(r.freeleech).toBe(false);
    });
  });

  describe('sortResults / renderSortedResults', () => {
    it('toggles direction on same column, resets to desc on new column', () => {
      const fx = bootstrap();
      fx.componentInstance.results.set([]);
      fx.componentInstance.sortResults('seeds'); // same as default -> toggle to asc
      expect(fx.componentInstance.sortDirection()).toBe('asc');
      fx.componentInstance.sortResults('seeds'); // toggle back to desc
      expect(fx.componentInstance.sortDirection()).toBe('desc');
      fx.componentInstance.sortResults('name'); // new column
      expect(fx.componentInstance.sortColumn()).toBe('name');
      expect(fx.componentInstance.sortDirection()).toBe('desc');
    });

    it('sorts by seeds desc by default', () => {
      const fx = bootstrap();
      fx.componentInstance.results.set([
        makeResult({ name: 'a', seeds: 10 }),
        makeResult({ name: 'b', seeds: 50 }),
        makeResult({ name: 'c', seeds: 30 }),
      ]);
      fx.componentInstance.sortColumn.set('seeds');
      fx.componentInstance.sortDirection.set('desc');
      fx.componentInstance.renderSortedResults();
      expect(fx.componentInstance.results().map(r => r.name)).toEqual(['b', 'c', 'a']);
    });

    it('sorts by size parsed from human-readable strings', () => {
      const fx = bootstrap();
      fx.componentInstance.results.set([
        makeResult({ name: 'a', size: '500 MB' }),
        makeResult({ name: 'b', size: '1.5 GB' }),
        makeResult({ name: 'c', size: '100 KB' }),
      ]);
      fx.componentInstance.sortColumn.set('size');
      fx.componentInstance.sortDirection.set('asc');
      fx.componentInstance.renderSortedResults();
      expect(fx.componentInstance.results().map(r => r.name)).toEqual(['c', 'a', 'b']);
    });

    it('sorts by name alphabetically', () => {
      const fx = bootstrap();
      fx.componentInstance.results.set([makeResult({ name: 'beta' }), makeResult({ name: 'alpha' })]);
      fx.componentInstance.sortColumn.set('name');
      fx.componentInstance.sortDirection.set('asc');
      fx.componentInstance.renderSortedResults();
      expect(fx.componentInstance.results().map(r => r.name)).toEqual(['alpha', 'beta']);
    });

    it('sorts by quality weight', () => {
      const fx = bootstrap();
      fx.componentInstance.results.set([
        makeResult({ name: 'a', quality: 'sd' }),
        makeResult({ name: 'b', quality: 'uhd_4k' }),
        makeResult({ name: 'c', quality: 'full_hd' }),
      ]);
      fx.componentInstance.sortColumn.set('quality');
      fx.componentInstance.sortDirection.set('desc');
      fx.componentInstance.renderSortedResults();
      expect(fx.componentInstance.results().map(r => r.name)).toEqual(['b', 'c', 'a']);
    });

    it('sorts unknown content_type first when desc, last when asc', () => {
      const fx = bootstrap();
      fx.componentInstance.results.set([
        makeResult({ name: 'a', content_type: 'movie' }),
        makeResult({ name: 'b', content_type: 'unknown' }),
      ]);
      fx.componentInstance.sortColumn.set('type');
      fx.componentInstance.sortDirection.set('desc');
      fx.componentInstance.renderSortedResults();
      expect(fx.componentInstance.results()[0].name).toBe('b');
      fx.componentInstance.sortDirection.set('asc');
      fx.componentInstance.renderSortedResults();
      expect(fx.componentInstance.results()[0].name).toBe('a');
    });

    it('sorts by number of sources', () => {
      const fx = bootstrap();
      const twoSrcs: Source[] = [
        { tracker: 't1', seeds: 1, leechers: 0 },
        { tracker: 't2', seeds: 1, leechers: 0 },
      ];
      fx.componentInstance.results.set([
        makeResult({ name: 'a', sources: [{ tracker: 't1', seeds: 1, leechers: 0 }] }),
        makeResult({ name: 'b', sources: twoSrcs }),
      ]);
      fx.componentInstance.sortColumn.set('sources');
      fx.componentInstance.sortDirection.set('desc');
      fx.componentInstance.renderSortedResults();
      expect(fx.componentInstance.results()[0].name).toBe('b');
    });

    it('sorts by leechers', () => {
      const fx = bootstrap();
      fx.componentInstance.results.set([
        makeResult({ name: 'a', leechers: 1 }),
        makeResult({ name: 'b', leechers: 5 }),
      ]);
      fx.componentInstance.sortColumn.set('leechers');
      fx.componentInstance.sortDirection.set('desc');
      fx.componentInstance.renderSortedResults();
      expect(fx.componentInstance.results()[0].name).toBe('b');
    });
  });

  describe('parseSize / formatSize / formatEta', () => {
    it('parseSize understands units', () => {
      const fx = bootstrap();
      const c = fx.componentInstance;
      expect(c.parseSize('')).toBe(0);
      expect(c.parseSize('junk')).toBe(0);
      expect(c.parseSize('1 KB')).toBe(1024);
      expect(c.parseSize('1.5 GB')).toBeCloseTo(1.5 * 1024 ** 3, 0);
      expect(c.parseSize('2 TB')).toBeCloseTo(2 * 1024 ** 4, 0);
      expect(c.parseSize('500 B')).toBe(500);
    });

    it('formatSize handles 0, numbers, and preformatted strings', () => {
      const fx = bootstrap();
      const c = fx.componentInstance;
      expect(c.formatSize(0)).toBe('0 B');
      expect(c.formatSize(1024)).toBe('1.0 KB');
      expect(c.formatSize(1024 ** 3)).toBe('1.0 GB');
      expect(c.formatSize('3.5 GB')).toBe('3.5 GB'); // already formatted
      expect(c.formatSize('500')).toBe('500.0 B');
      expect(c.formatSize('garbage')).toBe('garbage');
    });

    it('formatEta returns "-" when effectively infinite', () => {
      const fx = bootstrap();
      expect(fx.componentInstance.formatEta(8640000)).toBe('-');
      expect(fx.componentInstance.formatEta(45)).toBe('45s');
      expect(fx.componentInstance.formatEta(90)).toBe('1m 30s');
      expect(fx.componentInstance.formatEta(3661)).toBe('1h 1m 1s');
    });
  });

  describe('getSortClass / downloadStateClass', () => {
    it('getSortClass returns sortable when not active', () => {
      const fx = bootstrap();
      expect(fx.componentInstance.getSortClass('name')).toBe('sortable');
    });

    it('getSortClass appends direction when active', () => {
      const fx = bootstrap();
      fx.componentInstance.sortColumn.set('name');
      fx.componentInstance.sortDirection.set('asc');
      expect(fx.componentInstance.getSortClass('name')).toBe('sortable asc');
    });

    it('downloadStateClass buckets states', () => {
      const fx = bootstrap();
      const c = fx.componentInstance;
      expect(c.downloadStateClass('downloading')).toBe('downloading');
      expect(c.downloadStateClass('uploading')).toBe('seeding');
      expect(c.downloadStateClass('pausedDL')).toBe('paused');
      expect(c.downloadStateClass('unknown')).toBe('unknown');
    });
  });

  describe('schedule + hook actions', () => {
    it('createSchedule ignores blank name/query', () => {
      const fx = bootstrap();
      fx.componentInstance.schedName.set('');
      fx.componentInstance.schedQuery.set('');
      fx.componentInstance.createSchedule();
      http.expectNone('/api/v1/schedules');
    });

    it('createSchedule POSTs and refreshes list', () => {
      const fx = bootstrap();
      fx.componentInstance.schedName.set('n');
      fx.componentInstance.schedQuery.set('q');
      fx.componentInstance.schedInterval.set(45);
      fx.componentInstance.createSchedule();
      const tr = http.expectOne('/api/v1/schedules');
      expect(tr.request.method).toBe('POST');
      expect(tr.request.body).toEqual({ name: 'n', query: 'q', interval_minutes: 45 });
      tr.flush({ id: '1', name: 'n', query: 'q', interval_minutes: 45, status: 'active' });
      // loadSchedules() kicks off a GET.
      http.expectOne('/api/v1/schedules').flush({ schedules: [] });
    });

    it('deleteSchedule DELETEs and refreshes', () => {
      const fx = bootstrap();
      fx.componentInstance.deleteSchedule('42');
      http.expectOne('/api/v1/schedules/42').flush(null);
      http.expectOne('/api/v1/schedules').flush({ schedules: [] });
    });

    it('deleteHook DELETEs and refreshes', () => {
      const fx = bootstrap();
      fx.componentInstance.deleteHook('h1');
      http.expectOne('/api/v1/hooks/h1').flush(null);
      http.expectOne('/api/v1/hooks').flush({ hooks: [], count: 0 });
    });
  });

  describe('switchTab', () => {
    it('switches tab + triggers downloads reload', () => {
      const fx = bootstrap();
      fx.componentInstance.switchTab('downloads');
      expect(fx.componentInstance.activeTab()).toBe('downloads');
      http.expectOne('/api/v1/downloads/active').flush({ downloads: [], count: 0 });
    });

    it('switches to trackers tab and reloads stats', () => {
      const fx = bootstrap();
      fx.componentInstance.switchTab('trackers');
      http.expectOne('/api/v1/stats').flush({ active_searches: 0, completed_searches: 0, trackers_count: 0, trackers: [] });
    });

    it('switches to schedules tab and loads schedules', () => {
      const fx = bootstrap();
      fx.componentInstance.switchTab('schedules');
      http.expectOne('/api/v1/schedules').flush({ schedules: [] });
    });

    it('switches to hooks tab and loads hooks', () => {
      const fx = bootstrap();
      fx.componentInstance.switchTab('hooks');
      http.expectOne('/api/v1/hooks').flush({ hooks: [], count: 0 });
    });
  });

  describe('trackerHtml / escapeHtml', () => {
    it('returns "" on empty sources', () => {
      const fx = bootstrap();
      expect(fx.componentInstance.trackerHtml([])).toBe('');
    });

    it('single source renders a plain tracker-tag', () => {
      const fx = bootstrap();
      const html = fx.componentInstance.trackerHtml([{ tracker: 'rutracker', seeds: 1, leechers: 0 }]);
      expect(html).toContain('tracker-tag');
      expect(html).toContain('rutracker');
      expect(html).not.toContain('merged-indicator');
    });

    it('multiple sources trigger merged-indicator', () => {
      const fx = bootstrap();
      const html = fx.componentInstance.trackerHtml([
        { tracker: 'rutracker', seeds: 1, leechers: 0 },
        { tracker: 'kinozal', seeds: 1, leechers: 0 },
      ]);
      expect(html).toContain('merged-indicator');
      expect(html).toContain('rutracker');
      expect(html).toContain('kinozal');
    });

    it('freeleech-tagged tracker gets the freeleech class', () => {
      const fx = bootstrap();
      const html = fx.componentInstance.trackerHtml([{ tracker: 'IPTorrents [free]', seeds: 1, leechers: 0 }]);
      expect(html).toContain('freeleech');
    });

    it('escapeHtml escapes angle brackets', () => {
      const fx = bootstrap();
      expect(fx.componentInstance.escapeHtml('<script>')).toBe('&lt;script&gt;');
    });
  });

  describe('ngOnDestroy', () => {
    it('clears intervals and disconnects SSE', () => {
      const fx = bootstrap();
      fx.componentInstance.ngOnDestroy();
      expect(disconnectSpy).toHaveBeenCalled();
    });
  });

  describe('tracker chips + qBit username + logout', () => {
    it('loadAuthStatus updates qbitUsername and trackerChips', () => {
      const fx = bootstrap();
      fx.componentInstance.loadAuthStatus();
      http.expectOne('/api/v1/auth/status').flush({
        trackers: {
          qbittorrent: { has_session: true, username: 'milos' },
          rutracker: { has_session: true, username: 'r', base_url: 'https://rutracker.org' },
          kinozal: { has_session: false, base_url: '' },
        },
      });
      expect(fx.componentInstance.qbitUsername()).toBe('milos');
      expect(fx.componentInstance.trackerChips()).toHaveLength(2);
      expect(fx.componentInstance.trackerChips()[0].name).toBe('rutracker');
    });

    it('toggleChip flips expandedChip state', () => {
      const fx = bootstrap();
      fx.componentInstance.toggleChip('rutracker');
      expect(fx.componentInstance.expandedChip()).toBe('rutracker');
      fx.componentInstance.toggleChip('rutracker');
      expect(fx.componentInstance.expandedChip()).toBeNull();
      fx.componentInstance.toggleChip('kinozal');
      expect(fx.componentInstance.expandedChip()).toBe('kinozal');
    });

    it('logoutQbit POSTs /auth/qbittorrent/logout and refreshes auth', () => {
      const fx = bootstrap();
      fx.componentInstance.qbitAuthenticated.set(true);
      fx.componentInstance.qbitUsername.set('admin');
      const event = new Event('click');
      fx.componentInstance.logoutQbit(event);
      http.expectOne('/api/v1/auth/qbittorrent/logout').flush({ status: 'logged_out' });
      expect(fx.componentInstance.qbitAuthenticated()).toBe(false);
      expect(fx.componentInstance.qbitUsername()).toBeNull();
      // Then a follow-up auth status refresh.
      http.expectOne('/api/v1/auth/status').flush({ trackers: {} });
    });

    it('openQbitLogin wires up a success callback that refreshes auth', () => {
      const fx = bootstrap();
      const openSpy = vi.fn();
      (fx.componentInstance as any).qbitDialog = { open: openSpy };
      fx.componentInstance.openQbitLogin();
      expect(openSpy).toHaveBeenCalledTimes(1);
      // The handler is a function — invoke it to simulate dialog success
      // and assert the component refreshes auth status.
      const onSuccess = openSpy.mock.calls[0][0];
      expect(typeof onSuccess).toBe('function');
      onSuccess();
      http.expectOne('/api/v1/auth/status').flush({ trackers: { qbittorrent: { has_session: true, username: 'z' } } });
      expect(fx.componentInstance.qbitAuthenticated()).toBe(true);
      expect(fx.componentInstance.qbitUsername()).toBe('z');
    });
  });

  describe('bridge health', () => {
    it('loadBridgeHealth sets bridgeHealthy based on response', () => {
      const fx = bootstrap();
      fx.componentInstance.loadBridgeHealth();
      http.expectOne('/api/v1/bridge/health').flush({ healthy: false });
      expect(fx.componentInstance.bridgeHealthy()).toBe(false);
    });

    it('loadBridgeHealth treats HTTP error as bridge down', () => {
      const fx = bootstrap();
      fx.componentInstance.loadBridgeHealth();
      http.expectOne('/api/v1/bridge/health').flush(null, { status: 500, statusText: 'err' });
      expect(fx.componentInstance.bridgeHealthy()).toBe(false);
    });
  });

  describe('sourceStats', () => {
    it('returns an empty list when sources is missing', () => {
      const fx = bootstrap();
      expect(fx.componentInstance.sourceStats([])).toEqual({ isMerged: false, trackers: [] });
      expect(fx.componentInstance.sourceStats(undefined as any)).toEqual({ isMerged: false, trackers: [] });
    });

    it('flags merged=true when 2+ sources are present', () => {
      const fx = bootstrap();
      const s = fx.componentInstance.sourceStats([
        { tracker: 'rutracker', seeds: 1, leechers: 0 },
        { tracker: 'kinozal', seeds: 2, leechers: 0 },
      ]);
      expect(s.isMerged).toBe(true);
      expect(s.trackers.map(t => t.name)).toEqual(['rutracker', 'kinozal']);
    });

    it('counts duplicate trackers and detects freeleech', () => {
      const fx = bootstrap();
      const s = fx.componentInstance.sourceStats([
        { tracker: 'IPTorrents [free]', seeds: 1, leechers: 0 },
        { tracker: 'IPTorrents [free]', seeds: 2, leechers: 0 },
      ]);
      expect(s.trackers[0].name).toBe('IPTorrents [free]');
      expect(s.trackers[0].count).toBe(2);
      expect(s.trackers[0].isFree).toBe(true);
      expect(s.isMerged).toBe(true);
    });
  });

  describe('sortedResults computed signal', () => {
    it('is reactively derived from results() + sort column + direction', () => {
      const fx = bootstrap();
      fx.componentInstance.results.set([
        makeResult({ name: 'a', seeds: 10 }),
        makeResult({ name: 'b', seeds: 50 }),
      ]);
      fx.componentInstance.sortColumn.set('seeds');
      fx.componentInstance.sortDirection.set('desc');
      expect(fx.componentInstance.sortedResults().map(r => r.name)).toEqual(['b', 'a']);
      // Flip direction without mutating the underlying array.
      fx.componentInstance.sortDirection.set('asc');
      expect(fx.componentInstance.sortedResults().map(r => r.name)).toEqual(['a', 'b']);
    });
  });

  describe('searchErrors surface tracker failures', () => {
    it('stores errors from /search response', () => {
      const fx = bootstrap();
      fx.componentInstance.query.set('ubuntu');
      fx.componentInstance.doSearch();
      http.expectOne('/api/v1/search').flush({
        search_id: 's1',
        query: 'ubuntu',
        status: 'completed',
        results: [makeResult()],
        total_results: 1,
        merged_results: 0,
        trackers_searched: ['rutracker', 'kinozal'],
        errors: ['kinozal: HTTP 503'],
        started_at: 'now',
      });
      expect(fx.componentInstance.searchErrors()).toEqual(['kinozal: HTTP 503']);
    });

    it('populates errors from the follow-up get after SSE completes', () => {
      const fx = bootstrap();
      fx.componentInstance.searchId.set('s2');
      fx.componentInstance.loadSearchResults('s2');
      http.expectOne('/api/v1/search/s2').flush({
        search_id: 's2',
        query: 'x',
        status: 'completed',
        results: [],
        total_results: 0,
        merged_results: 0,
        trackers_searched: [],
        errors: ['rutracker: captcha_required'],
        started_at: 'now',
      });
      expect(fx.componentInstance.searchErrors()).toEqual(['rutracker: captcha_required']);
    });
  });

  describe('virtual-scroll trackBy', () => {
    it('produces a stable id from name|size|url', () => {
      const fx = bootstrap();
      const row = makeResult({ name: 'x', size: '1 GB', download_urls: ['u1'] });
      expect(fx.componentInstance.trackResult(0, row)).toBe('x|1 GB|u1');
    });
  });

  describe('doSchedule / executeSchedule / doDownload / doMagnet', () => {
    it('doSchedule bails when dialog cancelled', async () => {
      const fx = bootstrap();
      const dialog = TestBed.inject(DialogService);
      vi.spyOn(dialog, 'confirm').mockResolvedValue(false);
      fx.componentInstance.results.set([makeResult()]);
      await fx.componentInstance.doSchedule(0);
      http.expectNone('/api/v1/download');
    });

    it('doSchedule executes directly when already authenticated', async () => {
      const fx = bootstrap();
      const dialog = TestBed.inject(DialogService);
      vi.spyOn(dialog, 'confirm').mockResolvedValue(true);
      fx.componentInstance.qbitAuthenticated.set(true);
      fx.componentInstance.results.set([makeResult()]);
      await fx.componentInstance.doSchedule(0);
      const tr = http.expectOne('/api/v1/download');
      expect(tr.request.method).toBe('POST');
      tr.flush({ download_id: 'd', status: 'initiated', urls_count: 1, added_count: 1, results: [] });
    });

    it('executeSchedule shows toast on success', () => {
      const toast = TestBed.inject(ToastService);
      const successSpy = vi.spyOn(toast, 'success');
      const fx = bootstrap();
      fx.componentInstance.results.set([makeResult()]);
      fx.componentInstance.executeSchedule(0);
      http.expectOne('/api/v1/download').flush({ download_id: 'd', status: 'initiated', urls_count: 1, added_count: 1, results: [] });
      expect(successSpy).toHaveBeenCalled();
    });

    it('executeSchedule out-of-range index is a no-op', () => {
      const fx = bootstrap();
      fx.componentInstance.results.set([]);
      fx.componentInstance.executeSchedule(5);
      http.expectNone('/api/v1/download');
    });

    it('doDownload bails if cancelled', async () => {
      const fx = bootstrap();
      vi.spyOn(TestBed.inject(DialogService), 'confirm').mockResolvedValue(false);
      fx.componentInstance.results.set([makeResult()]);
      await fx.componentInstance.doDownload(0);
      http.expectNone('/api/v1/download/file');
    });

    it('doMagnet requests magnet and opens dialog via ViewChild', () => {
      const fx = bootstrap();
      const openSpy = vi.fn();
      (fx.componentInstance as any).magnetDialog = { open: openSpy };
      fx.componentInstance.results.set([makeResult()]);
      fx.componentInstance.doMagnet(0);
      http.expectOne('/api/v1/magnet').flush({ magnet: 'magnet:?xt=urn:btih:abc', hashes: ['abc'] });
      expect(openSpy).toHaveBeenCalled();
    });

    // Button-responsiveness UX (operator mandate 2026-06-14): the moment a
    // result-row button is clicked it MUST show a processing indicator and the
    // grid MUST report that row+action as busy, cleared only when the async
    // work resolves (success OR error). These assert the user-observable
    // `isBusy()` signal toggles around the REAL request lifecycle — they fail
    // against the pre-change handlers (no busy state → always false).
    describe('instant button processing indicator (isBusy)', () => {
      it('doMagnet: busy true in-flight, false after resolve', () => {
        const fx = bootstrap();
        (fx.componentInstance as any).magnetDialog = { open: vi.fn() };
        fx.componentInstance.results.set([makeResult()]);
        expect(fx.componentInstance.isBusy(0, 'magnet')).toBe(false);
        fx.componentInstance.doMagnet(0);
        expect(fx.componentInstance.isBusy(0, 'magnet')).toBe(true);
        http.expectOne('/api/v1/magnet').flush({ magnet: 'magnet:?xt=urn:btih:abc', hashes: ['abc'] });
        expect(fx.componentInstance.isBusy(0, 'magnet')).toBe(false);
      });

      it('doMagnet: busy cleared on error', () => {
        const fx = bootstrap();
        fx.componentInstance.results.set([makeResult()]);
        fx.componentInstance.doMagnet(0);
        expect(fx.componentInstance.isBusy(0, 'magnet')).toBe(true);
        http.expectOne('/api/v1/magnet').error(new ProgressEvent('error'));
        expect(fx.componentInstance.isBusy(0, 'magnet')).toBe(false);
      });

      it('doSchedule: busy true in-flight, false after add resolves', async () => {
        const fx = bootstrap();
        vi.spyOn(TestBed.inject(DialogService), 'confirm').mockResolvedValue(true);
        fx.componentInstance.qbitAuthenticated.set(true);
        fx.componentInstance.results.set([makeResult()]);
        await fx.componentInstance.doSchedule(0);
        expect(fx.componentInstance.isBusy(0, 'qbit')).toBe(true);
        http.expectOne('/api/v1/download').flush({ download_id: 'd', status: 'initiated', urls_count: 1, added_count: 1, results: [] });
        expect(fx.componentInstance.isBusy(0, 'qbit')).toBe(false);
      });

      it('doDownload: busy true in-flight, false after file resolves', async () => {
        const fx = bootstrap();
        vi.spyOn(TestBed.inject(DialogService), 'confirm').mockResolvedValue(true);
        vi.spyOn(window.URL, 'createObjectURL').mockReturnValue('blob:x');
        vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {});
        fx.componentInstance.results.set([makeResult()]);
        await fx.componentInstance.doDownload(0);
        expect(fx.componentInstance.isBusy(0, 'download')).toBe(true);
        http.expectOne('/api/v1/download/file').flush(new Blob(['torrent']));
        expect(fx.componentInstance.isBusy(0, 'download')).toBe(false);
      });

      it('doDownload: busy cleared on error', async () => {
        const fx = bootstrap();
        vi.spyOn(TestBed.inject(DialogService), 'confirm').mockResolvedValue(true);
        fx.componentInstance.results.set([makeResult()]);
        await fx.componentInstance.doDownload(0);
        expect(fx.componentInstance.isBusy(0, 'download')).toBe(true);
        http.expectOne('/api/v1/download/file').error(new ProgressEvent('error'));
        expect(fx.componentInstance.isBusy(0, 'download')).toBe(false);
      });
    });

    // Defect A regression (§11.4.115): while a search is IN PROGRESS the grid
    // renders liveResults() (via sortedResults()) and results() is still empty.
    // The buttons MUST act on the displayed live row. Pre-fix the handlers read
    // results()[index] → undefined → every button was a NO-OP mid-search. These
    // assert a REAL request/dialog fires for the live row. Against the pre-fix
    // code (results()[index]) every one of these fails with "expected one match".
    describe('buttons work DURING an in-progress search (live rows)', () => {
      function searchingWithLiveRow(fx: any): void {
        fx.componentInstance.isSearching.set(true);
        fx.componentInstance.results.set([]); // empty until search_complete
        fx.componentInstance.liveResults.set([
          makeResult({ name: 'live-row', download_urls: ['magnet:?xt=urn:btih:liverow'] }),
        ]);
      }

      it('qBit (doSchedule) sends the live row mid-search — not a no-op', async () => {
        const fx = bootstrap();
        vi.spyOn(TestBed.inject(DialogService), 'confirm').mockResolvedValue(true);
        fx.componentInstance.qbitAuthenticated.set(true);
        searchingWithLiveRow(fx);
        await fx.componentInstance.doSchedule(0);
        const tr = http.expectOne('/api/v1/download');
        expect(tr.request.method).toBe('POST');
        expect(tr.request.body.download_urls).toEqual(['magnet:?xt=urn:btih:liverow']);
        tr.flush({ download_id: 'd', status: 'initiated', urls_count: 1, added_count: 1, results: [] });
      });

      it('Download (doDownload) downloads the live row mid-search', async () => {
        const fx = bootstrap();
        vi.spyOn(TestBed.inject(DialogService), 'confirm').mockResolvedValue(true);
        vi.spyOn(window.URL, 'createObjectURL').mockReturnValue('blob:x');
        vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {});
        searchingWithLiveRow(fx);
        await fx.componentInstance.doDownload(0);
        const dr = http.expectOne('/api/v1/download/file');
        expect(dr.request.method).toBe('POST');
        expect(dr.request.body.download_urls).toEqual(['magnet:?xt=urn:btih:liverow']);
        dr.flush(new Blob(['torrent']));
      });

      it('Magnet (doMagnet) generates the live row magnet mid-search', () => {
        const fx = bootstrap();
        const openSpy = vi.fn();
        (fx.componentInstance as any).magnetDialog = { open: openSpy };
        searchingWithLiveRow(fx);
        fx.componentInstance.doMagnet(0);
        const mr = http.expectOne('/api/v1/magnet');
        expect(mr.request.body.download_urls).toEqual(['magnet:?xt=urn:btih:liverow']);
        mr.flush({ magnet: 'magnet:?xt=urn:btih:liverow', hashes: ['liverow'] });
        expect(openSpy).toHaveBeenCalled();
      });

      // Deferred-login race (review nit): if the qBit login dialog is open when
      // the search completes, sortedResults() re-orders — re-resolving by index
      // would send the WRONG torrent. The handler captures the clicked ROW, so
      // it must still send exactly what the user clicked. RED against the old
      // re-resolve-by-index path, GREEN with the row-capture.
      it('deferred qBit login sends the CLICKED row even if the search completes mid-dialog', async () => {
        const fx = bootstrap();
        vi.spyOn(TestBed.inject(DialogService), 'confirm').mockResolvedValue(true);
        vi.spyOn(fx.componentInstance, 'loadAuthStatus').mockImplementation(() => {});
        fx.componentInstance.qbitAuthenticated.set(false); // force the login dialog
        // mid-search: row 0 is the one the user clicks
        fx.componentInstance.isSearching.set(true);
        fx.componentInstance.results.set([]);
        fx.componentInstance.liveResults.set([
          makeResult({ name: 'CLICKED', download_urls: ['magnet:?xt=urn:btih:clicked'] }),
          makeResult({ name: 'OTHER', download_urls: ['magnet:?xt=urn:btih:other'] }),
        ]);
        let loginCb: (() => void) | undefined;
        (fx.componentInstance as any).qbitDialog = { open: (cb: () => void) => { loginCb = cb; } };
        await fx.componentInstance.doSchedule(0); // click row 0 = CLICKED
        // search completes; the final list re-orders so index 0 is now a DIFFERENT row
        fx.componentInstance.isSearching.set(false);
        fx.componentInstance.results.set([
          makeResult({ name: 'OTHER', download_urls: ['magnet:?xt=urn:btih:other'] }),
          makeResult({ name: 'CLICKED', download_urls: ['magnet:?xt=urn:btih:clicked'] }),
        ]);
        fx.componentInstance.qbitAuthenticated.set(true);
        loginCb!(); // user finishes login AFTER completion
        const tr = http.expectOne('/api/v1/download');
        expect(tr.request.body.download_urls).toEqual(['magnet:?xt=urn:btih:clicked']);
        tr.flush({ download_id: 'd', status: 'initiated', urls_count: 1, added_count: 1, results: [] });
      });

      // Busy-state regression guard (§11.4.135, review nit): the deferred-login
      // path is the most stuck-prone — busy must NOT latch true while the login
      // dialog is open (no work yet), must go true once the callback fires the
      // request, and must clear when it resolves. A latched spinner is a defect.
      it('deferred qBit login: busy stays false until callback, true in-flight, false after — never stuck', async () => {
        const fx = bootstrap();
        vi.spyOn(TestBed.inject(DialogService), 'confirm').mockResolvedValue(true);
        vi.spyOn(fx.componentInstance, 'loadAuthStatus').mockImplementation(() => {});
        fx.componentInstance.qbitAuthenticated.set(false);
        fx.componentInstance.results.set([makeResult()]);
        let loginCb: (() => void) | undefined;
        (fx.componentInstance as any).qbitDialog = { open: (cb: () => void) => { loginCb = cb; } };
        await fx.componentInstance.doSchedule(0);
        // Login dialog open, no request yet → NOT busy (waiting on the user).
        http.expectNone('/api/v1/download');
        expect(fx.componentInstance.isBusy(0, 'qbit')).toBe(false);
        // User completes login → callback fires the real request.
        fx.componentInstance.qbitAuthenticated.set(true);
        loginCb!();
        expect(fx.componentInstance.isBusy(0, 'qbit')).toBe(true);
        http.expectOne('/api/v1/download').flush({ download_id: 'd', status: 'initiated', urls_count: 1, added_count: 1, results: [] });
        expect(fx.componentInstance.isBusy(0, 'qbit')).toBe(false);
      });

      // auth_failed re-login: busy MUST clear (done() runs first) before the
      // re-login dialog opens — otherwise the spinner latches forever.
      it('executeScheduleRow auth_failed clears busy before re-prompting login', () => {
        const fx = bootstrap();
        (fx.componentInstance as any).qbitDialog = { open: vi.fn() };
        vi.spyOn(fx.componentInstance, 'loadAuthStatus').mockImplementation(() => {});
        fx.componentInstance.executeScheduleRow(makeResult(), 'qbit:0');
        expect(fx.componentInstance.isBusy(0, 'qbit')).toBe(true);
        http.expectOne('/api/v1/download').flush({ download_id: 'd', status: 'auth_failed', results: [] });
        expect(fx.componentInstance.isBusy(0, 'qbit')).toBe(false);
      });
    });
  });

  describe('tracker stats bar', () => {
    function makeStat(over: Partial<TrackerSearchStat> = {}): TrackerSearchStat {
      return {
        name: 'rutracker',
        tracker_url: 'https://rutracker.org',
        status: 'pending',
        results_count: 0,
        started_at: null,
        completed_at: null,
        duration_ms: null,
        error: null,
        error_type: null,
        authenticated: true,
        attempt: 1,
        http_status: null,
        category: 'all',
        query: 'ubuntu',
        notes: {},
        ...over,
      };
    }

    it('trackerStatsSummary computes bucket counts across all statuses', () => {
      const fx = bootstrap();
      fx.componentInstance.trackerStats.set([
        makeStat({ name: 'a', status: 'success' }),
        makeStat({ name: 'b', status: 'success' }),
        makeStat({ name: 'c', status: 'empty' }),
        makeStat({ name: 'd', status: 'error' }),
        makeStat({ name: 'e', status: 'timeout' }),
        makeStat({ name: 'f', status: 'running' }),
        makeStat({ name: 'g', status: 'pending' }),
      ]);
      const s = fx.componentInstance.trackerStatsSummary();
      expect(s.successCount).toBe(2);
      expect(s.emptyCount).toBe(1);
      expect(s.errorCount).toBe(2); // error + timeout
      expect(s.runningCount).toBe(2); // running + pending
      expect(s.completedCount).toBe(5); // everything except pending/running
    });

    it('doSearch seeds trackerStats from the POST /search response', () => {
      const fx = bootstrap();
      fx.componentInstance.query.set('ubuntu');
      fx.componentInstance.doSearch();
      const tr = http.expectOne('/api/v1/search');
      tr.flush({
        search_id: 's1',
        query: 'ubuntu',
        status: 'running',
        results: [],
        total_results: 0,
        merged_results: 0,
        trackers_searched: ['rutracker', 'kinozal'],
        tracker_stats: [
          makeStat({ name: 'kinozal', status: 'pending' }),
          makeStat({ name: 'rutracker', status: 'pending' }),
        ],
        started_at: 'now',
      });
      const stats = fx.componentInstance.trackerStats();
      expect(stats).toHaveLength(2);
      expect(stats.map(s => s.name)).toEqual(['kinozal', 'rutracker']);
    });

    it('SSE tracker_started flips a stat to running', () => {
      const fx = bootstrap();
      fx.componentInstance.trackerStats.set([
        makeStat({ name: 'rutracker', status: 'pending' }),
      ]);
      fx.componentInstance.onTrackerStarted({ name: 'rutracker', started_at: '2026-04-19T12:00:00Z' });
      const stat = fx.componentInstance.trackerStats().find(s => s.name === 'rutracker');
      expect(stat?.status).toBe('running');
      expect(stat?.started_at).toBe('2026-04-19T12:00:00Z');
    });

    it('SSE tracker_started adds a new chip when the name is unknown', () => {
      const fx = bootstrap();
      fx.componentInstance.trackerStats.set([]);
      fx.componentInstance.onTrackerStarted({ name: 'eztv', tracker_url: 'https://eztv' });
      const stats = fx.componentInstance.trackerStats();
      expect(stats).toHaveLength(1);
      expect(stats[0].name).toBe('eztv');
      expect(stats[0].status).toBe('running');
    });

    it('SSE tracker_completed replaces the full stat object', () => {
      const fx = bootstrap();
      fx.componentInstance.trackerStats.set([
        makeStat({ name: 'rutracker', status: 'running' }),
      ]);
      fx.componentInstance.onTrackerCompleted({
        name: 'rutracker',
        status: 'success',
        results_count: 5,
        duration_ms: 320,
      });
      const s = fx.componentInstance.trackerStats().find(x => x.name === 'rutracker');
      expect(s?.status).toBe('success');
      expect(s?.results_count).toBe(5);
      expect(s?.duration_ms).toBe(320);
    });

    it('SSE tracker_completed on error captures error_type/message', () => {
      const fx = bootstrap();
      fx.componentInstance.trackerStats.set([
        makeStat({ name: 'rutracker', status: 'running' }),
      ]);
      fx.componentInstance.onTrackerCompleted({
        name: 'rutracker',
        status: 'error',
        error: 'boom',
        error_type: 'RuntimeError',
      });
      const s = fx.componentInstance.trackerStats().find(x => x.name === 'rutracker');
      expect(s?.status).toBe('error');
      expect(s?.error).toBe('boom');
      expect(s?.error_type).toBe('RuntimeError');
    });

    it('openTrackerStatDialog delegates to the ViewChild dialog', () => {
      const fx = bootstrap();
      const openSpy = vi.fn();
      (fx.componentInstance as any).trackerStatDialog = { open: openSpy };
      const stat = makeStat();
      fx.componentInstance.openTrackerStatDialog(stat);
      expect(openSpy).toHaveBeenCalledWith(stat);
    });

    it('trackStatByName returns the stat name as identity key', () => {
      const fx = bootstrap();
      expect(fx.componentInstance.trackStatByName(0, makeStat({ name: 'eztv' }))).toBe('eztv');
    });

    it('connectSse routes tracker_started / tracker_completed into the signal', () => {
      const fx = bootstrap();
      fx.componentInstance.query.set('u');
      fx.componentInstance.doSearch();
      http.expectOne('/api/v1/search').flush({
        search_id: 's1',
        query: 'u',
        status: 'running',
        results: [],
        total_results: 0,
        merged_results: 0,
        trackers_searched: ['rutracker'],
        tracker_stats: [makeStat({ name: 'rutracker', status: 'pending' })],
        started_at: 'now',
      });
      sseEvents?.next({ event: 'tracker_started', data: { name: 'rutracker', started_at: 't0' } });
      expect(fx.componentInstance.trackerStats()[0].status).toBe('running');
      sseEvents?.next({ event: 'tracker_completed', data: { name: 'rutracker', status: 'success', results_count: 3 } });
      expect(fx.componentInstance.trackerStats()[0].status).toBe('success');
      expect(fx.componentInstance.trackerStats()[0].results_count).toBe(3);
    });

    it('renders one chip per stat in the Results tab', () => {
      const fx = bootstrap();
      fx.componentInstance.trackerStats.set([
        makeStat({ name: 'alpha', status: 'success', results_count: 2 }),
        makeStat({ name: 'beta', status: 'error', error_type: 'RuntimeError', error: 'boom' }),
      ]);
      fx.detectChanges();
      const chips = (fx.nativeElement as HTMLElement).querySelectorAll('.tracker-stat-chip');
      expect(chips.length).toBe(2);
      expect(chips[0].textContent).toContain('alpha');
      expect(chips[1].textContent).toContain('beta');
    });

    it('renders a deadline-hit badge when notes.deadline_hit is true', () => {
      // When the backend's per-tracker subprocess deadline fires, the
      // captured NDJSON rows are still surfaced — but the result set
      // is truncated. The badge tells the operator "there's more where
      // that came from; raise PUBLIC_TRACKER_DEADLINE_SECONDS".
      const fx = bootstrap();
      fx.componentInstance.trackerStats.set([
        makeStat({
          name: 'linuxtracker',
          status: 'success',
          results_count: 285,
          notes: { deadline_hit: true, deadline_seconds: 25 },
        }),
        makeStat({
          name: 'piratebay',
          status: 'success',
          results_count: 100,
          notes: {},
        }),
      ]);
      fx.detectChanges();

      const truncatedChip = (fx.nativeElement as HTMLElement).querySelector(
        '[data-tracker="linuxtracker"]'
      );
      const cleanChip = (fx.nativeElement as HTMLElement).querySelector(
        '[data-tracker="piratebay"]'
      );
      expect(truncatedChip).toBeTruthy();
      expect(cleanChip).toBeTruthy();

      expect(
        truncatedChip!.querySelector('[data-testid="deadline-hit-badge"]'),
      ).toBeTruthy();
      // Clean chip must NOT show the stopwatch — otherwise every chip
      // would look truncated and the signal is useless.
      expect(
        cleanChip!.querySelector('[data-testid="deadline-hit-badge"]'),
      ).toBeNull();
    });

    it('loadSearchResults populates tracker_stats when present on the response', () => {
      const fx = bootstrap();
      fx.componentInstance.loadSearchResults('sX');
      http.expectOne('/api/v1/search/sX').flush({
        search_id: 'sX',
        query: 'u',
        status: 'completed',
        results: [],
        total_results: 0,
        merged_results: 0,
        trackers_searched: ['rutracker', 'kinozal'],
        tracker_stats: [
          makeStat({ name: 'kinozal', status: 'success', results_count: 1 }),
          makeStat({ name: 'rutracker', status: 'empty' }),
        ],
        started_at: 'now',
      });
      expect(fx.componentInstance.trackerStats()).toHaveLength(2);
    });
  });

  describe('live result streaming', () => {
    function primeRunningSearch(fx: ReturnType<typeof bootstrap>): void {
      fx.componentInstance.query.set('linux');
      fx.componentInstance.doSearch();
      http.expectOne('/api/v1/search').flush({
        search_id: 'live-1',
        query: 'linux',
        status: 'running',
        results: [],
        total_results: 0,
        merged_results: 0,
        trackers_searched: [],
        tracker_stats: [],
        started_at: 'now',
      });
    }

    it('sortedResults reflects each result_found event during search', () => {
      const fx = bootstrap();
      primeRunningSearch(fx);
      expect(fx.componentInstance.isSearching()).toBe(true);
      // Initial state: nothing rendered.
      expect(fx.componentInstance.sortedResults()).toHaveLength(0);

      sseEvents?.next({
        event: 'result_found',
        data: {
          name: 'Ubuntu 22.04 LTS',
          size: '3.5 GB',
          seeds: 120,
          leechers: 4,
          tracker: 'rutracker',
          link: 'magnet:?xt=urn:btih:a',
        },
      });
      expect(fx.componentInstance.sortedResults()).toHaveLength(1);
      expect(fx.componentInstance.sortedResults()[0].name).toBe('Ubuntu 22.04 LTS');

      sseEvents?.next({
        event: 'result_found',
        data: {
          name: 'Debian 12',
          size: '600 MB',
          seeds: 200,
          leechers: 5,
          tracker: 'kinozal',
          link: 'magnet:?xt=urn:btih:b',
        },
      });
      expect(fx.componentInstance.sortedResults()).toHaveLength(2);
      // Sort is seeds-desc by default, so Debian (200) comes first.
      expect(fx.componentInstance.sortedResults()[0].name).toBe('Debian 12');
    });

    it('live rows dedup by tracker|link|name so duplicate events do not flash twice', () => {
      const fx = bootstrap();
      primeRunningSearch(fx);
      const evt = {
        event: 'result_found',
        data: { name: 'dup', size: '1 GB', seeds: 1, leechers: 0, tracker: 't', link: 'magnet:x' },
      };
      sseEvents?.next(evt);
      sseEvents?.next(evt);
      sseEvents?.next(evt);
      expect(fx.componentInstance.liveResults()).toHaveLength(1);
      expect(fx.componentInstance.sortedResults()).toHaveLength(1);
    });

    it('searchStatus reports the live-row count while streaming', () => {
      const fx = bootstrap();
      primeRunningSearch(fx);
      for (let i = 0; i < 3; i++) {
        sseEvents?.next({
          event: 'result_found',
          data: { name: `n${i}`, size: '1 GB', seeds: i, leechers: 0, tracker: 't', link: `magnet:${i}` },
        });
      }
      expect(fx.componentInstance.searchStatus()).toMatch(/Found 3 results/);
    });

    it('merged_update renders the MERGED rows, not the raw liveResults, and tracks the count', () => {
      const fx = bootstrap();
      primeRunningSearch(fx);

      // First, a couple of raw per-tracker rows arrive (pre-first-merged-update).
      sseEvents?.next({
        event: 'result_found',
        data: { name: 'r1', size: '1 GB', seeds: 1, leechers: 0, tracker: 'ta', link: 'magnet:1' },
      });
      sseEvents?.next({
        event: 'result_found',
        data: { name: 'r2', size: '1 GB', seeds: 2, leechers: 0, tracker: 'tb', link: 'magnet:2' },
      });
      expect(fx.componentInstance.sortedResults()).toHaveLength(2);

      // Now the backend emits the de-duplicated merged set: a single merged row.
      const mergedRow = makeResult({
        name: 'merged-1',
        seeds: 50,
        download_urls: ['magnet:m1'],
        sources: [
          { tracker: 'ta', seeds: 1, leechers: 0 },
          { tracker: 'tb', seeds: 2, leechers: 0 },
        ],
      });
      sseEvents?.next({ event: 'merged_update', data: { merged_results: 1, results: [mergedRow] } });

      // The grid now shows the MERGED view (1 row, the merged name), NOT the 2 raw rows.
      expect(fx.componentInstance.sortedResults()).toHaveLength(1);
      expect(fx.componentInstance.sortedResults()[0].name).toBe('merged-1');
      // The status line tracks the merged count.
      expect(fx.componentInstance.searchStatus()).toContain('1 unique results');
      // liveResults are still preserved underneath (not destroyed).
      expect(fx.componentInstance.liveResults()).toHaveLength(2);
    });

    // KEY ANTI-BLUFF GUARD (§11.4.115): the displayed count must GROW smoothly
    // through the merged_update sequence and NOT drop when the search completes.
    // Pre-change the grid showed raw liveResults during the search (say, many
    // per-tracker rows) and swapped to the smaller merged list on completion →
    // a visible shrink. With the fix the grid renders liveMergedResults during
    // the search, and the final get_search list equals the last merged_update,
    // so the count stays put. We synthesise growing merged batches (50 → 400 →
    // 663), complete, return the SAME 663 from get_search, and assert the
    // displayed length never drops below the last merged_update count.
    it('does NOT shrink on completion after growing merged_update events (50 → 400 → 663)', () => {
      const fx = bootstrap();
      primeRunningSearch(fx);

      const batch = (n: number): SearchResult[] =>
        Array.from({ length: n }, (_, i) =>
          makeResult({ name: `m${i}`, seeds: i, download_urls: [`magnet:m${i}`] }),
        );

      // Growing de-duplicated snapshots.
      sseEvents?.next({ event: 'merged_update', data: { merged_results: 50, results: batch(50) } });
      expect(fx.componentInstance.sortedResults().length).toBe(50);

      sseEvents?.next({ event: 'merged_update', data: { merged_results: 400, results: batch(400) } });
      expect(fx.componentInstance.sortedResults().length).toBe(400);

      const finalBatch = batch(663);
      sseEvents?.next({ event: 'merged_update', data: { merged_results: 663, results: finalBatch } });
      expect(fx.componentInstance.sortedResults().length).toBe(663);

      const lengthBeforeComplete = fx.componentInstance.sortedResults().length;
      expect(lengthBeforeComplete).toBe(663);

      // Completion: total_results is the RAW per-tracker total (larger), but the
      // de-duplicated/merged list returned by get_search equals the last
      // merged_update (663).
      sseEvents?.next({
        event: 'search_complete',
        data: { total_results: 1785, merged_results: 663, trackers_searched: ['ta', 'tb'] },
      });
      http.expectOne('/api/v1/search/live-1').flush({
        search_id: 'live-1',
        query: 'linux',
        status: 'completed',
        results: finalBatch,
        total_results: 1785,
        merged_results: 663,
        trackers_searched: ['ta', 'tb'],
        started_at: 'now',
      });

      // THE GUARD: the displayed count must NOT drop below the last
      // merged_update count. It stays 663 — no sudden shrink/overwrite.
      expect(fx.componentInstance.isSearching()).toBe(false);
      const lengthAfterComplete = fx.componentInstance.sortedResults().length;
      expect(lengthAfterComplete).toBe(663);
      expect(lengthAfterComplete).toBeGreaterThanOrEqual(lengthBeforeComplete);
    });

    // ANTI-BLUFF GUARD (§11.4.115) for the COMPLETION-path `liveMerged`
    // fallback in `sortedResults`:
    //   rows = merged.length > 0 ? merged : (liveMerged.length > 0 ? liveMerged : live)
    // The two existing tests cover (a) the during-search merged view and (b)
    // the no-shrink guard where results() is NON-empty after completion.
    // NEITHER exercises the case where, after completion, results() is EMPTY
    // but liveMergedResults() is populated — e.g. a synchronous POST
    // completion came back with no body while merged_update batches had
    // already streamed in. If the `liveMerged.length > 0 ? liveMerged : live`
    // sub-expression were dropped to a bare `: live`, this branch would
    // render the (empty/raw) liveResults and silently lose the merged
    // snapshot — and no other test would fail. This pins the fallback down.
    it('after completion with empty results() but populated liveMergedResults, sortedResults falls back to the merged snapshot', () => {
      const fx = bootstrap();
      const c = fx.componentInstance;

      // Drive the signals directly into the post-completion state we want to
      // isolate: search done, NO get_search results, but a merged snapshot
      // is present from earlier merged_update batches.
      c.isSearching.set(false);
      c.results.set([]); // get_search returned nothing
      c.liveMergedResults.set([
        makeResult({ name: 'merged-A', seeds: 90, download_urls: ['magnet:mA'] }),
        makeResult({ name: 'merged-B', seeds: 80, download_urls: ['magnet:mB'] }),
        makeResult({ name: 'merged-C', seeds: 70, download_urls: ['magnet:mC'] }),
        makeResult({ name: 'merged-D', seeds: 60, download_urls: ['magnet:mD'] }),
        makeResult({ name: 'merged-E', seeds: 50, download_urls: ['magnet:mE'] }),
      ]);
      // Raw live rows are present too — to PROVE the fallback prefers the
      // merged snapshot over the raw liveResults, not just "non-empty wins".
      c.liveResults.set([
        makeResult({ name: 'raw-X', seeds: 5, download_urls: ['magnet:rX'] }),
        makeResult({ name: 'raw-Y', seeds: 4, download_urls: ['magnet:rY'] }),
      ]);

      const rows = c.sortedResults();
      // The merged snapshot (5 rows) is rendered, NOT the 2 raw liveResults.
      expect(rows).toHaveLength(5);
      const names = rows.map(r => r.name).sort();
      expect(names).toEqual(['merged-A', 'merged-B', 'merged-C', 'merged-D', 'merged-E']);
      // And it must NOT have fallen through to the raw liveResults.
      expect(names).not.toContain('raw-X');
      expect(names).not.toContain('raw-Y');
    });

    it('search_complete swaps sortedResults over to the final merged list', () => {
      const fx = bootstrap();
      primeRunningSearch(fx);
      // Two live hits, from two different trackers for the same content.
      sseEvents?.next({
        event: 'result_found',
        data: { name: 'same', size: '1 GB', seeds: 10, leechers: 0, tracker: 'ta', link: 'magnet:z' },
      });
      sseEvents?.next({
        event: 'result_found',
        data: { name: 'same', size: '1 GB', seeds: 5, leechers: 0, tracker: 'tb', link: 'magnet:z' },
      });
      expect(fx.componentInstance.sortedResults()).toHaveLength(2);

      // The completion event triggers a GET /search/{id} for the
      // merged view — return a single deduped row.
      sseEvents?.next({
        event: 'search_complete',
        data: { total_results: 2, merged_results: 1, trackers_searched: ['ta', 'tb'] },
      });
      http.expectOne('/api/v1/search/live-1').flush({
        search_id: 'live-1',
        query: 'linux',
        status: 'completed',
        results: [
          {
            name: 'same',
            size: '1 GB',
            seeds: 15,
            leechers: 0,
            download_urls: ['magnet:z'],
            quality: 'hd',
            content_type: 'software',
            sources: [
              { tracker: 'ta', seeds: 10, leechers: 0 },
              { tracker: 'tb', seeds: 5, leechers: 0 },
            ],
            metadata: null,
            freeleech: false,
          },
        ],
        total_results: 2,
        merged_results: 1,
        trackers_searched: ['ta', 'tb'],
        started_at: 'now',
      });

      expect(fx.componentInstance.isSearching()).toBe(false);
      expect(fx.componentInstance.sortedResults()).toHaveLength(1);
      expect(fx.componentInstance.sortedResults()[0].seeds).toBe(15);
    });
  });
});
