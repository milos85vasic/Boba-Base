/**
 * @fileoverview Phase-2 PERFORMANCE tests for the BobaLink parsers.
 *
 * Anti-bluff (Constitution §11.4 + §11.4.50): these are REAL measured-timing
 * assertions against the project NFRs — not "does it run" smoke checks. Each
 * case:
 *   - imports the REAL committed parser module (no mocks / stubs),
 *   - measures wall-clock time with `performance.now()`,
 *   - WARMS UP first (the first measured run is discarded) and takes the
 *     MEDIAN over several iterations so the verdict is stable across runs
 *     (§11.4.50 deterministic — a single noisy sample is not a verdict),
 *   - asserts the measured number against a threshold calibrated to the NFR
 *     with a documented CI margin, AND
 *   - console.log's a one-line p50/median summary so the timing evidence is
 *     captured in the test output.
 *
 * The thresholds are deliberately CALIBRATED, not loose: a parser regressed to
 * an accidental O(n²) (case 2) or a 10×-slower decode (case 3) FAILS. The
 * anti-bluff proof for the suite is: transiently set a threshold to an
 * absurdly-tight value and observe the test FAIL — proving it really measures.
 *
 * ── NFR sources (docs/browser_extension/_analysis/01-guides-and-plan.md) ──
 *   NFR-002: "Magnet link detection (per link) ≤ 5 ms" — benchmark on a
 *            1,000-link page.
 *   Detection: "pages with 10,000+ links must not cause UI jank (>16 ms frame
 *            time)" — the scanner's per-frame budget; for the PARSERS in
 *            isolation the relevant ceiling is the ≤5 ms/link NFR-002 budget,
 *            of which detect+parse is only a fraction.
 *
 * Runner: Vitest (matches the project's unit suite). Run explicitly:
 *   cd extension && npx vitest run tests/perf/parsers.perf.test.ts
 *
 * @module tests/perf/parsers.perf
 */

import { describe, it, expect } from "vitest";

import { findMagnetUris, parseMagnetUri } from "../../src/parser/magnet";
import { encode, decode, type BencodeValue } from "../../src/parser/bencode";

// ─────────────────────────────────────────────────────────────────────────────
// Threshold calibration (documented per Constitution §11.4 anti-bluff)
// ─────────────────────────────────────────────────────────────────────────────
//
// NFR-002 hard ceiling = 5 ms PER LINK for detection. That budget is meant to
// cover the WHOLE detect+parse pipeline INCLUDING DOM work, on the slowest
// supported hardware. The pure parser path (regex find + manual param parse)
// is two-to-three orders of magnitude faster than that on any modern CPU
// (sub-microsecond per link in practice). We therefore set the parser-level
// budget WELL UNDER the NFR (a strict internal target) but still high enough to
// absorb CI-runner jitter / cold JIT / a busy shared machine.
//
//   MAGNET_PARSE_BUDGET_MS_PER_LINK = 0.5 ms
//     = 1/10th of the 5 ms NFR-002 ceiling. Rationale: detect+parse is only
//       one stage of the 5 ms/link budget (the rest is DOM traversal, dedup,
//       UI), so the parser alone must be comfortably inside a fraction of it.
//       0.5 ms is ~50–500× the typical observed per-link time, so it will NOT
//       false-fail on a slow CI box, yet a genuinely broken parser (e.g. a
//       10 ms/link regression) blows straight through it. NOT a never-fail
//       bluff threshold — see the anti-bluff tight-threshold proof.
//
//   MAGNET_SCALING_MAX_RATIO = 3.0
//     Per-link time at 5,000 links must not exceed 3× the per-link time at
//     1,000 links. Linear (O(n)) parsing keeps the ratio ~1.0; an accidental
//     O(n²) makes per-link time grow with n and the ratio explodes. 3× is a
//     generous jitter margin around 1.0 that still catches super-linear blowup.
//
//   BENCODE_DECODE_BUDGET_MS = 8 ms per decode
//     For a synthetic .torrent-like dict whose `pieces` string is 10,000
//     pieces × 20 bytes = 200,000 bytes (a large real torrent). A correct
//     single-pass decoder handles this in well under a millisecond; 8 ms is a
//     wide CI margin that still fails a quadratic / per-byte-allocating
//     regression. Decode happens ONCE per .torrent (not per link), so this is
//     an absolute per-operation budget, not a per-link one.
//
const MAGNET_PARSE_BUDGET_MS_PER_LINK = 0.5;
const MAGNET_SCALING_MAX_RATIO = 3.0;
const BENCODE_DECODE_BUDGET_MS = 8;

// Iteration counts for stable (deterministic, §11.4.50) medians.
const WARMUP_RUNS = 2; // discarded — primes the JIT / caches
const MEASURED_RUNS = 7; // odd count → unambiguous median element

/** Median of a numeric array (sorts a copy; for odd length picks the middle). */
function median(samples: number[]): number {
  if (samples.length === 0) throw new Error("median of empty sample set");
  const sorted = [...samples].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const hi = sorted[mid];
  if (hi === undefined) throw new Error("median index out of range");
  if (sorted.length % 2 !== 0) return hi;
  const lo = sorted[mid - 1];
  if (lo === undefined) throw new Error("median index out of range");
  return (lo + hi) / 2;
}

/**
 * Run `fn` WARMUP_RUNS times (discarded) then MEASURED_RUNS times, returning
 * the per-run wall-clock millisecond samples for the measured runs.
 *
 * Each call to `fn` is one full "page worth" of work; the caller divides by the
 * link count to get a per-link figure.
 */
function timeRuns(fn: () => void): number[] {
  for (let i = 0; i < WARMUP_RUNS; i++) fn();
  const samples: number[] = [];
  for (let i = 0; i < MEASURED_RUNS; i++) {
    const start = performance.now();
    fn();
    samples.push(performance.now() - start);
  }
  return samples;
}

/**
 * Build a text blob simulating a page body with `count` DISTINCT magnet URIs
 * embedded in surrounding prose, so `findMagnetUris` does real regex scanning
 * over non-magnet text too (the realistic scanner input).
 *
 * Each URI carries a unique 40-hex BTIH infohash plus realistic dn / tr / xl
 * params, so `parseMagnetUri` exercises the full param-extraction path
 * (display-name sanitize, multi-tracker, exact-length) — not a trivial hash.
 */
function buildMagnetPage(count: number): string {
  const parts: string[] = [];
  for (let i = 0; i < count; i++) {
    // 40-hex infohash, unique per link (zero-padded counter in hex tail).
    const hash = (i.toString(16).padStart(40, "0")).slice(0, 40);
    const dn = encodeURIComponent(`Ubuntu ${i}.04 Desktop amd64`);
    const uri =
      `magnet:?xt=urn:btih:${hash}` +
      `&dn=${dn}` +
      `&tr=${encodeURIComponent("udp://tracker.example.com:1337/announce")}` +
      `&tr=${encodeURIComponent("udp://tracker.openbittorrent.com:80/announce")}` +
      `&xl=${(i + 1) * 1024}`;
    parts.push(`<p>Release ${i} available here: <a href="${uri}">download</a></p>`);
  }
  return parts.join("\n");
}

/**
 * Build a synthetic .torrent-like bencode dict whose `info.pieces` is
 * `pieceCount` SHA-1 digests (20 bytes each) concatenated — the dominant cost
 * in a real torrent. Encoded once, decoded N times in the throughput test.
 */
function buildTorrentDict(pieceCount: number): Uint8Array {
  const pieces = new Uint8Array(pieceCount * 20);
  for (let i = 0; i < pieces.length; i++) pieces[i] = (i * 31 + 7) & 0xff;
  const dict: BencodeValue = {
    announce: "udp://tracker.example.com:1337/announce",
    "creation date": 1700000000,
    "created by": "BobaLink perf fixture",
    info: {
      name: "ubuntu-24.04-desktop-amd64.iso",
      "piece length": 262144,
      length: pieceCount * 262144,
      pieces,
    },
  };
  return encode(dict);
}

describe("perf: magnet detect+parse — NFR-002 ≤5 ms/link (1,000-link page)", () => {
  it("parses 1,000 distinct magnets at ≤0.5 ms/link (median, well under the 5 ms NFR)", () => {
    const LINKS = 1000;
    const page = buildMagnetPage(LINKS);

    // Sanity precondition: the fixture really contains all the links, otherwise
    // a fast "0 links found" run would be a false PASS (anti-bluff).
    const foundOnce = findMagnetUris(page);
    expect(foundOnce.length).toBe(LINKS);

    const samples = timeRuns(() => {
      const uris = findMagnetUris(page);
      for (const uri of uris) parseMagnetUri(uri);
    });

    const totalMedianMs = median(samples);
    const perLinkMs = totalMedianMs / LINKS;

    // eslint-disable-next-line no-console
    console.log(
      `[perf] magnet detect+parse @${LINKS} links: ` +
        `p50 total=${totalMedianMs.toFixed(3)}ms, ` +
        `per-link=${perLinkMs.toFixed(5)}ms ` +
        `(budget ${MAGNET_PARSE_BUDGET_MS_PER_LINK}ms/link; NFR-002 ceiling 5ms/link)`,
    );

    expect(perLinkMs).toBeLessThanOrEqual(MAGNET_PARSE_BUDGET_MS_PER_LINK);
  });
});

describe("perf: magnet parse scales ~linearly (no accidental O(n²))", () => {
  it("per-link time at 5,000 links stays within 3× the per-link time at 1,000 links", () => {
    const SMALL = 1000;
    const LARGE = 5000;
    const pageSmall = buildMagnetPage(SMALL);
    const pageLarge = buildMagnetPage(LARGE);

    expect(findMagnetUris(pageSmall).length).toBe(SMALL);
    expect(findMagnetUris(pageLarge).length).toBe(LARGE);

    const smallPerLink =
      median(
        timeRuns(() => {
          const uris = findMagnetUris(pageSmall);
          for (const uri of uris) parseMagnetUri(uri);
        }),
      ) / SMALL;

    const largePerLink =
      median(
        timeRuns(() => {
          const uris = findMagnetUris(pageLarge);
          for (const uri of uris) parseMagnetUri(uri);
        }),
      ) / LARGE;

    const ratio = largePerLink / smallPerLink;

    // eslint-disable-next-line no-console
    console.log(
      `[perf] magnet parse scaling: ` +
        `per-link@${SMALL}=${smallPerLink.toFixed(5)}ms, ` +
        `per-link@${LARGE}=${largePerLink.toFixed(5)}ms, ` +
        `ratio=${ratio.toFixed(3)} (max ${MAGNET_SCALING_MAX_RATIO} — linear≈1.0)`,
    );

    expect(ratio).toBeLessThanOrEqual(MAGNET_SCALING_MAX_RATIO);
  });
});

describe("perf: bencode decode throughput — large .torrent-like dict", () => {
  it("decodes a 10,000-piece torrent dict at ≤8 ms/decode (median)", () => {
    const PIECES = 10000;
    const encoded = buildTorrentDict(PIECES);

    // Precondition: the fixture decodes to the expected shape, otherwise a
    // throwing/short-circuiting decode could "pass" fast (anti-bluff).
    const decodedOnce = decode(encoded) as Record<string, BencodeValue>;
    const info = decodedOnce.info as Record<string, BencodeValue>;
    expect(typeof info.name).toBe("string");
    // pieces decoded as a UTF-8 string of 200,000 bytes (default encoding).
    expect((info.pieces as string).length).toBeGreaterThan(0);

    const samples = timeRuns(() => {
      decode(encoded);
    });

    const medianMs = median(samples);

    // eslint-disable-next-line no-console
    console.log(
      `[perf] bencode decode @${PIECES} pieces ` +
        `(${encoded.length} bytes): p50=${medianMs.toFixed(4)}ms/decode ` +
        `(budget ${BENCODE_DECODE_BUDGET_MS}ms)`,
    );

    expect(medianMs).toBeLessThanOrEqual(BENCODE_DECODE_BUDGET_MS);
  });
});
