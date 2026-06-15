import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { ApiService } from './api.service';
import { API_BASE_URL } from '../config/api-base';
import type {
  SearchRequest,
  SearchResponse,
  DownloadRequest,
  DownloadResponse,
  ActiveDownload,
  Schedule,
  Hook,
  AuthStatus,
  QbitCredentials,
  MagnetResponse,
  StatsResponse,
} from '../models/search.model';

describe('ApiService', () => {
  let svc: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    svc = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('search() POSTs to /api/v1/search with the request body', () => {
    const req: SearchRequest = { query: 'ubuntu', limit: 10 };
    const stub: Partial<SearchResponse> = { search_id: 's1', status: 'started' };
    svc.search(req).subscribe(r => {
      expect(r.search_id).toBe('s1');
    });
    const tr = http.expectOne('/api/v1/search');
    expect(tr.request.method).toBe('POST');
    expect(tr.request.body).toEqual(req);
    tr.flush(stub);
  });

  it('getSearch() GETs /api/v1/search/:id', () => {
    svc.getSearch('abc').subscribe();
    const tr = http.expectOne('/api/v1/search/abc');
    expect(tr.request.method).toBe('GET');
    tr.flush({});
  });

  it('abortSearch() POSTs /api/v1/search/:id/abort with empty body', () => {
    svc.abortSearch('abc').subscribe(r => {
      expect(r.status).toBe('aborted');
    });
    const tr = http.expectOne('/api/v1/search/abc/abort');
    expect(tr.request.method).toBe('POST');
    expect(tr.request.body).toEqual({});
    tr.flush({ search_id: 'abc', status: 'aborted' });
  });

  it('download() POSTs /api/v1/download', () => {
    const req: DownloadRequest = { result_id: '1', download_urls: ['https://a'] };
    const stub: Partial<DownloadResponse> = { download_id: 'd', status: 'initiated', urls_count: 1, added_count: 1, results: [] };
    svc.download(req).subscribe();
    const tr = http.expectOne('/api/v1/download');
    expect(tr.request.method).toBe('POST');
    expect(tr.request.body).toEqual(req);
    tr.flush(stub);
  });

  it('downloadFile() POSTs /api/v1/download/file with Blob responseType', () => {
    const req: DownloadRequest = { result_id: '1', download_urls: ['https://a'] };
    const blob = new Blob(['binary'], { type: 'application/x-bittorrent' });
    svc.downloadFile(req).subscribe(b => {
      expect(b).toBeInstanceOf(Blob);
    });
    const tr = http.expectOne('/api/v1/download/file');
    expect(tr.request.method).toBe('POST');
    expect(tr.request.responseType).toBe('blob');
    tr.flush(blob);
  });

  it('generateMagnet() POSTs /api/v1/magnet', () => {
    const req: DownloadRequest = { result_id: 'x', download_urls: ['https://a'] };
    const stub: MagnetResponse = { magnet: 'magnet:?xt=urn:btih:abc', hashes: ['abc'] };
    svc.generateMagnet(req).subscribe(r => {
      expect(r.magnet).toContain('magnet:');
    });
    const tr = http.expectOne('/api/v1/magnet');
    expect(tr.request.method).toBe('POST');
    tr.flush(stub);
  });

  it('getActiveDownloads() GETs /api/v1/downloads/active', () => {
    const downloads: ActiveDownload[] = [];
    svc.getActiveDownloads().subscribe(r => {
      expect(r.count).toBe(0);
    });
    const tr = http.expectOne('/api/v1/downloads/active');
    expect(tr.request.method).toBe('GET');
    tr.flush({ downloads, count: 0 });
  });

  it('getSchedules() GETs /api/v1/schedules', () => {
    const schedules: Schedule[] = [];
    svc.getSchedules().subscribe();
    const tr = http.expectOne('/api/v1/schedules');
    expect(tr.request.method).toBe('GET');
    tr.flush({ schedules });
  });

  it('createSchedule() POSTs /api/v1/schedules', () => {
    const body = { name: 'n', query: 'q', interval_minutes: 30 };
    svc.createSchedule(body).subscribe();
    const tr = http.expectOne('/api/v1/schedules');
    expect(tr.request.method).toBe('POST');
    expect(tr.request.body).toEqual(body);
    tr.flush({ id: '1', ...body, status: 'active' });
  });

  it('deleteSchedule() DELETEs /api/v1/schedules/:id', () => {
    svc.deleteSchedule('42').subscribe();
    const tr = http.expectOne('/api/v1/schedules/42');
    expect(tr.request.method).toBe('DELETE');
    tr.flush(null);
  });

  it('getHooks() GETs /api/v1/hooks', () => {
    const hooks: Hook[] = [];
    svc.getHooks().subscribe();
    const tr = http.expectOne('/api/v1/hooks');
    expect(tr.request.method).toBe('GET');
    tr.flush({ hooks, count: 0 });
  });

  it('createHook() POSTs /api/v1/hooks', () => {
    const body = { name: 'h', event: 'download_complete', script_path: '/tmp/x.sh', enabled: true };
    svc.createHook(body).subscribe();
    const tr = http.expectOne('/api/v1/hooks');
    expect(tr.request.method).toBe('POST');
    expect(tr.request.body).toEqual(body);
    tr.flush({ hook_id: 'h1', ...body });
  });

  it('deleteHook() DELETEs /api/v1/hooks/:id', () => {
    svc.deleteHook('h1').subscribe();
    const tr = http.expectOne('/api/v1/hooks/h1');
    expect(tr.request.method).toBe('DELETE');
    tr.flush(null);
  });

  it('getAuthStatus() GETs /api/v1/auth/status', () => {
    const stub: AuthStatus = { trackers: {} };
    svc.getAuthStatus().subscribe();
    const tr = http.expectOne('/api/v1/auth/status');
    expect(tr.request.method).toBe('GET');
    tr.flush(stub);
  });

  it('qbitLogin() POSTs /api/v1/auth/qbittorrent with credentials', () => {
    const creds: QbitCredentials = { username: 'admin', password: 'admin', save: true };
    svc.qbitLogin(creds).subscribe(r => {
      expect(r.status).toBe('authenticated');
    });
    const tr = http.expectOne('/api/v1/auth/qbittorrent');
    expect(tr.request.method).toBe('POST');
    expect(tr.request.body).toEqual(creds);
    tr.flush({ status: 'authenticated', version: '4.6' });
  });

  it('getStats() GETs /api/v1/stats', () => {
    const stub: StatsResponse = { active_searches: 1, completed_searches: 2, trackers_count: 3 };
    svc.getStats().subscribe(r => {
      expect(r.trackers_count).toBe(3);
    });
    const tr = http.expectOne('/api/v1/stats');
    expect(tr.request.method).toBe('GET');
    tr.flush(stub);
  });

  it('getConfig() GETs /api/v1/config', () => {
    svc.getConfig().subscribe(c => {
      expect(c.qbittorrent_url).toBe('http://localhost:7185');
    });
    const tr = http.expectOne('/api/v1/config');
    expect(tr.request.method).toBe('GET');
    tr.flush({ qbittorrent_url: 'http://localhost:7185' });
  });

  it('propagates HTTP 500 errors to subscribers', () => {
    let caught: unknown;
    svc.getStats().subscribe({
      next: () => { /* no-op */ },
      error: (err) => { caught = err; },
    });
    const tr = http.expectOne('/api/v1/stats');
    tr.flush({ error: 'boom' }, { status: 500, statusText: 'Server Error' });
    expect((caught as { status: number }).status).toBe(500);
  });

  it('propagates HTTP 4xx errors with response body to subscribers', () => {
    let caught: any;
    svc.qbitLogin({ username: '', password: '' }).subscribe({
      next: () => { /* no-op */ },
      error: (err) => { caught = err; },
    });
    const tr = http.expectOne('/api/v1/auth/qbittorrent');
    tr.flush({ error: 'bad creds' }, { status: 401, statusText: 'Unauthorized' });
    expect(caught.status).toBe(401);
    expect(caught.error.error).toBe('bad creds');
  });
});

// --- BUG-5 (search-flow-audit-20260615): a dashboard served from a
// different origin than the API hit its OWN origin because baseUrl was a
// hardcoded relative ''. The configured API base MUST prefix every
// request. §11.4.135 regression guard.
describe('ApiService (configured remote API base — BUG-5 RED)', () => {
  let svc: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://remote.example:7187' },
      ],
    });
    svc = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('search() POSTs to the configured remote API base', () => {
    svc.search({ query: 'ubuntu', limit: 10 }).subscribe();
    const tr = http.expectOne('https://remote.example:7187/api/v1/search');
    expect(tr.request.method).toBe('POST');
    tr.flush({ search_id: 's1', status: 'started' });
  });

  it('getSearch() GETs the configured remote API base', () => {
    svc.getSearch('abc').subscribe();
    const tr = http.expectOne('https://remote.example:7187/api/v1/search/abc');
    expect(tr.request.method).toBe('GET');
    tr.flush({});
  });
});
