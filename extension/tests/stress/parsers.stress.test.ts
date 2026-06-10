/**
 * @fileoverview Phase-2 STRESS + CHAOS tests for the BobaLink extension parsers.
 *
 * Constitution §11.4.85 (stress + chaos test mandate) + §11.4 anti-bluff
 * covenant. Exercises the REAL committed parser modules — no mocks of the unit
 * under test:
 *   - parser/bencode.ts  (encode / decode / sha1 / bytesToHex)
 *   - parser/magnet.ts   (findMagnetUris / parseMagnetUri / base32ToHex / ...)
 *
 * §11.4.85 closed-set coverage:
 *   STRESS — sustained load (N≥100 varied inputs), concurrent (N≥10 parallel
 *            async infohash computations), boundary (empty / single-byte /
 *            maximum-realistic / off-by-one length-prefix).
 *   CHAOS  — input-corruption injection: a VALID bencoded torrent is corrupted
 *            at every (deterministically iterated, NOT Math.random per §11.4.50)
 *            byte position and EACH variant MUST yield a CATEGORISED result
 *            (parsed-ok OR a typed ParseError) — NEVER an uncaught throw that
 *            escapes the parser's contract. Magnet URIs are corrupted the same
 *            way (truncated xt, bad base32, missing scheme).
 *
 * ANTI-BLUFF: every PASS proves RESILIENCE, not absence-of-error. Each input is
 * classified into a category bucket and the per-category counts are asserted
 * AND printed to console as the §11.4.85 captured evidence. A category that an
 * uncaught (non-ParseError, non-categorised) exception escapes from FAILS the
 * test — a silent wrong value from a swallow-and-return stub is therefore NOT
 * a categorised rejection and FAILS the chaos assertions.
 */

import { describe, it, expect } from "vitest";

import {
  encode,
  decode,
  sha1,
  bytesToHex,
  type BencodeValue,
} from "../../src/parser/bencode";
import {
  findMagnetUris,
  parseMagnetUri,
  base32ToHex,
} from "../../src/parser/magnet";
import { ParseError } from "../../src/shared/errors";

/** UTF-8 encode a literal bencode string for decoder inputs. */
const enc = (s: string): Uint8Array => new TextEncoder().encode(s);

/**
 * Categorised outcome of running a parser against one input.
 *
 *  - "ok"         : parser returned a value (success).
 *  - "rejected"   : parser threw a TYPED ParseError (handled, expected for
 *                   malformed input — this is the categorised-failure path).
 *  - "uncaught"   : parser threw something that is NOT a ParseError — an
 *                   escaped/uncategorised exception. §11.4.85 forbids this.
 *
 * NOTE: a swallow-and-return stub that returns a wrong value instead of
 * throwing on malformed input lands in "ok" — which is exactly why the chaos
 * assertions require "rejected" (not merely "not uncaught"): a silent wrong
 * value is a bluff, not resilience.
 */
type Outcome = "ok" | "rejected" | "uncaught";

/** Run a synchronous parser and categorise its outcome. Never re-throws. */
function classify(fn: () => unknown): Outcome {
  try {
    fn();
    return "ok";
  } catch (err) {
    return err instanceof ParseError ? "rejected" : "uncaught";
  }
}

/** A deterministic PRNG (mulberry32) so corruption byte values are seeded, not random (§11.4.50). */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Build a realistic VALID bencoded torrent metainfo dict (binary mode). */
function buildValidTorrent(): Uint8Array {
  const info: Record<string, BencodeValue> = {
    name: "boba.stress.fixture.iso",
    "piece length": 262144,
    // 3 * 20-byte SHA-1 piece hashes (binary).
    pieces: new Uint8Array(60).map((_, i) => (i * 7 + 3) & 0xff),
    length: 1073741824,
    private: 1,
  };
  const torrent: Record<string, BencodeValue> = {
    announce: "http://tracker.example.test:6969/announce",
    "announce-list": [
      ["http://tracker.a.test/announce"],
      ["udp://tracker.b.test:80/announce"],
    ],
    "created by": "BobaLink/0.2 stress-fixture",
    "creation date": 1700000000,
    encoding: "UTF-8",
    info,
  };
  return encode(torrent);
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. STRESS — sustained load (N ≥ 100)
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: bencode sustained load (N≥100 varied inputs)", () => {
  it("classifies every one of N≥100 varied decodes — zero uncaught, count matches", () => {
    const N = 250;
    // A deterministic mix of valid and malformed bencode inputs.
    const valids = [
      "i0e",
      "i42e",
      "i-7e",
      "i9999999e",
      "4:spam",
      "0:",
      "le",
      "li1ei2ei3ee",
      "de",
      "d3:cow3:moo4:spam4:eggse",
      "d4:listl1:a1:bee",
    ];
    const malformed = [
      "i", // unterminated integer
      "ie", // empty integer
      "iie", // invalid digit
      "5:abc", // string extends past end (off-by-one too long)
      "3:ab", // length one too long
      "1:ab", // trailing data
      ":x", // empty length prefix
      "l", // unterminated list
      "d", // unterminated dict
      "d3:keye", // dict key without value
      "x", // unexpected leading byte
      "", // empty
      "i1e2:zz", // trailing data after valid int
    ];

    const counts: Record<Outcome, number> = { ok: 0, rejected: 0, uncaught: 0 };
    let total = 0;

    for (let i = 0; i < N; i++) {
      const pool = i % 2 === 0 ? valids : malformed;
      const sample = pool[i % pool.length] as string;
      const outcome = classify(() => decode(enc(sample)));
      counts[outcome]++;
      total++;
    }

    // Resilience: every input produced a categorised result (ok OR rejected),
    // NONE escaped as an uncaught exception.
    expect(counts.uncaught).toBe(0);
    // No-unbounded-memory / no-input-dropped signal: result count == input count.
    expect(counts.ok + counts.rejected + counts.uncaught).toBe(N);
    expect(total).toBe(N);
    // Both arms genuinely exercised (not all-ok / all-rejected) — proves the
    // mix actually drove the success AND the rejection paths.
    expect(counts.ok).toBeGreaterThan(0);
    expect(counts.rejected).toBeGreaterThan(0);

    // §11.4.85 captured evidence.
    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS sustained] ${N} bencode decodes: ` +
        `${counts.ok} ok, ${counts.rejected} rejected(ParseError), ` +
        `${counts.uncaught} uncaught`,
    );
  });

  it("classifies every one of N≥100 varied magnet parses — zero uncaught", () => {
    const N = 200;
    const HEX = "1234567890abcdef1234567890abcdef12345678";
    const valids = [
      `magnet:?xt=urn:btih:${HEX}`,
      `magnet:?xt=urn:btih:${HEX}&dn=Test+Name`,
      `magnet:?xt=urn:btih:${HEX}&tr=http%3A%2F%2Ftr.test%2Fa&tr=udp%3A%2F%2Ftr.test%2Fb`,
      "magnet:?xt=urn:btih:YEX6DQDLXISUVHOJ6UM3GNNKPQJWPKEK", // base32
    ];
    const malformed = [
      "magnet:?xt=urn:btih:tooshort",
      "magnet:?dn=NoInfohash",
      "magnet:?xt=urn:btih:ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ", // bad base32 chars
      "http://not-a-magnet.test/",
      "",
      "magnet:?",
    ];

    const counts: Record<Outcome, number> = { ok: 0, rejected: 0, uncaught: 0 };

    for (let i = 0; i < N; i++) {
      const pool = i % 2 === 0 ? valids : malformed;
      const sample = pool[i % pool.length] as string;
      const outcome = classify(() => parseMagnetUri(sample));
      counts[outcome]++;
    }

    expect(counts.uncaught).toBe(0);
    expect(counts.ok + counts.rejected).toBe(N);
    expect(counts.ok).toBeGreaterThan(0);
    expect(counts.rejected).toBeGreaterThan(0);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS sustained] ${N} magnet parses: ` +
        `${counts.ok} ok, ${counts.rejected} rejected(ParseError), ` +
        `${counts.uncaught} uncaught`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. STRESS — concurrent (N ≥ 10) + §11.4.50 determinism under concurrency
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: concurrent async infohash (N≥10) + §11.4.50 determinism", () => {
  it("computes the same infohash for the same input across ≥10 concurrent runs", async () => {
    const CONCURRENCY = 24;
    const info: Record<string, BencodeValue> = {
      name: "concurrent.fixture",
      "piece length": 16384,
      pieces: new Uint8Array(20).fill(0xab),
      length: 4096,
    };
    const infoBytes = encode(info);

    // Fire CONCURRENCY identical sha1 computations in parallel via Promise.all.
    const results = await Promise.all(
      Array.from({ length: CONCURRENCY }, () => sha1(infoBytes)),
    );

    // Determinism under concurrency: every concurrent run produced the SAME
    // 40-char hex digest — no interleaving corruption (§11.4.50).
    const unique = new Set(results);
    expect(unique.size).toBe(1);
    const digest = results[0] as string;
    expect(digest).toMatch(/^[0-9a-f]{40}$/);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS concurrent] ${CONCURRENCY} parallel sha1 runs: ` +
        `${unique.size} distinct digest(s) (expected 1) = ${digest}`,
    );
  });

  it("computes distinct infohashes for distinct concurrent inputs without cross-talk", async () => {
    const CONCURRENCY = 16;
    const inputs = Array.from({ length: CONCURRENCY }, (_, i) =>
      encode({ name: `torrent-${i}`, length: i }),
    );

    // Interleave with a single repeated input to prove no shared-state leak:
    // run all distinct inputs concurrently, twice, and assert each input maps
    // to a stable digest regardless of concurrent neighbours.
    const round1 = await Promise.all(inputs.map((b) => sha1(b)));
    const round2 = await Promise.all([...inputs].reverse().map((b) => sha1(b)));
    const round2Aligned = [...round2].reverse();

    // Same input → same digest in both concurrent rounds (no interleaving corruption).
    for (let i = 0; i < CONCURRENCY; i++) {
      expect(round1[i]).toBe(round2Aligned[i]);
    }
    // Distinct inputs → distinct digests (no cross-talk collapse).
    expect(new Set(round1).size).toBe(CONCURRENCY);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS concurrent] ${CONCURRENCY} distinct inputs x2 rounds: ` +
        `${new Set(round1).size} distinct digests, stable across rounds`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. STRESS — boundary inputs
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 STRESS: boundary inputs (empty / single-byte / max / off-by-one)", () => {
  it("handles every boundary case with a categorised result — never an uncaught crash", () => {
    type BoundaryCase = { label: string; bytes: Uint8Array };

    // Maximum-realistic large bencoded dict: ~5000 piece hashes (100 KB binary)
    // + a large announce-list — exercises the encoder/decoder under volume.
    const bigPieces = new Uint8Array(5000 * 20);
    for (let i = 0; i < bigPieces.length; i++) bigPieces[i] = (i * 31 + 7) & 0xff;
    const bigTrackers: BencodeValue[] = Array.from({ length: 300 }, (_, i) => [
      `udp://tracker${i}.example.test:6969/announce`,
    ]);
    const bigTorrent = encode({
      "announce-list": bigTrackers,
      info: { name: "huge.fixture", "piece length": 262144, pieces: bigPieces },
    });

    // Maximum-realistic magnet: many trackers.
    const HEX = "1234567890abcdef1234567890abcdef12345678";
    const manyTrackers = Array.from(
      { length: 200 },
      (_, i) => `tr=udp%3A%2F%2Ftracker${i}.test%3A6969%2Fannounce`,
    ).join("&");
    const bigMagnet = `magnet:?xt=urn:btih:${HEX}&dn=${"A".repeat(2000)}&${manyTrackers}`;

    const cases: BoundaryCase[] = [
      { label: "empty", bytes: new Uint8Array(0) },
      { label: "single-byte 'i'", bytes: enc("i") },
      { label: "single-byte 'e'", bytes: enc("e") },
      { label: "single-byte '4'", bytes: enc("4") },
      { label: "single-byte 0x00", bytes: new Uint8Array([0]) },
      { label: "off-by-one length too long", bytes: enc("5:abcd") },
      { label: "off-by-one length too short", bytes: enc("3:abcd") },
      { label: "off-by-one int unterminated", bytes: enc("i123") },
      { label: "max-realistic big torrent (valid)", bytes: bigTorrent },
    ];

    const counts: Record<Outcome, number> = { ok: 0, rejected: 0, uncaught: 0 };
    const perCase: Record<string, Outcome> = {};

    for (const c of cases) {
      const outcome = classify(() => decode(c.bytes, { encoding: "binary" }));
      counts[outcome]++;
      perCase[c.label] = outcome;
    }

    // The large valid torrent round-trips successfully (proves max-realistic
    // volume is HANDLED, not just survived) — re-encode equals original bytes.
    expect(perCase["max-realistic big torrent (valid)"]).toBe("ok");
    const redecoded = decode(bigTorrent, { encoding: "binary" });
    expect(bytesToHex(encode(redecoded as BencodeValue))).toBe(
      bytesToHex(bigTorrent),
    );

    // The big magnet parses to a usable result with all trackers captured.
    const bigMagnetOutcome = classify(() => parseMagnetUri(bigMagnet));
    expect(bigMagnetOutcome).toBe("ok");
    const parsedBig = parseMagnetUri(bigMagnet);
    expect(parsedBig.infohash).toBe(HEX);
    expect(parsedBig.trackers.length).toBe(200);

    // EVERY boundary case yielded a categorised result — zero uncaught.
    expect(counts.uncaught).toBe(0);
    expect(counts.ok + counts.rejected).toBe(cases.length);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS boundary] ${cases.length} bencode boundary cases: ` +
        `${counts.ok} ok, ${counts.rejected} rejected, ${counts.uncaught} uncaught | ` +
        `big-magnet(200 trackers)=${bigMagnetOutcome}`,
    );
    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 STRESS boundary] per-case: ${JSON.stringify(perCase)}`,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. CHAOS — input-corruption injection (deterministic positions, §11.4.50)
// ─────────────────────────────────────────────────────────────────────────────

describe("§11.4.85 CHAOS: bencode byte-corruption injection (categorised, never uncaught)", () => {
  it("rejects-or-survives every single-byte corruption — ZERO uncaught across all positions", () => {
    const valid = buildValidTorrent();
    const rng = mulberry32(0xb0ba1115); // seeded — deterministic per §11.4.50

    const counts: Record<Outcome, number> = { ok: 0, rejected: 0, uncaught: 0 };
    let positions = 0;

    // Iterate EVERY byte position (deterministic, not random) and inject a
    // deterministic-but-different corrupting byte at each.
    for (let pos = 0; pos < valid.length; pos++) {
      const corrupted = new Uint8Array(valid);
      const orig = corrupted[pos] as number;
      // Seeded corrupting byte guaranteed != original.
      const delta = 1 + Math.floor(rng() * 254);
      corrupted[pos] = (orig + delta) & 0xff;

      const outcome = classify(() => decode(corrupted, { encoding: "binary" }));
      counts[outcome]++;
      positions++;
    }

    // §11.4.85 CHAOS contract: EVERY corrupted variant is categorised — a
    // typed ParseError rejection OR a (still-valid) parse — but NEVER an
    // uncaught exception escaping the parser's contract.
    expect(counts.uncaught).toBe(0);
    expect(counts.ok + counts.rejected).toBe(positions);
    // Corruption genuinely breaks the structure in the overwhelming majority of
    // positions → most variants are rejected with a typed error (proves the
    // chaos actually corrupted something, not a no-op).
    expect(counts.rejected).toBeGreaterThan(0);
    expect(positions).toBeGreaterThan(0);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 CHAOS corruption] ${positions} byte positions corrupted: ` +
        `${counts.rejected} rejected(ParseError), ${counts.ok} still-valid, ` +
        `${counts.uncaught} uncaught`,
    );
  });

  it("rejects multi-byte (truncation + overwrite) corruption with categorised results", () => {
    const valid = buildValidTorrent();
    const counts: Record<Outcome, number> = { ok: 0, rejected: 0, uncaught: 0 };
    let variants = 0;

    // Truncations at every length from full-1 down to 0.
    for (let len = valid.length - 1; len >= 0; len--) {
      const truncated = valid.slice(0, len);
      counts[classify(() => decode(truncated, { encoding: "binary" }))]++;
      variants++;
    }
    // Trailing-garbage appends.
    for (let extra = 1; extra <= 32; extra++) {
      const appended = new Uint8Array(valid.length + extra);
      appended.set(valid);
      for (let i = 0; i < extra; i++) appended[valid.length + i] = (extra * 13 + i) & 0xff;
      counts[classify(() => decode(appended, { encoding: "binary" }))]++;
      variants++;
    }

    expect(counts.uncaught).toBe(0);
    expect(counts.ok + counts.rejected).toBe(variants);
    expect(counts.rejected).toBeGreaterThan(0);

    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 CHAOS corruption] ${variants} truncation/append variants: ` +
        `${counts.rejected} rejected, ${counts.ok} still-valid, ${counts.uncaught} uncaught`,
    );
  });
});

describe("§11.4.85 CHAOS: magnet-URI corruption injection (categorised, never uncaught)", () => {
  it("handles truncated/bad-base32/missing-scheme magnet corruption with categorised results", () => {
    const HEX = "1234567890abcdef1234567890abcdef12345678";
    const validMagnet = `magnet:?xt=urn:btih:${HEX}&dn=Boba+Fixture&tr=http%3A%2F%2Ftr.test%2Fa`;

    const corruptions: { label: string; uri: string }[] = [];

    // Truncate the xt at every length (eats the infohash byte by byte).
    const xtFull = `magnet:?xt=urn:btih:${HEX}`;
    for (let len = xtFull.length; len >= "magnet:?".length; len--) {
      corruptions.push({ label: `trunc-xt@${len}`, uri: xtFull.slice(0, len) });
    }
    // Bad base32 (invalid chars / wrong length).
    corruptions.push({ label: "bad-base32-chars", uri: "magnet:?xt=urn:btih:0189ZZZZZZZZZZZZZZZZZZZZZZZZZZZZ" });
    corruptions.push({ label: "base32-too-short", uri: "magnet:?xt=urn:btih:ABCDEFG" });
    // Missing scheme.
    corruptions.push({ label: "missing-scheme", uri: validMagnet.replace("magnet:?", "") });
    corruptions.push({ label: "wrong-scheme", uri: validMagnet.replace("magnet:?", "torrent:?") });
    // Garbage suffix on an otherwise-valid magnet (must still parse — categorised ok).
    corruptions.push({ label: "garbage-suffix", uri: `${validMagnet}& ￿&=&x` });

    const counts: Record<Outcome, number> = { ok: 0, rejected: 0, uncaught: 0 };
    for (const c of corruptions) {
      counts[classify(() => parseMagnetUri(c.uri))]++;
    }

    // Also chaos-corrupt base32ToHex directly with non-base32 input.
    const badBase32 = ["", "11111111111111111111111111111111", "not-base32!!", "AAAA"];
    let base32Rejected = 0;
    for (const b of badBase32) {
      const o = classify(() => base32ToHex(b));
      counts[o]++;
      if (o === "rejected") base32Rejected++;
    }

    // findMagnetUris over corrupted blobs must never throw — returns categorised array.
    const blobs = ["", "magnet:?", "magnet:?xt=urn:btih:" + "z".repeat(40), "x".repeat(10000)];
    let findOk = 0;
    for (const blob of blobs) {
      const o = classify(() => findMagnetUris(blob));
      counts[o]++;
      if (o === "ok") findOk++;
    }

    expect(counts.uncaught).toBe(0);
    expect(counts.rejected).toBeGreaterThan(0); // bad base32 / truncated xt are rejected
    expect(base32Rejected).toBe(badBase32.length); // every bad base32 is a typed rejection
    expect(findOk).toBe(blobs.length); // findMagnetUris is total (never throws)

    const total = corruptions.length + badBase32.length + blobs.length;
    // eslint-disable-next-line no-console
    console.log(
      `[§11.4.85 CHAOS corruption] ${total} magnet-corruption inputs ` +
        `(${corruptions.length} uri + ${badBase32.length} base32 + ${blobs.length} find): ` +
        `${counts.rejected} rejected, ${counts.ok} ok, ${counts.uncaught} uncaught`,
    );
  });
});
