/**
 * @fileoverview Typed event emitter for BobaLink.
 *
 * Provides a type-safe event system for cross-component communication
 * within the extension. Used by scanners, API clients, and UI components
 * to emit and listen for domain-specific events.
 *
 * @module shared/events
 */

/** Event name to payload type mapping. */
export interface EventMap {
  "torrent-detected": {
    id: string;
    type: "magnet" | "torrent-file";
    displayName: string;
    url: string;
  };
  "scan-started": { url: string; timestamp: number };
  "scan-completed": {
    url: string;
    magnetCount: number;
    torrentFileCount: number;
    durationMs: number;
  };
  "scan-error": { url: string; error: string };
  "send-started": { ids: readonly string[] };
  "send-completed": { results: ReadonlyArray<{ id: string; success: boolean }> };
  "send-error": { id: string; error: string };
  "auth-state-changed": {
    method: string;
    authenticated: boolean;
  };
  "connection-status": {
    serverId: string;
    connected: boolean;
    latency: number | null;
  };
  "config-changed": { key: string; newValue: unknown; oldValue: unknown };
  "queue-updated": { size: number };
  "badge-update": { count: number; color: string };
  "notification": { title: string; message: string; type: "info" | "success" | "warning" | "error" };
}

/** Valid event names derived from EventMap. */
export type EventName = keyof EventMap;

/** Listener function type for a specific event. */
export type EventListener<T extends EventName> = (payload: EventMap[T]) => void;

/**
 * Lightweight typed event emitter implementation.
 *
 * Provides subscribe/emit/unsubscribe semantics with full type safety.
 * Does not extend EventTarget to avoid DOM dependency in service worker.
 *
 * @example
 * ```typescript
 * const events = new TypedEventEmitter();
 * const unsub = events.on("torrent-detected", (data) => {
 *   console.log(`Found: ${data.displayName}`);
 * });
 * events.emit("torrent-detected", { id: "1", type: "magnet", displayName: "Test", url: "magnet:..." });
 * unsub(); // Remove listener
 * ```
 */
export class TypedEventEmitter {
  /** Map of event names to sets of listener functions. */
  private readonly listeners: Map<
    EventName,
    Set<EventListener<EventName>>
  > = new Map();

  /**
   * Register a listener for a specific event.
   *
   * @param event - The event name to listen for
   * @param listener - The callback function to invoke
   * @returns Unsubscribe function to remove the listener
   */
  on<T extends EventName>(event: T, listener: EventListener<T>): () => void {
    const existing = this.listeners.get(event);
    if (existing) {
      existing.add(listener as EventListener<EventName>);
    } else {
      this.listeners.set(event, new Set([listener as EventListener<EventName>]));
    }

    // Return unsubscribe function
    return (): void => {
      const set = this.listeners.get(event);
      if (set) {
        set.delete(listener as EventListener<EventName>);
        if (set.size === 0) {
          this.listeners.delete(event);
        }
      }
    };
  }

  /**
   * Register a one-time listener that auto-removes after first invocation.
   *
   * @param event - The event name to listen for
   * @param listener - The callback function to invoke once
   */
  once<T extends EventName>(event: T, listener: EventListener<T>): void {
    const onceWrapper = (payload: EventMap[T]): void => {
      unsub();
      listener(payload);
    };
    const unsub = this.on(event, onceWrapper);
  }

  /**
   * Emit an event with a payload to all registered listeners.
   *
   * @param event - The event name to emit
   * @param payload - The event payload data
   */
  emit<T extends EventName>(event: T, payload: EventMap[T]): void {
    const set = this.listeners.get(event);
    if (!set) return;

    // Create a copy to safely iterate even if listeners are removed during emit
    const listeners = Array.from(set);
    for (const listener of listeners) {
      try {
        listener(payload);
      } catch (err) {
        // Log but don't let listener errors break other listeners
        console.error(`Error in event listener for "${event}":`, err);
      }
    }
  }

  /**
   * Remove all listeners for a specific event, or all listeners entirely.
   *
   * @param event - Optional event name to clear; if omitted, clears all
   */
  off(event?: EventName): void {
    if (event) {
      this.listeners.delete(event);
    } else {
      this.listeners.clear();
    }
  }

  /**
   * Get the number of listeners registered for an event.
   *
   * @param event - The event name to check
   * @returns Number of active listeners
   */
  listenerCount(event: EventName): number {
    return this.listeners.get(event)?.size ?? 0;
  }

  /**
   * Check if there are any listeners for a given event.
   *
   * @param event - The event name to check
   * @returns True if at least one listener is registered
   */
  hasListeners(event: EventName): boolean {
    return (this.listeners.get(event)?.size ?? 0) > 0;
  }
}

/**
 * Global event emitter instance used across the extension.
 * Service worker and content scripts create their own instances.
 */
export const globalEvents = new TypedEventEmitter();
