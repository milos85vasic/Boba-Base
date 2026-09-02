export interface SearchRequest {
  query: string;
  category?: string;
  limit?: number;
  enable_metadata?: boolean;
  validate_trackers?: boolean;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export interface SearchResponse {
  search_id: string;
  query: string;
  status: string;
  results: SearchResult[];
  total_results: number;
  merged_results: number;
  trackers_searched: string[];
  tracker_stats?: TrackerSearchStat[];
  started_at: string;
  completed_at?: string;
  /** Per-search SSE bearer token (CONTINUATION #6); pass to the stream URL. */
  stream_token?: string;
}

export interface TrackerSearchStat {
  name: string;
  tracker_url: string;
  status: 'pending' | 'running' | 'success' | 'empty' | 'error' | 'timeout' | 'cancelled';
  results_count: number;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  error: string | null;
  error_type: string | null;
  /** A real session exists for this tracker (login succeeded, or the
   *  operator exported a browser cookie carrying the session key). */
  authenticated: boolean;
  /** Credentials/cookies are PRESENT in the service environment — something
   *  to log in with, which is not the same as having logged in (BOB-173). */
  credentials_configured: boolean;
  attempt: number;
  http_status: number | null;
  category: string;
  query: string;
  notes: Record<string, unknown>;
}

export interface SearchResult {
  name: string;
  size: string;
  seeds: number;
  leechers: number;
  download_urls: string[];
  quality: string;
  content_type: string;
  desc_link?: string;
  tracker?: string;
  sources: Source[];
  metadata?: Metadata | null;
  freeleech: boolean;
}

export interface Source {
  tracker: string;
  seeds: number;
  leechers: number;
}

export interface Metadata {
  source: string;
  title: string;
  year?: number;
  content_type?: string;
  poster_url?: string;
  overview?: string;
  genres?: string[];
}

export interface TrackerStatus {
  name: string;
  url: string;
  enabled: boolean;
  health_status: string;
  last_checked?: string;
}

export interface DownloadRequest {
  result_id: string;
  download_urls: string[];

  // Content facts forwarded so the backend can tag the torrent in qBittorrent
  // (type / quality / year / genre, plus the Boba promotion tags).
  //
  // Added 2026-09-01. The backend gained these fields but NO client sent them,
  // so three of the four operator-chosen tag dimensions were unreachable and
  // every download landed with only a name-derived quality tag. The search
  // result the user clicked already carries all of this — it was simply being
  // discarded at the download call.
  title?: string;
  content_type?: string;
  year?: number;
  genres?: string[];
}

export interface DownloadResponse {
  download_id: string;
  status: string;
  urls_count: number;
  added_count: number;
  results: DownloadResult[];
}

export interface DownloadResult {
  url: string;
  status: string;
  method?: string;
  detail?: string;
  message?: string;
}

export interface ActiveDownload {
  name: string;
  size: number;
  progress: number;
  dlspeed: number;
  upspeed: number;
  state: string;
  hash: string;
  eta: number;
}

export interface Schedule {
  id: string;
  name: string;
  query: string;
  interval_minutes: number;
  status: string;
  last_run?: string;
  next_run?: string;
}

export interface Hook {
  hook_id: string;
  name: string;
  event: string;
  script_path: string;
  enabled: boolean;
  created_at?: string;
}

export interface AuthStatus {
  trackers: Record<string, {
    authenticated?: boolean;
    has_session?: boolean;
    username?: string;
    base_url?: string;
  }>;
}

export interface QbitCredentials {
  username: string;
  password: string;
  save?: boolean;
}

export interface MagnetResponse {
  magnet: string;
  hashes: string[];
}

export interface StatsResponse {
  active_searches: number;
  completed_searches: number;
  trackers_count: number;
  trackers?: TrackerStatus[];
}

export interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'warning' | 'info';
  duration?: number;
}
