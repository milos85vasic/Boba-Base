import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, timeout } from 'rxjs';

const API_TIMEOUT_MS = 15000;
import {
  SearchRequest, SearchResponse, DownloadRequest, DownloadResponse,
  ActiveDownload, Schedule, Hook, AuthStatus, QbitCredentials,
  MagnetResponse, StatsResponse
} from '../models/search.model';
import { API_BASE_URL } from '../config/api-base';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  // BUG-5 (search-flow-audit-20260615): was a hardcoded relative '' which
  // routed every request to the page origin instead of a configured remote
  // API. Now injected + runtime-configurable (see config/api-base.ts).
  private baseUrl = inject(API_BASE_URL);

  search(req: SearchRequest): Observable<SearchResponse> {
    return this.http.post<SearchResponse>(`${this.baseUrl}/api/v1/search`, req).pipe(timeout(API_TIMEOUT_MS));
  }

  getSearch(searchId: string): Observable<SearchResponse> {
    return this.http.get<SearchResponse>(`${this.baseUrl}/api/v1/search/${searchId}`).pipe(timeout(API_TIMEOUT_MS));
  }

  abortSearch(searchId: string): Observable<{ search_id: string; status: string }> {
    return this.http.post<{ search_id: string; status: string }>(`${this.baseUrl}/api/v1/search/${searchId}/abort`, {}).pipe(timeout(API_TIMEOUT_MS));
  }

  download(req: DownloadRequest): Observable<DownloadResponse> {
    return this.http.post<DownloadResponse>(`${this.baseUrl}/api/v1/download`, req).pipe(timeout(API_TIMEOUT_MS));
  }

  downloadFile(req: DownloadRequest): Observable<Blob> {
    return this.http.post(`${this.baseUrl}/api/v1/download/file`, req, { responseType: 'blob' }).pipe(timeout(API_TIMEOUT_MS));
  }

  generateMagnet(req: DownloadRequest): Observable<MagnetResponse> {
    return this.http.post<MagnetResponse>(`${this.baseUrl}/api/v1/magnet`, req).pipe(timeout(API_TIMEOUT_MS));
  }

  getActiveDownloads(): Observable<{ downloads: ActiveDownload[]; count: number }> {
    return this.http.get<{ downloads: ActiveDownload[]; count: number }>(`${this.baseUrl}/api/v1/downloads/active`).pipe(timeout(API_TIMEOUT_MS));
  }

  getSchedules(): Observable<{ schedules: Schedule[] }> {
    return this.http.get<{ schedules: Schedule[] }>(`${this.baseUrl}/api/v1/schedules`).pipe(timeout(API_TIMEOUT_MS));
  }

  createSchedule(schedule: Partial<Schedule>): Observable<Schedule> {
    return this.http.post<Schedule>(`${this.baseUrl}/api/v1/schedules`, schedule).pipe(timeout(API_TIMEOUT_MS));
  }

  deleteSchedule(id: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/api/v1/schedules/${id}`).pipe(timeout(API_TIMEOUT_MS));
  }

  getHooks(): Observable<{ hooks: Hook[]; count: number }> {
    return this.http.get<{ hooks: Hook[]; count: number }>(`${this.baseUrl}/api/v1/hooks`).pipe(timeout(API_TIMEOUT_MS));
  }

  createHook(hook: Partial<Hook>): Observable<Hook> {
    return this.http.post<Hook>(`${this.baseUrl}/api/v1/hooks`, hook).pipe(timeout(API_TIMEOUT_MS));
  }

  deleteHook(id: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/api/v1/hooks/${id}`).pipe(timeout(API_TIMEOUT_MS));
  }

  getAuthStatus(): Observable<AuthStatus> {
    return this.http.get<AuthStatus>(`${this.baseUrl}/api/v1/auth/status`).pipe(timeout(API_TIMEOUT_MS));
  }

  qbitLogin(creds: QbitCredentials): Observable<{ status: string; version?: string; message?: string; error?: string }> {
    return this.http.post<{ status: string; version?: string; message?: string; error?: string }>(`${this.baseUrl}/api/v1/auth/qbittorrent`, creds).pipe(timeout(API_TIMEOUT_MS));
  }

  getStats(): Observable<StatsResponse> {
    return this.http.get<StatsResponse>(`${this.baseUrl}/api/v1/stats`).pipe(timeout(API_TIMEOUT_MS));
  }

  getConfig(): Observable<{ qbittorrent_url: string }> {
    return this.http.get<{ qbittorrent_url: string }>(`${this.baseUrl}/api/v1/config`).pipe(timeout(API_TIMEOUT_MS));
  }
}
