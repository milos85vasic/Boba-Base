/**
 * @fileoverview Anti-bluff unit tests for the REAL utils module.
 *
 * Imports the production `src/shared/utils.ts`. Asserts user-observable
 * behaviour: debounce coalesces calls, throttle caps frequency, TokenBucket
 * exhausts + refills, retryWithBackoff retries then succeeds, formatBytes
 * renders human units, url helpers validate, escapeHtml neutralizes markup,
 * processInChunks visits every item.
 *
 * @module tests/unit/utils.test
 */

import { describe, it, expect, vi } from "vitest";
import {
  debounce,
  throttle,
  generateId,
  truncate,
  escapeHtml,
  retryWithBackoff,
  TokenBucket,
  isValidHttpUrl,
  getDomain,
  formatBytes,
  deepClone,
  arraysEqual,
  processInChunks,
} from "../../src/shared/utils";

describe("debounce", () => {
  it("fires once with the latest args after the delay", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const d = debounce(fn, 100);
    d("a");
    d("ab");
    vi.advanceTimersByTime(100);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("ab");
    vi.useRealTimers();
  });

  it("cancel() prevents a pending call", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const d = debounce(fn, 100);
    d("x");
    d.cancel();
    vi.advanceTimersByTime(200);
    expect(fn).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});

describe("throttle", () => {
  it("invokes immediately then drops calls within the interval", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const t = throttle(fn, 100);
    t("a");
    t("b");
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("a");
    vi.advanceTimersByTime(100);
    expect(fn).toHaveBeenCalledTimes(2); // trailing call fires
    vi.useRealTimers();
  });
});

describe("TokenBucket", () => {
  it("allows up to capacity then refuses", () => {
    const b = new TokenBucket(2, 1);
    expect(b.consume()).toBe(true);
    expect(b.consume()).toBe(true);
    expect(b.consume()).toBe(false);
  });

  it("refills over time", () => {
    vi.useFakeTimers();
    const b = new TokenBucket(1, 10); // 10 tokens/sec
    expect(b.consume()).toBe(true);
    expect(b.consume()).toBe(false);
    vi.advanceTimersByTime(200); // 0.2s * 10 = 2 tokens, capped at 1
    expect(b.consume()).toBe(true);
    vi.useRealTimers();
  });
});

describe("retryWithBackoff", () => {
  it("retries on failure then returns the eventual success", async () => {
    vi.useFakeTimers();
    let calls = 0;
    const fn = vi.fn(() => {
      calls += 1;
      if (calls < 3) return Promise.reject(new Error("fail"));
      return Promise.resolve("ok");
    });
    const p = retryWithBackoff(fn, 5, 10, 100);
    await vi.runAllTimersAsync();
    await expect(p).resolves.toBe("ok");
    expect(fn).toHaveBeenCalledTimes(3);
    vi.useRealTimers();
  });

  it("throws the last error after exhausting retries", async () => {
    vi.useFakeTimers();
    const fn = vi.fn(() => Promise.reject(new Error("always")));
    const p = retryWithBackoff(fn, 1, 10, 100);
    const assertion = expect(p).rejects.toThrow("always");
    await vi.runAllTimersAsync();
    await assertion;
    expect(fn).toHaveBeenCalledTimes(2); // initial + 1 retry
    vi.useRealTimers();
  });
});

describe("string + url helpers", () => {
  it("truncate adds ellipsis past maxLength", () => {
    expect(truncate("hello world", 8)).toBe("hello...");
    expect(truncate("short", 10)).toBe("short");
  });

  it("escapeHtml neutralizes markup (XSS-safe)", () => {
    const out = escapeHtml('<img src=x onerror="alert(1)">');
    expect(out).not.toContain("<img");
    expect(out).toContain("&lt;img");
  });

  it("isValidHttpUrl accepts http(s) and rejects others", () => {
    expect(isValidHttpUrl("http://localhost:7187")).toBe(true);
    expect(isValidHttpUrl("https://example.com")).toBe(true);
    expect(isValidHttpUrl("magnet:?xt=urn:btih:abc")).toBe(false);
    expect(isValidHttpUrl("not a url")).toBe(false);
  });

  it("getDomain extracts hostname or empty string", () => {
    expect(getDomain("https://rutracker.org/forum")).toBe("rutracker.org");
    expect(getDomain("garbage")).toBe("");
  });

  it("generateId returns unique non-empty strings", () => {
    expect(generateId()).not.toBe(generateId());
    expect(generateId().length).toBeGreaterThan(0);
  });
});

describe("formatBytes + collection helpers", () => {
  it("formatBytes renders human-readable units", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(1073741824)).toBe("1 GB");
  });

  it("deepClone produces an independent copy", () => {
    const src = { a: { b: 1 } };
    const clone = deepClone(src);
    clone.a.b = 2;
    expect(src.a.b).toBe(1);
  });

  it("arraysEqual compares shallowly", () => {
    expect(arraysEqual([1, 2, 3], [1, 2, 3])).toBe(true);
    expect(arraysEqual([1, 2], [1, 2, 3])).toBe(false);
    expect(arraysEqual([1, 2], [1, 9])).toBe(false);
  });

  it("processInChunks visits every item", async () => {
    const seen: number[] = [];
    await processInChunks([1, 2, 3, 4, 5], (n) => seen.push(n), 2);
    expect(seen).toEqual([1, 2, 3, 4, 5]);
  });
});
