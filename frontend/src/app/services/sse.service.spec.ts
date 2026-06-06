import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { SseService, type SseEvent } from './sse.service';

// Minimal EventSource mock capturing registered listeners so tests can
// trigger them synchronously via dispatch().
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  readyState = 0;
  onopen: ((e: Event) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  listeners: Record<string, Array<(e: MessageEvent) => void>> = {};
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(name: string, cb: (e: MessageEvent) => void): void {
    (this.listeners[name] ||= []).push(cb);
  }

  removeEventListener(): void { /* no-op */ }

  close(): void {
    this.closed = true;
    this.readyState = 2;
  }

  dispatch(name: string, data: unknown): void {
    const payload = typeof data === 'string' ? data : JSON.stringify(data);
    const me = new MessageEvent(name, { data: payload });
    for (const cb of this.listeners[name] ?? []) cb(me);
  }

  triggerOpen(): void {
    this.onopen?.(new Event('open'));
  }

  triggerError(): void {
    this.onerror?.(new Event('error'));
  }
}

describe('SseService', () => {
  let svc: SseService;
  let originalES: typeof globalThis.EventSource;

  beforeEach(() => {
    originalES = globalThis.EventSource;
    MockEventSource.instances = [];
    (globalThis as unknown as { EventSource: typeof MockEventSource }).EventSource = MockEventSource;
    TestBed.configureTestingModule({});
    svc = TestBed.inject(SseService);
  });

  afterEach(() => {
    (globalThis as unknown as { EventSource: typeof EventSource | undefined }).EventSource = originalES;
  });

  it('connect() opens an EventSource pointed at the stream URL', () => {
    svc.connect('abc');
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe('/api/v1/search/stream/abc');
  });

  it('connect() appends the SSE bearer token as a query param', () => {
    svc.connect('abc', 'tok-123');
    expect(MockEventSource.instances[0].url).toBe('/api/v1/search/stream/abc?token=tok-123');
  });

  it('connect() url-encodes the token', () => {
    svc.connect('abc', 'a b/c+d');
    expect(MockEventSource.instances[0].url).toBe('/api/v1/search/stream/abc?token=a%20b%2Fc%2Bd');
  });

  it('onopen emits a connected event', () => {
    const events: SseEvent[] = [];
    svc.events.subscribe(e => events.push(e));
    svc.connect('abc');
    MockEventSource.instances[0].triggerOpen();
    expect(events.map(e => e.event)).toContain('connected');
  });

  it('dispatches parsed JSON for named events', () => {
    const events: SseEvent[] = [];
    svc.events.subscribe(e => events.push(e));
    svc.connect('abc');
    const es = MockEventSource.instances[0];

    es.dispatch('search_start', { search_id: 'abc' });
    es.dispatch('result_found', { name: 'r' });
    es.dispatch('results_update', { total_results: 1 });
    es.dispatch('search_complete', { total_results: 1, merged_results: 0 });
    es.dispatch('download_start', { id: 'd' });
    es.dispatch('download_progress', { pct: 50 });
    es.dispatch('download_complete', { id: 'd' });

    const names = events.map(e => e.event);
    expect(names).toContain('search_start');
    expect(names).toContain('result_found');
    expect(names).toContain('results_update');
    expect(names).toContain('search_complete');
    expect(names).toContain('download_start');
    expect(names).toContain('download_progress');
    expect(names).toContain('download_complete');

    const startEvt = events.find(e => e.event === 'search_start');
    expect(startEvt?.data).toEqual({ search_id: 'abc' });
  });

  it('returns the raw string when payload is not JSON', () => {
    const events: SseEvent[] = [];
    svc.events.subscribe(e => events.push(e));
    svc.connect('abc');
    MockEventSource.instances[0].dispatch('search_start', '<<not-json>>');
    const startEvt = events.find(e => e.event === 'search_start');
    expect(startEvt?.data).toBe('<<not-json>>');
  });

  it('onerror emits an error event carrying the error object', () => {
    const events: SseEvent[] = [];
    svc.events.subscribe(e => events.push(e));
    svc.connect('abc');
    MockEventSource.instances[0].triggerError();
    expect(events.some(e => e.event === 'error')).toBe(true);
  });

  it('disconnect() closes the underlying EventSource', () => {
    svc.connect('abc');
    const es = MockEventSource.instances[0];
    svc.disconnect();
    expect(es.closed).toBe(true);
  });

  it('disconnect() without an active connection is a no-op', () => {
    expect(() => svc.disconnect()).not.toThrow();
  });

  it('connect() replaces an existing connection', () => {
    svc.connect('one');
    const firstInstance = MockEventSource.instances[0];
    svc.connect('two');
    expect(firstInstance.closed).toBe(true);
    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[1].url).toBe('/api/v1/search/stream/two');
  });

  it('events observable is a multicast of the shared subject', () => {
    const a: SseEvent[] = [];
    const b: SseEvent[] = [];
    svc.events.subscribe(e => a.push(e));
    svc.events.subscribe(e => b.push(e));
    svc.connect('abc');
    MockEventSource.instances[0].dispatch('result_found', { name: 'x' });
    expect(a).toHaveLength(1);
    expect(b).toHaveLength(1);
  });
});
