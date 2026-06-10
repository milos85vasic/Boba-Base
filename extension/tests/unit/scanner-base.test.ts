/**
 * @fileoverview Anti-bluff unit tests for the REAL BaseScanner (scanner/base.ts).
 *
 * Imports the production `src/scanner/base.ts`. The LOAD-BEARING assertion is the
 * §11.4.115 RED-on-broken-behavior proof for the REFACTORED defect: the reference
 * source derived each detection `id` by appending `Date.now().toString(36)` to the
 * content hash (reference `base.ts:272`), so the SAME torrent produced a DIFFERENT
 * id on every scan — breaking the orchestrator's id-keyed deduplication.
 *
 * The stability tests below assert that the SAME torrent input yields the SAME id
 * across two `createDetectedTorrent` calls, and that two DIFFERENT torrents yield
 * DIFFERENT ids. Against the reference's time-salted `hashString`, the
 * "same torrent → same id" assertion would FAIL (the two ids would differ by the
 * appended `Date.now()` term), which is exactly the RED-on-broken proof this test
 * is written to capture. The anti-bluff step in the agent session re-introduces the
 * `Date.now()` salt and demonstrates this test fails, then restores the fix.
 *
 * @module tests/unit/scanner-base.test
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  BaseScanner,
  DEFAULT_SCANNER_OPTIONS,
  type ScannerOptions,
} from "../../src/scanner/base";
import { TypedEventEmitter } from "../../src/shared/events";
import type { DetectedTorrent, MagnetInfo, TorrentFile } from "../../src/types/torrent";

/**
 * Build a minimal MagnetInfo for tests. Only the identity-bearing fields
 * (uri / infohash) matter for id stability; the rest are filled with inert values.
 */
function makeMagnet(infohash: string, uri?: string): MagnetInfo {
  return {
    uri: uri ?? `magnet:?xt=urn:btih:${infohash}`,
    infohash,
    displayName: null,
    trackers: [],
    webSeeds: [],
    exactLength: null,
    exactSource: null,
    keywords: [],
    acceptableSource: null,
    manifest: null,
    detectedAt: 0,
    sourceElement: null,
  };
}

/** Build a minimal TorrentFile for tests. */
function makeTorrentFile(url: string): TorrentFile {
  return {
    url,
    filename: "x.torrent",
    size: null,
    sameOrigin: false,
    detectedAt: 0,
    sourceElement: null,
  };
}

/**
 * Concrete test subclass exposing the protected surface under test
 * (createDetectedTorrent / computeStableId / executeScan / isActive).
 */
class TestScanner extends BaseScanner {
  getScannerId(): string {
    return "test";
  }

  // Drives the protected executeScan re-entrancy/guard path via a supplied fn.
  async scan(): Promise<readonly DetectedTorrent[]> {
    return this.executeScan(() => Promise.resolve([]));
  }

  // Public passthrough so tests can exercise the protected builder.
  public make(
    type: "magnet" | "torrent-file",
    displayName: string,
    magnet: MagnetInfo | null,
    torrentFile: TorrentFile | null,
  ): DetectedTorrent {
    return this.createDetectedTorrent(type, displayName, magnet, torrentFile);
  }

  // Expose the guarded executeScan with a caller-controlled fn for re-entrancy tests.
  public run(
    fn: () => Promise<readonly DetectedTorrent[]>,
  ): Promise<readonly DetectedTorrent[]> {
    return this.executeScan(fn);
  }

  public expose(): Readonly<ScannerOptions> {
    return this.options;
  }
}

const INFOHASH_A = "0123456789abcdef0123456789abcdef01234567";
const INFOHASH_B = "fedcba9876543210fedcba9876543210fedcba98";

describe("BaseScanner — stable detection id (§11.4.115 refactor proof)", () => {
  let scanner: TestScanner;

  beforeEach(() => {
    scanner = new TestScanner("test", new TypedEventEmitter());
  });

  it("LOAD-BEARING: the SAME magnet torrent yields the SAME id across two calls", () => {
    // Advance the clock between the two detections so a Date.now()-salted id
    // (the reference defect) would necessarily differ. A stable id must not.
    const first = scanner.make("magnet", "Ubuntu 24.04", makeMagnet(INFOHASH_A), null);
    vi.useFakeTimers();
    vi.setSystemTime(new Date(first.detectedAt + 1_000_000));
    const second = scanner.make("magnet", "Ubuntu 24.04", makeMagnet(INFOHASH_A), null);
    vi.useRealTimers();

    expect(second.id).toBe(first.id);
    // detectedAt is allowed to differ (it carries the timestamp); the id is not.
    expect(typeof first.id).toBe("string");
    expect(first.id.length).toBeGreaterThan(0);
  });

  it("two DIFFERENT magnet torrents yield DIFFERENT ids (dedup discriminates)", () => {
    const a = scanner.make("magnet", "A", makeMagnet(INFOHASH_A), null);
    const b = scanner.make("magnet", "B", makeMagnet(INFOHASH_B), null);
    expect(a.id).not.toBe(b.id);
  });

  it("id is identity-based, not display-name based: same infohash, different name → same id", () => {
    const a = scanner.make("magnet", "Some Release 1080p", makeMagnet(INFOHASH_A), null);
    const b = scanner.make("magnet", "totally different label", makeMagnet(INFOHASH_A), null);
    expect(b.id).toBe(a.id);
  });

  it("magnet id is stable across infohash case + surrounding whitespace (normalization)", () => {
    const lower = scanner.make("magnet", "X", makeMagnet(INFOHASH_A), null);
    const upper = scanner.make(
      "magnet",
      "X",
      makeMagnet("  " + INFOHASH_A.toUpperCase() + "  "),
      null,
    );
    expect(upper.id).toBe(lower.id);
  });

  it("torrent-file id is stable across two detections of the same URL", () => {
    const url = "https://example.org/path/ubuntu.torrent";
    const first = scanner.make("torrent-file", "ubuntu.torrent", null, makeTorrentFile(url));
    const second = scanner.make("torrent-file", "ubuntu.torrent", null, makeTorrentFile(url));
    expect(second.id).toBe(first.id);
  });

  it("falls back to display name for id when no magnet/file identity is present", () => {
    const a = scanner.make("magnet", "FallbackName", null, null);
    const b = scanner.make("magnet", "FallbackName", null, null);
    const c = scanner.make("magnet", "OtherName", null, null);
    expect(b.id).toBe(a.id);
    expect(c.id).not.toBe(a.id);
  });

  it("computeStableId is a pure function of identity (containing no Date.now() salt)", () => {
    // Re-deriving the id with a forced clock jump must not change it.
    const original = scanner.make("magnet", "Z", makeMagnet(INFOHASH_A), null).id;
    const realNow = Date.now;
    try {
      // Force Date.now far into the future for any code path that might read it.
      // A correct stable id ignores it entirely.
      (Date as unknown as { now: () => number }).now = () => realNow() + 9_999_999_999;
      const again = scanner.make("magnet", "Z", makeMagnet(INFOHASH_A), null).id;
      expect(again).toBe(original);
    } finally {
      (Date as unknown as { now: () => number }).now = realNow;
    }
  });
});

describe("BaseScanner — DetectedTorrent record shape", () => {
  let scanner: TestScanner;

  beforeEach(() => {
    scanner = new TestScanner("test", new TypedEventEmitter());
  });

  it("produces a well-formed DetectedTorrent with the expected fields", () => {
    const magnet = makeMagnet(INFOHASH_A);
    const before = Date.now();
    const rec = scanner.make("magnet", "Ubuntu", magnet, null);
    const after = Date.now();

    expect(rec).toMatchObject({
      type: "magnet",
      magnet,
      torrentFile: null,
      displayName: "Ubuntu",
      selected: false,
      sent: false,
      sendStatus: null,
    });
    expect(typeof rec.id).toBe("string");
    expect(rec.detectedAt).toBeGreaterThanOrEqual(before);
    expect(rec.detectedAt).toBeLessThanOrEqual(after);
  });

  it("truncates display names longer than 80 chars with an ellipsis", () => {
    const long = "n".repeat(200);
    const rec = scanner.make("magnet", long, makeMagnet(INFOHASH_A), null);
    expect(rec.displayName.length).toBe(83); // 80 + "..."
    expect(rec.displayName.endsWith("...")).toBe(true);
    expect(rec.displayName.startsWith("n".repeat(80))).toBe(true);
  });

  it("does NOT truncate display names of 80 chars or fewer", () => {
    const exact = "n".repeat(80);
    const rec = scanner.make("magnet", exact, makeMagnet(INFOHASH_A), null);
    expect(rec.displayName).toBe(exact);
  });
});

describe("BaseScanner — options + scan lifecycle", () => {
  it("merges partial options over DEFAULT_SCANNER_OPTIONS", () => {
    const s = new TestScanner("test", new TypedEventEmitter(), { maxElements: 5 });
    expect(s.expose()).toEqual({ ...DEFAULT_SCANNER_OPTIONS, maxElements: 5 });
  });

  it("exposes getScannerId", () => {
    const s = new TestScanner("test", new TypedEventEmitter());
    expect(s.getScannerId()).toBe("test");
  });

  it("isActive() is false before/after a scan and true during executeScan", async () => {
    const s = new TestScanner("test", new TypedEventEmitter());
    expect(s.isActive()).toBe(false);

    let activeDuring = false;
    const p = s.run(() => {
      activeDuring = s.isActive();
      return Promise.resolve([]);
    });
    await p;

    expect(activeDuring).toBe(true);
    expect(s.isActive()).toBe(false);
  });

  it("executeScan is re-entrancy guarded: a concurrent call returns [] without running", async () => {
    const s = new TestScanner("test", new TypedEventEmitter());
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const second = vi.fn(() => Promise.resolve([] as readonly DetectedTorrent[]));

    const firstPromise = s.run(async () => {
      await gate;
      return [];
    });
    // While the first scan is parked on the gate, the guard must reject the second.
    const secondResult = await s.run(second);
    expect(secondResult).toEqual([]);
    expect(second).not.toHaveBeenCalled();

    release();
    await firstPromise;
  });

  it("executeScan swallows a thrown error and returns [] (does not reject)", async () => {
    const s = new TestScanner("test", new TypedEventEmitter());
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const result = await s.run(() => Promise.reject(new Error("scan boom")));
    expect(result).toEqual([]);
    expect(errSpy).toHaveBeenCalled();
    errSpy.mockRestore();
    expect(s.isActive()).toBe(false); // finally{} reset the guard
  });
});

afterEach(() => {
  vi.useRealTimers();
});
