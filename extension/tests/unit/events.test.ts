/**
 * @fileoverview Anti-bluff unit tests for the REAL TypedEventEmitter.
 *
 * Imports the production `src/shared/events.ts`. Asserts user-observable
 * outcomes: a registered listener actually receives the emitted payload;
 * unsubscribe stops delivery; once fires exactly once; a throwing listener is
 * isolated; off() clears; counts are accurate.
 *
 * @module tests/unit/events.test
 */

import { describe, it, expect, vi } from "vitest";
import { TypedEventEmitter, globalEvents } from "../../src/shared/events";

describe("TypedEventEmitter", () => {
  it("delivers the exact emitted payload to a registered listener", () => {
    const e = new TypedEventEmitter();
    const received: unknown[] = [];
    e.on("queue-updated", (p) => received.push(p));
    e.emit("queue-updated", { size: 3 });
    expect(received).toEqual([{ size: 3 }]);
  });

  it("on() returns an unsubscribe that stops further delivery", () => {
    const e = new TypedEventEmitter();
    const fn = vi.fn();
    const unsub = e.on("queue-updated", fn);
    e.emit("queue-updated", { size: 1 });
    unsub();
    e.emit("queue-updated", { size: 2 });
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith({ size: 1 });
  });

  it("once() fires exactly once then auto-removes", () => {
    const e = new TypedEventEmitter();
    const fn = vi.fn();
    e.once("queue-updated", fn);
    e.emit("queue-updated", { size: 1 });
    e.emit("queue-updated", { size: 2 });
    expect(fn).toHaveBeenCalledTimes(1);
    expect(e.listenerCount("queue-updated")).toBe(0);
  });

  it("isolates a throwing listener so others still run", () => {
    const e = new TypedEventEmitter();
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const good = vi.fn();
    e.on("queue-updated", () => {
      throw new Error("listener boom");
    });
    e.on("queue-updated", good);
    e.emit("queue-updated", { size: 9 });
    expect(good).toHaveBeenCalledWith({ size: 9 });
    expect(errSpy).toHaveBeenCalled();
    errSpy.mockRestore();
  });

  it("listenerCount / hasListeners reflect registrations", () => {
    const e = new TypedEventEmitter();
    expect(e.hasListeners("scan-started")).toBe(false);
    const unsub = e.on("scan-started", () => {});
    expect(e.listenerCount("scan-started")).toBe(1);
    expect(e.hasListeners("scan-started")).toBe(true);
    unsub();
    expect(e.hasListeners("scan-started")).toBe(false);
  });

  it("off(event) clears one event; off() clears all", () => {
    const e = new TypedEventEmitter();
    e.on("scan-started", () => {});
    e.on("scan-error", () => {});
    e.off("scan-started");
    expect(e.hasListeners("scan-started")).toBe(false);
    expect(e.hasListeners("scan-error")).toBe(true);
    e.off();
    expect(e.hasListeners("scan-error")).toBe(false);
  });

  it("globalEvents is a usable shared singleton", () => {
    const fn = vi.fn();
    const unsub = globalEvents.on("badge-update", fn);
    globalEvents.emit("badge-update", { count: 2, color: "#fff" });
    expect(fn).toHaveBeenCalledWith({ count: 2, color: "#fff" });
    unsub();
  });
});
