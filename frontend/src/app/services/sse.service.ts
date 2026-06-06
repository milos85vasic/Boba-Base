import { Injectable, inject, DestroyRef } from '@angular/core';
import { Subject, Observable } from 'rxjs';

export interface SseEvent {
  event: string;
  data: any;
}

@Injectable({ providedIn: 'root' })
export class SseService {
  private destroyRef = inject(DestroyRef);
  private eventSource?: EventSource;
  private events$ = new Subject<SseEvent>();

  events: Observable<SseEvent> = this.events$.asObservable();

  connect(searchId: string, token?: string): void {
    this.disconnect();
    // EventSource can't set headers, so the per-search bearer token
    // (CONTINUATION #6) rides as a query param. Harmless when the server
    // doesn't require it; required when SSE_REQUIRE_TOKEN is enabled.
    const query = token ? `?token=${encodeURIComponent(token)}` : '';
    const url = `/api/v1/search/stream/${searchId}${query}`;
    this.eventSource = new EventSource(url);

    this.eventSource.onopen = () => {
      this.events$.next({ event: 'connected', data: {} });
    };

    this.eventSource.addEventListener('search_start', (e: MessageEvent) => {
      this.events$.next({ event: 'search_start', data: this.safeParse(e.data) });
    });

    this.eventSource.addEventListener('result_found', (e: MessageEvent) => {
      this.events$.next({ event: 'result_found', data: this.safeParse(e.data) });
    });

    this.eventSource.addEventListener('results_update', (e: MessageEvent) => {
      this.events$.next({ event: 'results_update', data: this.safeParse(e.data) });
    });

    this.eventSource.addEventListener('search_complete', (e: MessageEvent) => {
      this.events$.next({ event: 'search_complete', data: this.safeParse(e.data) });
    });

    this.eventSource.addEventListener('download_start', (e: MessageEvent) => {
      this.events$.next({ event: 'download_start', data: this.safeParse(e.data) });
    });

    this.eventSource.addEventListener('download_progress', (e: MessageEvent) => {
      this.events$.next({ event: 'download_progress', data: this.safeParse(e.data) });
    });

    this.eventSource.addEventListener('download_complete', (e: MessageEvent) => {
      this.events$.next({ event: 'download_complete', data: this.safeParse(e.data) });
    });

    this.eventSource.onerror = (err) => {
      this.events$.next({ event: 'error', data: err });
    };
  }

  disconnect(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = undefined;
    }
  }

  private safeParse(data: string): any {
    try {
      return JSON.parse(data);
    } catch {
      return data;
    }
  }
}
