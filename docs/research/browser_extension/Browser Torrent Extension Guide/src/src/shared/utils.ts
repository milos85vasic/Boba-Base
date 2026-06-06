/**
 * @fileoverview Utility functions for BobaLink.
 *
 * Provides debounce, throttle, hash functions, string helpers,
 * and other shared utilities used across the extension.
 *
 * @module shared/utils
 */

/**
 * Debounce a function call.
 * Delays execution until after `delay` ms have elapsed since the last call.
 *
 * @param fn - The function to debounce
 * @param delay - Delay in milliseconds
 * @returns Debounced function with a `cancel` method
 *
 * @example
 * ```typescript
 * const debounced = debounce((text) => search(text), 300);
 * debounced("a");
 * debounced("ab"); // resets timer
 * // Only "ab" search executes after 300ms of no calls
 * ```
 */
export function debounce<T extends unknown[]>(
  fn: (...args: T) => void,
  delay: number,
): { (...args: T): void; cancel(): void } {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  const debounced = (...args: T): void => {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }
    timeoutId = setTimeout(() => {
      timeoutId = null;
      fn(...args);
    }, delay);
  };

  debounced.cancel = (): void => {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };

  return debounced;
}

/**
 * Throttle a function call.
 * Ensures the function is called at most once per `interval` ms.
 *
 * @param fn - The function to throttle
 * @param interval - Minimum interval between calls in milliseconds
 * @returns Throttled function with a `cancel` method
 *
 * @example
 * ```typescript
 * const throttled = throttle(() => updateUI(), 100);
 * // updateUI called at most every 100ms regardless of call frequency
 * ```
 */
export function throttle<T extends unknown[]>(
  fn: (...args: T) => void,
  interval: number,
): { (...args: T): void; cancel(): void } {
  let lastCall = 0;
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  const throttled = (...args: T): void => {
    const now = Date.now();
    const remaining = interval - (now - lastCall);

    if (remaining <= 0) {
      // Enough time has passed, call immediately
      if (timeoutId !== null) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
      lastCall = now;
      fn(...args);
    } else if (timeoutId === null) {
      // Schedule a call for when the interval expires
      timeoutId = setTimeout(() => {
        timeoutId = null;
        lastCall = Date.now();
        fn(...args);
      }, remaining);
    }
    // If timeoutId is already set, drop this call
  };

  throttled.cancel = (): void => {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };

  return throttled;
}

/**
 * Generate a unique identifier string.
 * Uses crypto.randomUUID if available, falls back to a timestamp + random.
 *
 * @returns Unique identifier string
 */
export function generateId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }

  // Fallback for environments without randomUUID
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 10);
  const random2 = Math.random().toString(36).slice(2, 10);
  return `${timestamp}-${random}-${random2}`;
}

/**
 * Truncate a string to a maximum length with ellipsis.
 *
 * @param str - String to truncate
 * @param maxLength - Maximum length
 * @returns Truncated string with "..." if truncated
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + "...";
}

/**
 * Escape HTML special characters to prevent XSS.
 *
 * @param text - Raw text that may contain HTML
 * @returns Escaped text safe for HTML insertion
 */
export function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Sleep for a specified number of milliseconds.
 *
 * @param ms - Milliseconds to sleep
 * @returns Promise that resolves after the delay
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Retry an async function with exponential backoff.
 *
 * @param fn - Async function to retry
 * @param maxRetries - Maximum number of retries
 * @param baseDelay - Initial delay in milliseconds
 * @param maxDelay - Maximum delay in milliseconds
 * @returns Result of the function
 * @throws The last error if all retries fail
 */
export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries: number = 3,
  baseDelay: number = 1000,
  maxDelay: number = 30000,
): Promise<T> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));

      if (attempt < maxRetries) {
        // Calculate delay with exponential backoff and jitter
        const exponentialDelay = baseDelay * Math.pow(2, attempt);
        const clampedDelay = Math.min(exponentialDelay, maxDelay);
        const jitter = Math.random() * 0.3 * clampedDelay;
        const delay = clampedDelay + jitter;

        await sleep(delay);
      }
    }
  }

  throw lastError ?? new Error("Retry failed with unknown error");
}

/**
 * Simple token bucket rate limiter.
 */
export class TokenBucket {
  private tokens: number;
  private lastRefill: number;

  /**
   * Create a token bucket rate limiter.
   *
   * @param capacity - Maximum number of tokens (requests allowed in burst)
   * @param refillRate - Tokens added per second
   */
  constructor(
    private readonly capacity: number,
    private readonly refillRate: number,
  ) {
    this.tokens = capacity;
    this.lastRefill = Date.now();
  }

  /**
   * Try to consume a token.
   *
   * @returns True if a token was consumed (request allowed)
   */
  consume(): boolean {
    this.refill();

    if (this.tokens >= 1) {
      this.tokens -= 1;
      return true;
    }
    return false;
  }

  /**
   * Get the number of available tokens.
   *
   * @returns Current token count
   */
  getAvailableTokens(): number {
    this.refill();
    return this.tokens;
  }

  /**
   * Refill tokens based on elapsed time.
   */
  private refill(): void {
    const now = Date.now();
    const elapsedMs = now - this.lastRefill;
    const tokensToAdd = (elapsedMs / 1000) * this.refillRate;

    this.tokens = Math.min(this.capacity, this.tokens + tokensToAdd);
    this.lastRefill = now;
  }
}

/**
 * Yield to the browser to prevent blocking the main thread.
 * Uses requestAnimationFrame or setTimeout depending on environment.
 *
 * @returns Promise that resolves after yielding
 */
export function yieldToBrowser(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame !== "undefined") {
      requestAnimationFrame(() => resolve());
    } else {
      setTimeout(resolve, 0);
    }
  });
}

/**
 * Process an array in chunks, yielding between chunks.
 * Prevents UI blocking during large array operations.
 *
 * @param items - Items to process
 * @param processor - Function to process each item
 * @param chunkSize - Number of items per chunk
 */
export async function processInChunks<T>(
  items: readonly T[],
  processor: (item: T) => void,
  chunkSize: number = 50,
): Promise<void> {
  for (let i = 0; i < items.length; i += chunkSize) {
    const chunk = items.slice(i, i + chunkSize);
    for (const item of chunk) {
      processor(item);
    }
    if (i + chunkSize < items.length) {
      await yieldToBrowser();
    }
  }
}

/**
 * Check if a URL is valid and uses HTTP(S).
 *
 * @param url - URL string to validate
 * @returns True if valid HTTP(S) URL
 */
export function isValidHttpUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * Get the base domain from a URL.
 *
 * @param url - URL to extract domain from
 * @returns Domain name (e.g., "example.com")
 */
export function getDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

/**
 * Format bytes to human-readable string.
 *
 * @param bytes - Number of bytes
 * @param decimals - Decimal places to show
 * @returns Formatted string (e.g., "1.5 GB")
 */
export function formatBytes(bytes: number, decimals: number = 2): string {
  if (bytes === 0) return "0 B";

  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB", "PB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const size = Math.min(i, sizes.length - 1);

  return `${parseFloat((bytes / Math.pow(k, size)).toFixed(decimals))} ${sizes[size]}`;
}

/**
 * Deep clone a JSON-serializable object.
 *
 * @param obj - Object to clone
 * @returns Deep clone of the object
 */
export function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj)) as T;
}

/**
 * Compare two arrays for equality (shallow).
 *
 * @param a - First array
 * @param b - Second array
 * @returns True if arrays have same length and elements
 */
export function arraysEqual<T>(a: readonly T[], b: readonly T[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}
