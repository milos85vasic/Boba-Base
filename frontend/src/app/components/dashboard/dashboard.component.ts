import { Component, inject, signal, computed, OnInit, OnDestroy, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ScrollingModule } from '@angular/cdk/scrolling';
import { HttpClient } from '@angular/common/http';
import { ApiService } from '../../services/api.service';
import { ToastService } from '../../services/toast.service';
import { DialogService } from '../../services/dialog.service';
import { SseService } from '../../services/sse.service';
import {
  SearchResult, ActiveDownload, Schedule, Hook,
  TrackerStatus, Source, TrackerSearchStat
} from '../../models/search.model';
import { MagnetDialogComponent } from '../magnet-dialog/magnet-dialog.component';
import { QbitLoginDialogComponent } from '../qbit-login-dialog/qbit-login-dialog.component';
import { TrackerStatDialogComponent } from '../tracker-stat-dialog/tracker-stat-dialog.component';
import { ThemePickerComponent } from '../theme-picker/theme-picker.component';

export interface TrackerChip {
  name: string;
  has_session: boolean;
  username?: string;
  base_url?: string;
}

export interface SourceStats {
  isMerged: boolean;
  trackers: { name: string; count: number; isFree: boolean }[];
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, ScrollingModule, MagnetDialogComponent, QbitLoginDialogComponent, TrackerStatDialogComponent, ThemePickerComponent],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss']
})
export class DashboardComponent implements OnInit, OnDestroy {
  private api = inject(ApiService);
  private toast = inject(ToastService);
  private dialog = inject(DialogService);
  private sse = inject(SseService);
  private http = inject(HttpClient);

  @ViewChild(MagnetDialogComponent) magnetDialog!: MagnetDialogComponent;
  @ViewChild(QbitLoginDialogComponent) qbitDialog!: QbitLoginDialogComponent;
  @ViewChild(TrackerStatDialogComponent) trackerStatDialog!: TrackerStatDialogComponent;

  // Search state
  query = signal('');
  isSearching = signal(false);
  searchId = signal('');
  searchStatus = signal('');
  results = signal<SearchResult[]>([]);
  liveResults = signal<SearchResult[]>([]);
  // De-duplicated (merged) snapshot streamed during the search via the
  // backend's `merged_update` SSE events. Once the first merged_update
  // arrives, the grid prefers this over the raw `liveResults` so the
  // displayed list IS the merged set as it builds — and the final
  // merged_update equals what GET /search/{id} returns, so completion is
  // seamless (no sudden shrink/overwrite of the count).
  liveMergedResults = signal<SearchResult[]>([]);
  totalResults = signal(0);
  mergedResults = signal(0);
  searchErrors = signal<string[]>([]);
  trackerStats = signal<TrackerSearchStat[]>([]);

  // Sorting
  sortColumn = signal('seeds');
  sortDirection = signal<'asc' | 'desc'>('desc');

  // Memoised sorted view for fast rendering of thousands of rows.
  //
  // While the search is running, prefer the DEDUPLICATED (merged) view
  // streamed via `merged_update` SSE events the moment it has data, so
  // the grid renders the merged set as it builds and grows smoothly to
  // the final unique count. Before the first `merged_update` arrives we
  // fall back to the raw `liveResults` (the per-tracker `result_found`
  // rows) so the table still fills in early. The moment the search
  // completes, `loadSearchResults` populates the `results` signal from
  // GET /search/{id} — which equals the LAST `merged_update`, so the
  // swap is seamless: NO sudden shrink/overwrite of the row count. If
  // the search completes and returned nothing live (e.g. a purely
  // synchronous completion came back on the POST), still fall back to
  // the merged `results` so we never render an empty grid when we have
  // data.
  readonly sortedResults = computed(() => {
    const searching = this.isSearching();
    const liveMerged = this.liveMergedResults();
    const live = this.liveResults();
    const merged = this.results();
    let rows: SearchResult[];
    if (searching) {
      // Merged view wins as soon as it exists; otherwise the raw live
      // rows that arrive before the first merged_update.
      rows = liveMerged.length > 0 ? liveMerged : live;
    } else {
      // Completed: the final merged list from get_search (== last
      // merged_update). Fall back to live rows only if it's empty.
      rows = merged.length > 0 ? merged : (liveMerged.length > 0 ? liveMerged : live);
    }
    const col = this.sortColumn();
    const dir = this.sortDirection();
    return this._sort(rows, col, dir);
  });

  // Bucket counts for the per-tracker chip bar header.  Running +
  // pending share a bucket because from the user's perspective they
  // are both "in flight".
  readonly trackerStatsSummary = computed(() => {
    const stats = this.trackerStats();
    return {
      successCount: stats.filter(s => s.status === 'success').length,
      emptyCount:   stats.filter(s => s.status === 'empty').length,
      errorCount:   stats.filter(s => s.status === 'error' || s.status === 'timeout').length,
      runningCount: stats.filter(s => s.status === 'running' || s.status === 'pending').length,
      completedCount: stats.filter(s => !['pending', 'running'].includes(s.status)).length,
    };
  });

  // Tabs
  activeTab = signal('results');

  // Stats
  stats = signal({ active_searches: 0, completed_searches: 0, trackers_count: 0 });
  trackers = signal<TrackerStatus[]>([]);

  // Downloads
  activeDownloads = signal<ActiveDownload[]>([]);

  // Schedules
  schedules = signal<Schedule[]>([]);
  schedName = signal('');
  schedQuery = signal('');
  schedInterval = signal(60);

  // Hooks
  hooks = signal<Hook[]>([]);

  // Auth
  qbitAuthenticated = signal(false);
  qbitUsername = signal<string | null>(null);
  trackerChips = signal<TrackerChip[]>([]);
  expandedChip = signal<string | null>(null);

  // Bridge health. `null` = probe has not run yet (don't lie on first
  // render); `true` = bridge responded 200-ish; `false` = probe failed.
  // Separate interval from stats so a slow-to-start bridge self-heals
  // quickly without waiting for the 30-second stats tick.
  bridgeHealthy = signal<boolean | null>(null);
  bridgeChecking = signal(false);

  // Config
  config = signal({
    qbittorrent_url:
      typeof window !== 'undefined'
        ? `${window.location.protocol}//${window.location.hostname}:7186`
        : 'http://localhost:7186',
  });

  private sseSub?: any;
  private pollInterval?: any;
  private statsInterval?: any;
  private bridgeInterval?: any;

  get hostUrl(): string {
    return typeof window !== 'undefined'
      ? `${window.location.protocol}//${window.location.hostname}`
      : 'http://localhost';
  }

  ngOnInit(): void {
    this.loadStats();
    this.loadAuthStatus();
    this.loadBridgeHealth();
    this.api.getConfig().subscribe(c => this.config.set(c));
    this.statsInterval = setInterval(() => {
      this.loadStats();
      this.loadAuthStatus();
      this.loadDownloads();
    }, 30000);
    // Bridge re-probe every 10 s — independent of the 30 s stats
    // cadence so a late-starting bridge flips to "up" within one
    // cycle instead of up to half a minute.
    this.bridgeInterval = setInterval(() => this.loadBridgeHealth(), 10000);
  }

  ngOnDestroy(): void {
    this.sse.disconnect();
    if (this.pollInterval) clearInterval(this.pollInterval);
    if (this.statsInterval) clearInterval(this.statsInterval);
    if (this.bridgeInterval) clearInterval(this.bridgeInterval);
    if (this.sseSub) this.sseSub.unsubscribe();
  }

  // Stats & Auth
  loadStats(): void {
    this.api.getStats().subscribe(s => {
      this.stats.set(s);
      this.trackers.set(s.trackers || []);
    });
  }

  loadAuthStatus(): void {
    this.api.getAuthStatus().subscribe(status => {
      const qbit = status.trackers?.['qbittorrent'];
      this.qbitAuthenticated.set(!!(qbit?.has_session || qbit?.authenticated));
      this.qbitUsername.set(qbit?.username ?? null);
      // Everything except qBittorrent becomes a tracker chip.
      const chips: TrackerChip[] = [];
      for (const [name, val] of Object.entries(status.trackers || {})) {
        if (name === 'qbittorrent') continue;
        chips.push({
          name,
          has_session: !!(val?.has_session || val?.authenticated),
          username: val?.username,
          base_url: (val as any)?.base_url,
        });
      }
      this.trackerChips.set(chips);
    });
  }

  loadBridgeHealth(): void {
    this.bridgeChecking.set(true);
    this.http.get<{ healthy: boolean }>('/api/v1/bridge/health').subscribe({
      next: (r) => {
        this.bridgeHealthy.set(!!r.healthy);
        this.bridgeChecking.set(false);
      },
      error: () => {
        this.bridgeHealthy.set(false);
        this.bridgeChecking.set(false);
      },
    });
  }

  /** User clicked the WebUI Bridge link while it's marked down.
   * Re-probe once — if the bridge came up in the meantime, let the
   * navigation proceed; otherwise keep the click suppressed so they
   * don't land on a dead page.
   */
  onBridgeLinkClick(event: Event): void {
    if (this.bridgeHealthy() === true) return; // healthy — let anchor navigate
    event.preventDefault();
    this.loadBridgeHealth();
    this.toast.info('Re-probing WebUI Bridge…');
  }

  /** Manual "retry" affordance — same as onBridgeLinkClick but also
   * fires from the small refresh button next to the down hint.
   */
  retryBridgeProbe(event: Event): void {
    event.stopPropagation();
    event.preventDefault();
    this.loadBridgeHealth();
  }

  // Per-tracker chip interactions
  toggleChip(name: string): void {
    this.expandedChip.set(this.expandedChip() === name ? null : name);
  }

  reloginTracker(name: string): void {
    // CAPTCHA flow is tracker-specific. For rutracker we already have
    // /api/v1/auth/rutracker/captcha + /login; for others we expose
    // a placeholder for re-login via backend config.
    if (name === 'rutracker') {
      this.http.get<any>('/api/v1/auth/rutracker/captcha').subscribe({
        next: (res) => {
          if (res.authenticated) {
            this.toast.success('Re-authenticated with rutracker');
            this.loadAuthStatus();
          } else if (res.captcha_required) {
            this.toast.info('CAPTCHA required — use the CAPTCHA form');
          } else {
            this.toast.warning(res.message || 'Could not re-login');
          }
        },
        error: (err) => this.toast.error('Re-login failed: ' + (err.error?.detail || err.message)),
      });
    } else {
      this.toast.info(`Manual re-login for ${name} — update credentials in .env and restart the proxy`);
    }
  }

  // qBit logout (clears saved credentials)
  logoutQbit(event: Event): void {
    event.stopPropagation();
    this.http.post<any>('/api/v1/auth/qbittorrent/logout', {}).subscribe({
      next: () => {
        this.toast.success('Logged out of qBittorrent');
        this.qbitAuthenticated.set(false);
        this.qbitUsername.set(null);
        this.loadAuthStatus();
      },
      error: () => this.toast.error('Logout failed'),
    });
  }

  openQbitLogin(): void {
    this.qbitDialog.open(() => this.loadAuthStatus());
  }

  // Search
  doSearch(): void {
    if (this.isSearching()) {
      this.abortSearch();
      return;
    }
    const q = this.query().trim();
    if (!q) return;

    this.isSearching.set(true);
    this.searchStatus.set('Searching...');
    this.results.set([]);
    this.liveResults.set([]);
    this.liveMergedResults.set([]);
    this.searchErrors.set([]);
    this.trackerStats.set([]);

    this.api.search({ query: q, limit: 50, sort_by: this.sortColumn(), sort_order: this.sortDirection() }).subscribe({
      next: (resp) => {
        this.searchId.set(resp.search_id);
        this.searchStatus.set(`Found ${resp.total_results} results...`);
        this.trackerStats.set(((resp as any).tracker_stats as TrackerSearchStat[]) || []);
        if (resp.status === 'completed' && resp.results.length > 0) {
          this.results.set(resp.results);
          this.totalResults.set(resp.total_results);
          this.mergedResults.set(resp.merged_results);
          this.searchErrors.set((resp as any).errors || []);
          this.searchStatus.set(`Found ${resp.total_results} results (${resp.merged_results} merged)`);
          this.isSearching.set(false);
        } else {
          this.connectSse(resp.search_id, resp.stream_token);
        }
      },
      error: (err) => {
        this.toast.error('Search failed: ' + (err.error?.detail || err.message));
        this.isSearching.set(false);
        this.searchStatus.set('Search failed');
      }
    });
  }

  connectSse(searchId: string, token?: string): void {
    this.sse.connect(searchId, token);
    this.sseSub = this.sse.events.subscribe(event => {
      switch (event.event) {
        case 'result_found':
          this.addLiveResult(event.data);
          break;
        case 'merged_update':
          // The de-duplicated set as it builds. Render it directly so
          // the displayed list grows smoothly to the final unique
          // count and never shrinks when the search completes.
          this.liveMergedResults.set(event.data.results ?? []);
          this.searchStatus.set(`Found ${event.data.merged_results} unique results…`);
          break;
        case 'results_update':
          this.searchStatus.set(`Found ${event.data.total_results} results...`);
          break;
        case 'tracker_started':
          this.onTrackerStarted(event.data);
          break;
        case 'tracker_completed':
          this.onTrackerCompleted(event.data);
          break;
        case 'search_complete':
          this.isSearching.set(false);
          if (event.data.total_results > 0) {
            this.searchStatus.set(`Found ${event.data.total_results} results (${event.data.merged_results} merged)`);
            this.loadSearchResults(searchId);
          } else {
            this.searchStatus.set('No results found.');
          }
          this.sse.disconnect();
          break;
        case 'error':
          this.toast.warning('Real-time connection error');
          this.isSearching.set(false);
          this.sse.disconnect();
          break;
      }
    });
  }

  onTrackerStarted(data: any): void {
    if (!data || typeof data.name !== 'string') return;
    this.trackerStats.update(stats => {
      const name = data.name as string;
      const next = stats.slice();
      const idx = next.findIndex(s => s.name === name);
      if (idx >= 0) {
        next[idx] = {
          ...next[idx],
          status: 'running',
          started_at: data.started_at ?? next[idx].started_at,
        };
      } else {
        next.push(this.normaliseStat({ ...data, status: 'running' }));
      }
      return next;
    });
  }

  onTrackerCompleted(data: any): void {
    if (!data || typeof data.name !== 'string') return;
    this.trackerStats.update(stats => {
      const name = data.name as string;
      const next = stats.slice();
      const idx = next.findIndex(s => s.name === name);
      const merged = this.normaliseStat({ ...(idx >= 0 ? next[idx] : {}), ...data });
      if (idx >= 0) {
        next[idx] = merged;
      } else {
        next.push(merged);
      }
      return next;
    });
  }

  private normaliseStat(raw: any): TrackerSearchStat {
    return {
      name: raw.name ?? 'unknown',
      tracker_url: raw.tracker_url ?? '',
      status: (raw.status ?? 'pending') as TrackerSearchStat['status'],
      results_count: raw.results_count ?? 0,
      started_at: raw.started_at ?? null,
      completed_at: raw.completed_at ?? null,
      duration_ms: raw.duration_ms ?? null,
      error: raw.error ?? null,
      error_type: raw.error_type ?? null,
      authenticated: !!raw.authenticated,
      attempt: raw.attempt ?? 1,
      http_status: raw.http_status ?? null,
      category: raw.category ?? 'all',
      query: raw.query ?? '',
      notes: raw.notes ?? {},
    };
  }

  trackStatByName(_i: number, s: TrackerSearchStat): string {
    return s.name;
  }

  openTrackerStatDialog(stat: TrackerSearchStat): void {
    this.trackerStatDialog?.open(stat);
  }

  loadSearchResults(searchId: string): void {
    this.api.getSearch(searchId).subscribe(resp => {
      this.results.set(resp.results);
      this.totalResults.set(resp.total_results);
      this.mergedResults.set(resp.merged_results);
      this.searchErrors.set((resp as any).errors || []);
      const stats = (resp as any).tracker_stats as TrackerSearchStat[] | undefined;
      if (stats && stats.length > 0) {
        this.trackerStats.set(stats);
      }
    });
  }

  abortSearch(): void {
    const sid = this.searchId();
    if (sid) {
      this.api.abortSearch(sid).subscribe(() => {
        this.toast.info('Search cancelled');
      });
    }
    this.sse.disconnect();
    this.isSearching.set(false);
    this.searchStatus.set('Search cancelled.');
  }

  addLiveResult(data: any): void {
    const normalized: SearchResult = {
      name: data.name || 'Unknown',
      size: data.size || '0 B',
      seeds: data.seeds || 0,
      leechers: data.leechers || 0,
      tracker: data.tracker || 'unknown',
      download_urls: [data.link || ''],
      sources: [{ tracker: data.tracker || 'unknown', seeds: data.seeds || 0, leechers: data.leechers || 0 }],
      quality: data.quality || 'unknown',
      content_type: data.content_type || 'unknown',
      metadata: null,
      freeleech: false
    };
    // Deduplicate live results on the fly. The SSE stream can emit
    // the same result twice if a poll cycle racing a client
    // reconnection fires — we don't want duplicate rows flashing in
    // the live table. Dedup key: link (primary, magnet hash unique) +
    // tracker + name.
    this.liveResults.update(rows => {
      const key = (r: SearchResult) => `${r.tracker}|${r.download_urls[0] || ''}|${r.name}`;
      const seen = new Set(rows.map(key));
      if (seen.has(key(normalized))) return rows;
      return [...rows, normalized];
    });
    // Keep the running status-line honest with the actual count the
    // UI is showing, not just the backend's total.
    if (this.isSearching()) {
      const n = this.liveResults().length;
      this.searchStatus.set(`Found ${n} result${n === 1 ? '' : 's'}…`);
    }
  }

  // Sorting
  sortResults(column: string): void {
    if (this.sortColumn() === column) {
      this.sortDirection.update(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      this.sortColumn.set(column);
      this.sortDirection.set('desc');
    }
    this.renderSortedResults();
  }

  private _sort(rows: SearchResult[], col: string, dir: 'asc' | 'desc'): SearchResult[] {
    const qw: Record<string, number> = { uhd_8k: 6, uhd_4k: 5, full_hd: 4, hd: 3, sd: 2, unknown: 1 };
    const sorted = [...rows];
    sorted.sort((a, b) => {
      let cmp = 0;
      switch (col) {
        case 'name':
          cmp = (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase());
          break;
        case 'type': {
          const av = a.content_type || 'unknown';
          const bv = b.content_type || 'unknown';
          const unknownFirst = dir === 'desc';
          if (av === 'unknown' && bv !== 'unknown') return unknownFirst ? -1 : 1;
          if (bv === 'unknown' && av !== 'unknown') return unknownFirst ? 1 : -1;
          cmp = av.localeCompare(bv);
          break;
        }
        case 'size':
          cmp = this.parseSize(a.size) - this.parseSize(b.size);
          break;
        case 'seeds':
          cmp = (a.seeds || 0) - (b.seeds || 0);
          break;
        case 'leechers':
          cmp = (a.leechers || 0) - (b.leechers || 0);
          break;
        case 'quality':
          cmp = (qw[a.quality] || 1) - (qw[b.quality] || 1);
          break;
        case 'sources':
          cmp = (a.sources?.length || 0) - (b.sources?.length || 0);
          break;
      }
      return dir === 'asc' ? cmp : -cmp;
    });
    return sorted;
  }

  renderSortedResults(): void {
    // Kept for backward compatibility; the computed signal
    // `sortedResults` does the same work and is what the template uses
    // for rendering. This method also mutates `results` in place so
    // legacy call sites (and existing tests) still see sorted rows.
    const sorted = this._sort(this.results(), this.sortColumn(), this.sortDirection());
    this.results.set(sorted);
  }

  parseSize(sizeStr: string): number {
    if (!sizeStr) return 0;
    const m = sizeStr.match(/([\d.]+)\s*([KMGT]?B)/i);
    if (!m) return 0;
    const val = parseFloat(m[1]);
    const unit = m[2].toUpperCase();
    const mult: Record<string, number> = { B: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3, TB: 1024 ** 4 };
    return val * (mult[unit] || 1);
  }

  formatSize(value: number | string): string {
    if (!value && value !== 0) return '0 B';
    if (typeof value === 'string') {
      if (value.match(/^[\d.]+\s*[KMGT]?B$/i)) return value;
      const num = parseFloat(value);
      if (!isNaN(num)) value = num; else return value || '0 B';
    }
    const bytes = parseFloat(String(value)) || 0;
    if (bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
  }

  getSortClass(col: string): string {
    if (this.sortColumn() !== col) return 'sortable';
    return 'sortable ' + this.sortDirection();
  }

  // trackBy for cdk-virtual-scroll-viewport to avoid re-rendering
  // every row when the underlying array reference changes.
  trackResult = (_index: number, row: SearchResult): string => {
    return (row.name || '') + '|' + (row.size || '') + '|' + (row.download_urls?.[0] || '');
  };

  // Actions
  async doSchedule(index: number): Promise<void> {
    // The grid renders `sortedResults()` (= liveResults() while a search is
    // running, the sorted final list after). The button passes that row's
    // display index, so the handlers MUST resolve the row from the SAME array
    // the template iterates — not `results()`, which is empty during a search
    // and in a different order after. Indexing `results()` made every button a
    // no-op while searching (and acted on the wrong row after a sort).
    const r = this.sortedResults()[index];
    if (!r) return;

    const confirmed = await this.dialog.confirm({
      title: 'Send to qBittorrent?',
      message: `Add "${r.name}" to qBittorrent?`,
      confirmText: 'Send',
      cancelText: 'Cancel'
    });
    if (!confirmed) return;

    if (!this.qbitAuthenticated()) {
      // Capture the ROW object (not the index) for the deferred-login callback:
      // a search can complete WHILE the login dialog is open, at which point
      // sortedResults() pivots from liveResults() to the re-sorted final list —
      // re-resolving by index would then act on a DIFFERENT row than the one the
      // user clicked. The captured `r` is immune to that re-ordering race.
      this.qbitDialog.open(() => { this.loadAuthStatus(); this.executeScheduleRow(r); });
      return;
    }
    this.executeScheduleRow(r);
  }

  // Thin index-based wrapper retained for existing call sites/tests — resolves
  // the displayed row then delegates to the row-based implementation.
  executeSchedule(index: number): void {
    const r = this.sortedResults()[index];
    if (!r) return;
    this.executeScheduleRow(r);
  }

  executeScheduleRow(r: SearchResult): void {
    this.api.download({ result_id: r.name, download_urls: r.download_urls }).subscribe({
      next: (res) => {
        if (res.added_count > 0 || res.status === 'initiated') {
          this.toast.success(`Sent "${r.name}" to qBittorrent`);
        } else if (res.status === 'auth_failed') {
          this.toast.error('qBittorrent auth failed. Please login.');
          // Same row-capture discipline on the auth-failed re-login path.
          this.qbitDialog.open(() => { this.loadAuthStatus(); this.executeScheduleRow(r); });
        } else {
          // Surface real failure reason from backend.
          const detail = (res.results || [])
            .map((x: any) => x.detail || x.message)
            .filter(Boolean)
            .join('; ');
          this.toast.error('Failed to send to qBittorrent' + (detail ? ': ' + detail : ''));
        }
      },
      error: (err) => {
        this.toast.error('Error: ' + (err.error?.error || err.message));
      }
    });
  }

  async doDownload(index: number): Promise<void> {
    const r = this.sortedResults()[index];
    if (!r) return;

    const confirmed = await this.dialog.confirm({
      title: 'Download Torrent?',
      message: `Download "${r.name}"?`,
      confirmText: 'Download',
      cancelText: 'Cancel'
    });
    if (!confirmed) return;

    this.api.downloadFile({ result_id: String(index), download_urls: r.download_urls }).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'download.torrent';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        this.toast.success(`Downloaded "${r.name}"`);
      },
      error: () => {
        this.toast.error('Download failed');
      }
    });
  }

  async doMagnet(index: number): Promise<void> {
    const r = this.sortedResults()[index];
    if (!r) return;
    this.api.generateMagnet({ result_id: r.name, download_urls: r.download_urls }).subscribe({
      next: (res) => {
        this.magnetDialog.open(res.magnet, () => {
          this.api.download({ result_id: String(index), download_urls: [res.magnet] }).subscribe({
            next: (dres) => {
              if (dres.added_count > 0) {
                this.toast.success('Added magnet to qBittorrent');
              } else {
                this.toast.error('Failed to add magnet');
              }
            },
            error: () => this.toast.error('Failed to add magnet')
          });
        });
      },
      error: () => this.toast.error('Failed to generate magnet link')
    });
  }

  // Tab: Downloads
  loadDownloads(): void {
    this.api.getActiveDownloads().subscribe(d => {
      this.activeDownloads.set(d.downloads || []);
    });
  }

  // Tab: Schedules
  loadSchedules(): void {
    this.api.getSchedules().subscribe(s => {
      this.schedules.set(s.schedules || []);
    });
  }

  createSchedule(): void {
    const name = this.schedName().trim();
    const query = this.schedQuery().trim();
    const interval = this.schedInterval();
    if (!name || !query) return;
    this.api.createSchedule({ name, query, interval_minutes: interval }).subscribe({
      next: () => {
        this.toast.success('Schedule created');
        this.schedName.set('');
        this.schedQuery.set('');
        this.loadSchedules();
      },
      error: () => this.toast.error('Failed to create schedule')
    });
  }

  deleteSchedule(id: string): void {
    this.api.deleteSchedule(id).subscribe({
      next: () => {
        this.toast.success('Schedule deleted');
        this.loadSchedules();
      },
      error: () => this.toast.error('Failed to delete schedule')
    });
  }

  // Tab: Hooks
  loadHooks(): void {
    this.api.getHooks().subscribe(h => {
      this.hooks.set(h.hooks || []);
    });
  }

  deleteHook(id: string): void {
    this.api.deleteHook(id).subscribe({
      next: () => {
        this.toast.success('Hook deleted');
        this.loadHooks();
      },
      error: () => this.toast.error('Failed to delete hook')
    });
  }

  // Tab switch
  switchTab(tab: string): void {
    this.activeTab.set(tab);
    if (tab === 'downloads') this.loadDownloads();
    if (tab === 'trackers') this.loadStats();
    if (tab === 'schedules') this.loadSchedules();
    if (tab === 'hooks') this.loadHooks();
  }

  downloadStateClass(state: string): string {
    if (['stalledDL', 'forcedDL', 'downloading'].includes(state)) return 'downloading';
    if (['uploading', 'stalledUP', 'forcedUP'].includes(state)) return 'seeding';
    if (['pausedDL', 'pausedUP'].includes(state)) return 'paused';
    return 'unknown';
  }

  formatEta(seconds: number): string {
    if (seconds >= 8640000) return '-';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return (h > 0 ? h + 'h ' : '') + (m > 0 ? m + 'm ' : '') + s + 's';
  }

  // Helpers
  sourceStats(sources: Source[] | undefined | null): SourceStats {
    if (!sources?.length) return { isMerged: false, trackers: [] };
    const counts: Record<string, number> = {};
    for (const s of sources) {
      const t = s.tracker || 'unknown';
      counts[t] = (counts[t] || 0) + 1;
    }
    const names = Object.keys(counts);
    const isMerged = names.length > 1 || sources.length > 1;
    const trackers = names.map(name => ({
      name,
      count: counts[name],
      isFree: name.includes('[free]'),
    }));
    return { isMerged, trackers };
  }

  // Legacy helper retained so existing tests continue to pass.  The
  // template itself no longer uses [innerHTML]; it renders the
  // ``sourceStats()`` output via Angular bindings.
  trackerHtml(sources: Source[]): string {
    const stats = this.sourceStats(sources);
    if (!stats.trackers.length) return '';
    let html = '';
    if (stats.isMerged) {
      html += '<span class="merged-indicator"><span class="merge-icon">&#x2697;</span>Merged</span>';
    }
    for (const t of stats.trackers) {
      const cls = t.isFree ? 'tracker-tag freeleech' : 'tracker-tag';
      const suffix = t.count > 1 ? ` (x${t.count})` : '';
      html += `<span class="${cls}">${t.name}${suffix}</span>`;
    }
    return html;
  }

  escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}
