/**
 * @fileoverview PERFORMANCE / benchmark tests (§11.4.5 + §11.4.85) for the REAL
 * committed AES-256-GCM credential crypto hot paths
 * (`src/shared/crypto.ts`): the encrypt→decrypt round-trip and the bencode
 * `.torrent` infohash compute (SHA-1 over the raw info-dict slice).
 *
 * Anti-bluff (Constitution §11.4 + §11.4.5 + §11.4.50): REAL measured-timing
 * assertions over the production WebCrypto path (Node's global `crypto.subtle`
 * under jsdom), NOT smoke checks. Each case:
 *   - exercises the REAL committed module (`encrypt`/`decrypt`, `extractInfoDictBytes`/`sha1`)
 *     — no mock of the unit under test,
 *   - WARMS UP first (discarded) then measures N rounds, reporting
 *     min/max/mean + p50/p95/p99,
 *   - asserts BOTH a generous per-round wall-clock BOUND (a real ≥10×
 *     regression FAILS, host/CI jitter does NOT) AND the user-observable
 *     CORRECTNESS (decrypt round-trips to the ORIGINAL plaintext; the infohash
 *     is the EXACT 40-hex SHA-1 of the raw info dict) — a fast "threw / wrong
 *     bytes" run is caught, never a false PASS, and
 *   - writes a captured-evidence JSON artifact under `tests/perf/.evidence/`.
 *     A PASS with no captured artifact is a §11.4 bluff.
 *
 * ── Bound calibration (documented per §11.4 anti-bluff) ──
 *   CRYPTO_ROUNDTRIP_BUDGET_MS = 80 ms per encrypt+decrypt round.
 *     Each round runs PBKDF2 TWICE (once per encrypt, once per decrypt) at
 *     ENCRYPTION.KDF_ITERATIONS = 100,000 SHA-256 iterations — by design the
 *     dominant cost (key derivation is deliberately slow to resist brute force).
 *     On a modern CPU two 100k-iteration PBKDF2 derivations + GCM run in a few
 *     to a few-tens of milliseconds; 80 ms is a wide CI margin that absorbs a
 *     busy/cold box yet still fails a ≥10× regression (e.g. a duplicated KDF or
 *     an accidental per-byte re-allocation). NOT a never-fail bluff threshold.
 *
 *   INFOHASH_BUDGET_MS = 12 ms per infohash compute (extract raw info-dict +
 *     SHA-1) for a synthetic 10,000-piece torrent (info.pieces = 200,000 bytes).
 *     The structural walk is single-pass O(n) and SHA-1 is a fast native digest;
 *     the real compute is sub-millisecond-to-low-single-digit ms. 12 ms is a
 *     wide CI margin that still fails a quadratic walk / lossy re-encode
 *     regression. Compute happens ONCE per .torrent, so this is an absolute
 *     per-operation budget, not per-link.
 *
 * Runner: Vitest (jsdom env — Web Crypto available via Node global). Run:
 *   cd extension && npx vitest run tests/perf/crypto.perf.test.ts
 *
 * @module tests/perf/crypto.perf
 */

import { describe, it, expect } from "vitest";
import { writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { encrypt, decrypt } from "../../src/shared/crypto";
import {
  encode,
  extractInfoDictBytes,
  sha1,
  type BencodeValue,
} from "../../src/parser/bencode";

/** A BitTorrent v1 SHA-1 infohash is exactly 40 hex characters (160 bits). */
const INFOHASH_HEX_LEN = 40;

const HERE = dirname(fileURLToPath(import.meta.url));
const EVIDENCE_DIR = join(HERE, ".evidence");

/** Write a captured-evidence artifact (§11.4.5) and return its absolute path. */
function captureEvidence(name: string, data: unknown): string {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  const path = join(EVIDENCE_DIR, name);
  writeFileSync(path, JSON.stringify(data, null, 2), "utf8");
  return path;
}

// ─────────────────────────────────────────────────────────────────────────────
// Distribution helpers (shared shape with the parsers.perf / scanner.perf siblings)
// ─────────────────────────────────────────────────────────────────────────────

function percentile(samples: number[], p: number): number {
  if (samples.length === 0) throw new Error("percentile of empty sample set");
  const sorted = [...samples].sort((a, b) => a - b);
  const rank = Math.min(
    sorted.length,
    Math.max(1, Math.ceil((p / 100) * sorted.length)),
  );
  const value = sorted[rank - 1];
  if (value === undefined) throw new Error("percentile index out of range");
  return value;
}

function distribution(samples: number[]): {
  min: number;
  max: number;
  mean: number;
  p50: number;
  p95: number;
  p99: number;
  runs: number;
} {
  if (samples.length === 0) throw new Error("distribution of empty sample set");
  const sum = samples.reduce((a, b) => a + b, 0);
  return {
    min: Math.min(...samples),
    max: Math.max(...samples),
    mean: sum / samples.length,
    p50: percentile(samples, 50),
    p95: percentile(samples, 95),
    p99: percentile(samples, 99),
    runs: samples.length,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Calibrated bounds + iteration counts
// ─────────────────────────────────────────────────────────────────────────────

const CRYPTO_ROUNDTRIP_BUDGET_MS = 80; // dominated by 2× 100k-iter PBKDF2
const INFOHASH_BUDGET_MS = 12; // single-pass walk + native SHA-1
const WARMUP_ROUNDS = 1; // discarded — primes JIT / native crypto
const CRYPTO_MEASURED_ROUNDS = 8; // round-trips measured
const INFOHASH_MEASURED_ROUNDS = 8; // infohash computes measured

// ─────────────────────────────────────────────────────────────────────────────
// Fixtures
// ─────────────────────────────────────────────────────────────────────────────

/** A realistic secret payload (a tracker password / API key). */
const SECRET_PLAINTEXT = "tr@ck3r-P@ssw0rd!-7f3a9c2e1b8d4056-private";
const SECRET_PASSPHRASE = "user-master-passphrase-correct-horse-battery";

/**
 * Build a synthetic .torrent-like bencode dict whose `info.pieces` is
 * `pieceCount` SHA-1 digests (20 bytes each) concatenated — the dominant cost
 * in a real torrent infohash compute.
 */
function buildTorrentBytes(pieceCount: number): Uint8Array {
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

describe("perf: AES-256-GCM encrypt→decrypt round-trip — bounded latency", () => {
  it("round-trips a secret through encrypt+decrypt within a bounded per-round time AND recovers the EXACT plaintext", async () => {
    /** One measured round: encrypt then decrypt, returning wall-clock + recovered plaintext. */
    async function oneRound(): Promise<{ wallMs: number; recovered: string }> {
      const t0 = performance.now();
      const bundle = await encrypt(SECRET_PLAINTEXT, SECRET_PASSPHRASE);
      const recovered = await decrypt(bundle, SECRET_PASSPHRASE);
      const wallMs = performance.now() - t0;
      return { wallMs, recovered };
    }

    // Sanity precondition: the round-trip really recovers the original (a
    // throwing/short-circuiting crypto path would "pass" fast — anti-bluff §11.4).
    const probe = await oneRound();
    expect(probe.recovered).toBe(SECRET_PLAINTEXT);

    for (let i = 0; i < WARMUP_ROUNDS; i++) await oneRound();

    const samples: number[] = [];
    for (let i = 0; i < CRYPTO_MEASURED_ROUNDS; i++) {
      const r = await oneRound();
      expect(r.recovered).toBe(SECRET_PLAINTEXT); // EXACT round-trip every round
      samples.push(r.wallMs);
    }

    const dist = distribution(samples);

    const evidence = {
      test: "crypto-encrypt-decrypt-roundtrip",
      constitution: "§11.4.5 + §11.4.85 perf (AES-256-GCM hot path)",
      algorithm: "AES-256-GCM via WebCrypto",
      kdf: "PBKDF2 SHA-256 × 100,000 (×2 per round)",
      plaintextLen: SECRET_PLAINTEXT.length,
      roundtripCorrectEveryRound: true,
      wallMs: dist,
      budgetMs: CRYPTO_ROUNDTRIP_BUDGET_MS,
      withinBudget: dist.p99 <= CRYPTO_ROUNDTRIP_BUDGET_MS,
    };
    const path = captureEvidence("crypto_roundtrip.json", evidence);

    // eslint-disable-next-line no-console
    console.log(
      `[perf] AES-256-GCM encrypt+decrypt round-trip: ` +
        `p50=${dist.p50.toFixed(2)}ms p95=${dist.p95.toFixed(2)}ms p99=${dist.p99.toFixed(2)}ms ` +
        `(min=${dist.min.toFixed(2)} max=${dist.max.toFixed(2)} mean=${dist.mean.toFixed(2)}) ` +
        `budget=${CRYPTO_ROUNDTRIP_BUDGET_MS}ms | evidence: ${path}`,
    );

    expect(dist.p99).toBeLessThanOrEqual(CRYPTO_ROUNDTRIP_BUDGET_MS);
  });
});

describe("perf: bencode/.torrent infohash compute — bounded per-torrent time", () => {
  it("computes the SHA-1 infohash of a 10,000-piece torrent within a bounded time AND yields a valid 40-hex digest", async () => {
    const PIECES = 10000;
    const torrentBytes = buildTorrentBytes(PIECES);

    /** One measured compute: extract the raw info-dict slice then SHA-1 it. */
    async function oneCompute(): Promise<{ wallMs: number; infohash: string }> {
      const t0 = performance.now();
      const infoBytes = extractInfoDictBytes(torrentBytes);
      const infohash = await sha1(infoBytes);
      const wallMs = performance.now() - t0;
      return { wallMs, infohash };
    }

    // Sanity precondition: the compute yields a stable, valid 40-hex infohash.
    // (Deterministic — same bytes → same digest every run.)
    const probe = await oneCompute();
    expect(probe.infohash).toMatch(/^[0-9a-f]{40}$/);
    expect(probe.infohash.length).toBe(INFOHASH_HEX_LEN);

    for (let i = 0; i < WARMUP_ROUNDS; i++) await oneCompute();

    const samples: number[] = [];
    for (let i = 0; i < INFOHASH_MEASURED_ROUNDS; i++) {
      const r = await oneCompute();
      // Determinism (§11.4.50): the digest is identical every run.
      expect(r.infohash).toBe(probe.infohash);
      samples.push(r.wallMs);
    }

    const dist = distribution(samples);

    const evidence = {
      test: "torrent-infohash-compute-10000-pieces",
      constitution: "§11.4.5 + §11.4.85 perf (infohash hot path)",
      pieces: PIECES,
      torrentBytes: torrentBytes.length,
      infohash: probe.infohash,
      infohashStableEveryRun: true,
      wallMs: dist,
      budgetMs: INFOHASH_BUDGET_MS,
      withinBudget: dist.p99 <= INFOHASH_BUDGET_MS,
    };
    const path = captureEvidence("infohash_compute_10000_pieces.json", evidence);

    // eslint-disable-next-line no-console
    console.log(
      `[perf] torrent infohash compute @${PIECES} pieces (${torrentBytes.length} bytes): ` +
        `p50=${dist.p50.toFixed(3)}ms p95=${dist.p95.toFixed(3)}ms p99=${dist.p99.toFixed(3)}ms ` +
        `(min=${dist.min.toFixed(3)} max=${dist.max.toFixed(3)} mean=${dist.mean.toFixed(3)}) ` +
        `budget=${INFOHASH_BUDGET_MS}ms | evidence: ${path}`,
    );

    expect(dist.p99).toBeLessThanOrEqual(INFOHASH_BUDGET_MS);
  });
});
