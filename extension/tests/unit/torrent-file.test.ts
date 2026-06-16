/**
 * @fileoverview Unit tests for the .torrent file parser (parser/torrent-file.ts).
 *
 * Anti-bluff (Constitution §11.4): imports the REAL module under test (no
 * mocks, no stubs), and builds every `.torrent` input IN THE TEST from the
 * committed `bencode.encode` — a genuine encode→parse→decode round-trip, not a
 * fixture blob. Every assertion inspects a user-observable outcome (the parsed
 * name / size / files / trackers / infohash / piece count / private flag, the
 * generated magnet URI, the sanitized URL, or the thrown error). The suite is
 * built to FAIL against a no-op stub of the parser — each test pins a concrete
 * recovered value rather than merely "no throw".
 *
 * The infohash assertions are the load-bearing wiring proof: the infohash is
 * computed by the REAL `sha1(encode(info))` chain, so the determinism +
 * uniqueness tests catch any break in that computation (see the anti-bluff
 * mutation evidence in the session report).
 */

import { describe, it, expect, vi, afterEach } from "vitest";

import {
  parseTorrentFile,
  parseTorrentFromUrl,
  computeInfohash,
  buildMagnetFromTorrent,
  sanitizePasskeyFromUrl,
} from "../../src/parser/torrent-file";
import { encode, type BencodeValue } from "../../src/parser/bencode";
import { ParseError } from "../../src/shared/errors";

// ─────────────────────────────────────────────────────────────────────────────
// Independent infohash oracle — deliberately does NOT touch the parser.
//
// The BitTorrent infohash is SHA-1 over the RAW bencoded bytes of the info
// dictionary, exactly as they sit in the .torrent file. This helper computes it
// straight from a known `infoBytes` slice via `crypto.subtle` (NOT via
// `parseTorrentFile`, NOT via the parser's decode→re-encode chain). It is the
// ground truth that the binary-pieces test below pins the parser against.
// ─────────────────────────────────────────────────────────────────────────────
async function oracleInfohashFromInfoBytes(infoBytes: Uint8Array): Promise<string> {
  // Copy into a fresh ArrayBuffer-backed view for `crypto.subtle.digest`.
  const input = new Uint8Array(infoBytes);
  const digest = await crypto.subtle.digest("SHA-1", input);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * ASCII bytes helper for assembling a root .torrent buffer by hand (so the test
 * controls the EXACT on-disk info-dict byte slice without going through the
 * parser).
 */
function ascii(s: string): Uint8Array {
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i) & 0xff;
  return out;
}

/** Concatenate byte chunks. */
function concatBytes(...chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.length;
  }
  return out;
}

// ─────────────────────────────────────────────────────────────────────────────
// Builders: real .torrent bytes via the committed bencode.encode
// ─────────────────────────────────────────────────────────────────────────────

/** Build N×20 deterministic "pieces" bytes (each piece = a 20-byte SHA-1). */
function makePieces(count: number, seed = 1): Uint8Array {
  const bytes = new Uint8Array(count * 20);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = (i * 7 + seed) & 0xff;
  }
  return bytes;
}

interface SingleFileOpts {
  name?: string;
  length?: number;
  pieceLength?: number;
  pieceCount?: number;
  isPrivate?: boolean;
  announce?: string;
  announceList?: string[][];
  pieceSeed?: number;
}

/** Build a single-file `.torrent` as raw bencoded bytes. */
function buildSingleFileTorrent(opts: SingleFileOpts = {}): Uint8Array {
  const {
    name = "ubuntu.iso",
    length = 2048,
    pieceLength = 256,
    pieceCount = 8,
    isPrivate = false,
    announce,
    announceList,
    pieceSeed = 1,
  } = opts;

  const info: Record<string, BencodeValue> = {
    name,
    length,
    "piece length": pieceLength,
    pieces: makePieces(pieceCount, pieceSeed),
  };
  if (isPrivate) info["private"] = 1;

  const root: Record<string, BencodeValue> = { info };
  if (announce) root["announce"] = announce;
  if (announceList) root["announce-list"] = announceList;

  return encode(root);
}

/** Build a multi-file `.torrent` as raw bencoded bytes. */
function buildMultiFileTorrent(
  files: { path: string[]; length: number }[],
  name = "Season 1",
): Uint8Array {
  const info: Record<string, BencodeValue> = {
    name,
    "piece length": 512,
    pieces: makePieces(4),
    files: files.map((f) => ({ path: f.path, length: f.length })),
  };
  return encode({ info });
}

// ─────────────────────────────────────────────────────────────────────────────
// Infohash: determinism + uniqueness (REAL sha1(encode(info)))
// ─────────────────────────────────────────────────────────────────────────────

describe("torrent-file: infohash determinism + uniqueness", () => {
  it("computes a 40-char hex SHA-1 infohash for a valid torrent", async () => {
    const parsed = await parseTorrentFile(buildSingleFileTorrent());
    expect(parsed.infohash).toMatch(/^[a-f0-9]{40}$/);
  });

  it("produces the SAME infohash for identical bytes (determinism)", async () => {
    const bytes = buildSingleFileTorrent({ name: "deterministic.iso" });
    const a = await parseTorrentFile(bytes);
    const b = await parseTorrentFile(bytes.slice()); // distinct buffer, same content
    expect(b.infohash).toBe(a.infohash);
  });

  it("computeInfohash matches the full-parse infohash for the same bytes", async () => {
    const bytes = buildSingleFileTorrent({ name: "match.iso" });
    const parsed = await parseTorrentFile(bytes);
    const quick = await computeInfohash(bytes);
    expect(quick).toBe(parsed.infohash);
  });

  it("produces DIFFERENT infohashes for different torrents (uniqueness)", async () => {
    const a = await parseTorrentFile(buildSingleFileTorrent({ name: "alpha.iso" }));
    const b = await parseTorrentFile(buildSingleFileTorrent({ name: "beta.iso" }));
    expect(a.infohash).not.toBe(b.infohash);
  });

  it("a single differing info byte changes the infohash (info-dict sensitivity)", async () => {
    // Same metadata, different piece bytes ⇒ different bencoded info ⇒ different hash.
    const a = await parseTorrentFile(
      buildSingleFileTorrent({ name: "x.iso", pieceSeed: 1 }),
    );
    const b = await parseTorrentFile(
      buildSingleFileTorrent({ name: "x.iso", pieceSeed: 2 }),
    );
    expect(a.infohash).not.toBe(b.infohash);
  });

  it("infohash equals SHA-1 of the RAW on-disk info-dict bytes (golden vector)", async () => {
    // Independent oracle for the CORRECT BitTorrent definition: the infohash is
    // SHA-1 over the RAW bencoded `info` bytes exactly as they sit in the file —
    // NOT a decode→re-encode (which mangles binary `pieces`). The test owns the
    // exact info-dict slice by assembling the root buffer by hand, then hashes
    // that slice via the independent `crypto.subtle` oracle. If the parser
    // hashed a re-encode, the wrong dict, or skipped the sha1 step, this diverges.
    const infoBytes = encode({
      length: 1024,
      name: "golden.iso",
      "piece length": 256,
      pieces: makePieces(4, 1),
    });
    const bytes = concatBytes(ascii("d4:info"), infoBytes, ascii("e"));

    const parsed = await parseTorrentFile(bytes);
    const oracleInfohash = await oracleInfohashFromInfoBytes(infoBytes);

    expect(parsed.infohash).toBe(oracleInfohash);
    expect(parsed.infohash).toMatch(/^[a-f0-9]{40}$/);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Infohash over REAL BINARY pieces (high bytes) — the correctness defect.
//
// A real torrent's `info.pieces` is binary: 20 bytes × N piece-hashes, full of
// bytes in 0x80–0xff. The infohash is SHA-1 of the RAW bencoded info-dict bytes
// as they appear on disk — NOT a UTF-8 decode-then-re-encode (that mangles every
// high byte and yields the WRONG identity). These tests build the on-disk bytes
// by hand so the test owns the exact info-dict slice, then pin the parser's
// infohash to an independent `crypto.subtle` oracle over that raw slice.
// ─────────────────────────────────────────────────────────────────────────────

/** Deterministic binary pieces with high bytes (0x80, 0xfe, 0xff, 0x00, …). */
function makeBinaryPieces(count: number): Uint8Array {
  const bytes = new Uint8Array(count * 20);
  // Deterministic high-byte pattern (NOT Math.random, per §11.4.50). Cycles
  // through values that exercise the 0x80–0xff range plus 0x00 boundaries that
  // UTF-8 decode/re-encode demonstrably corrupts.
  const pattern = [0x80, 0xff, 0xfe, 0x00, 0xc0, 0x81, 0x90, 0xab, 0xcd, 0xef];
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = pattern[i % pattern.length] ?? 0;
  }
  return bytes;
}

describe("torrent-file: infohash over REAL binary pieces", () => {
  it("computes infohash as SHA-1 of the RAW info-dict bytes (binary pieces, high bytes)", async () => {
    const pieces = makeBinaryPieces(3); // 3×20 = 60 binary bytes incl. 0x80/0xff/0xfe/0x00
    // Sanity: the fixture really does contain high bytes that UTF-8 mangles.
    expect(pieces).toContain(0x80);
    expect(pieces).toContain(0xff);
    expect(pieces).toContain(0xfe);

    // Build the info dict's canonical bencoded bytes ONCE (binary pieces preserved).
    const infoBytes = encode({
      length: 1024,
      name: "realistic-binary.iso",
      "piece length": 256,
      pieces,
    });

    // Assemble the on-disk root buffer by hand: d 4:info <infoBytes> e.
    // The test now owns the EXACT raw info-dict slice that ends up on disk.
    const fileBytes = concatBytes(ascii("d4:info"), infoBytes, ascii("e"));

    // Independent oracle: SHA-1 over the raw info-dict bytes (no parser involved).
    const expected = await oracleInfohashFromInfoBytes(infoBytes);

    const parsed = await parseTorrentFile(fileBytes);

    // THE defect: a UTF-8 decode→re-encode infohash diverges from this.
    expect(parsed.infohash).toBe(expected);
    expect(parsed.infohash).toMatch(/^[a-f0-9]{40}$/);

    // The binary pieces must still be counted correctly (60 / 20 = 3).
    expect(parsed.numPieces).toBe(3);
  });

  it("computeInfohash over binary pieces equals the raw-info-dict SHA-1 oracle", async () => {
    const pieces = makeBinaryPieces(2);
    const infoBytes = encode({
      length: 512,
      name: "quick-binary.iso",
      "piece length": 256,
      pieces,
    });
    const fileBytes = concatBytes(ascii("d4:info"), infoBytes, ascii("e"));

    const expected = await oracleInfohashFromInfoBytes(infoBytes);
    const quick = await computeInfohash(fileBytes);

    expect(quick).toBe(expected);
  });

  it("still decodes UTF-8 metadata correctly alongside binary pieces", async () => {
    const pieces = makeBinaryPieces(3);
    const infoBytes = encode({
      length: 4096,
      name: "Café Über — Москва.mkv", // genuine multi-byte UTF-8 name
      "piece length": 1024,
      pieces,
    });
    const fileBytes = concatBytes(
      ascii("d8:announce"),
      ascii("31:udp://tracker.example:1337/anno"),
      ascii("4:info"),
      infoBytes,
      ascii("e"),
    );

    const parsed = await parseTorrentFile(fileBytes);

    // Metadata (UTF-8) decodes correctly even though pieces are raw binary.
    expect(parsed.name).toBe("Café Über — Москва.mkv");
    expect(parsed.totalSize).toBe(4096);
    expect(parsed.files[0]?.fullPath).toBe("Café Über — Москва.mkv");
    expect(parsed.trackers).toContain("udp://tracker.example:1337/anno");

    // And the infohash is the raw-info-dict SHA-1 (not the mangled re-encode).
    const expected = await oracleInfohashFromInfoBytes(infoBytes);
    expect(parsed.infohash).toBe(expected);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Single-file parse: name / totalSize / files
// ─────────────────────────────────────────────────────────────────────────────

describe("torrent-file: single-file parse", () => {
  it("extracts name, totalSize and a single file entry", async () => {
    const parsed = await parseTorrentFile(
      buildSingleFileTorrent({ name: "movie.mkv", length: 5000 }),
    );
    expect(parsed.name).toBe("movie.mkv");
    expect(parsed.totalSize).toBe(5000);
    expect(parsed.files).toHaveLength(1);
    expect(parsed.files[0]?.length).toBe(5000);
    expect(parsed.files[0]?.fullPath).toBe("movie.mkv");
    expect(parsed.files[0]?.path).toEqual(["movie.mkv"]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Multi-file parse: name / totalSize / files
// ─────────────────────────────────────────────────────────────────────────────

describe("torrent-file: multi-file parse", () => {
  it("extracts every file and sums totalSize across files", async () => {
    const parsed = await parseTorrentFile(
      buildMultiFileTorrent(
        [
          { path: ["E01.mkv"], length: 1000 },
          { path: ["subs", "E01.srt"], length: 50 },
          { path: ["E02.mkv"], length: 1200 },
        ],
        "Season 1",
      ),
    );
    expect(parsed.name).toBe("Season 1");
    expect(parsed.files).toHaveLength(3);
    expect(parsed.totalSize).toBe(2250);
    // Nested path joins with "/".
    expect(parsed.files[1]?.fullPath).toBe("subs/E01.srt");
    expect(parsed.files[1]?.path).toEqual(["subs", "E01.srt"]);
    expect(parsed.files[2]?.length).toBe(1200);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Tracker extraction
// ─────────────────────────────────────────────────────────────────────────────

describe("torrent-file: tracker extraction", () => {
  it("extracts the primary announce URL", async () => {
    const parsed = await parseTorrentFile(
      buildSingleFileTorrent({ announce: "udp://tracker.example:1337/announce" }),
    );
    expect(parsed.trackers).toContain("udp://tracker.example:1337/announce");
  });

  it("merges announce + announce-list and deduplicates", async () => {
    const parsed = await parseTorrentFile(
      buildSingleFileTorrent({
        announce: "udp://a.example/announce",
        announceList: [
          ["udp://a.example/announce"], // duplicate of primary
          ["http://b.example/announce"],
          ["http://c.example/announce"],
        ],
      }),
    );
    expect(parsed.trackers).toEqual([
      "udp://a.example/announce",
      "http://b.example/announce",
      "http://c.example/announce",
    ]);
  });

  it("returns no trackers for a trackerless torrent", async () => {
    const parsed = await parseTorrentFile(buildSingleFileTorrent());
    expect(parsed.trackers).toHaveLength(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Private-flag detection
// ─────────────────────────────────────────────────────────────────────────────

describe("torrent-file: private flag", () => {
  it("detects isPrivate=true when private=1", async () => {
    const parsed = await parseTorrentFile(
      buildSingleFileTorrent({ isPrivate: true }),
    );
    expect(parsed.isPrivate).toBe(true);
  });

  it("detects isPrivate=false when the private flag is absent", async () => {
    const parsed = await parseTorrentFile(
      buildSingleFileTorrent({ isPrivate: false }),
    );
    expect(parsed.isPrivate).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Piece count
// ─────────────────────────────────────────────────────────────────────────────

describe("torrent-file: piece count", () => {
  it("reports numPieces = pieces.length / 20", async () => {
    const parsed = await parseTorrentFile(
      buildSingleFileTorrent({ pieceCount: 12 }),
    );
    expect(parsed.numPieces).toBe(12);
  });

  it("reports a different piece count for a different pieces blob", async () => {
    const parsed = await parseTorrentFile(
      buildSingleFileTorrent({ pieceCount: 3 }),
    );
    expect(parsed.numPieces).toBe(3);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Magnet generation
// ─────────────────────────────────────────────────────────────────────────────

describe("torrent-file: magnet generation", () => {
  it("builds a magnet URI carrying the parsed infohash + name", async () => {
    const parsed = await parseTorrentFile(
      buildSingleFileTorrent({ name: "Big Buck Bunny" }),
    );
    const magnet = buildMagnetFromTorrent(parsed);
    expect(magnet).toContain(`xt=urn:btih:${parsed.infohash}`);
    expect(magnet).toContain(`dn=${encodeURIComponent("Big Buck Bunny")}`);
    expect(magnet.startsWith("magnet:?")).toBe(true);
  });

  it("folds (sanitized) trackers into the magnet as tr= params", async () => {
    const parsed = await parseTorrentFile(
      buildSingleFileTorrent({
        announce: "udp://open.tracker/announce",
      }),
    );
    const magnet = buildMagnetFromTorrent(parsed);
    expect(magnet).toContain(`tr=${encodeURIComponent("udp://open.tracker/announce")}`);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Passkey sanitization — the secret must NOT survive into exposed/log form
// ─────────────────────────────────────────────────────────────────────────────

describe("torrent-file: passkey sanitization", () => {
  const PASSKEY = "deadbeefcafebabe0123456789abcdef01234567"; // 40-char hex passkey

  it("strips a path-segment passkey from the exposed trackers", async () => {
    const announce = `https://private.tracker/${PASSKEY}/announce`;
    const parsed = await parseTorrentFile(buildSingleFileTorrent({ announce }));
    // The passkey must NOT survive anywhere in the exposed tracker list.
    const joined = parsed.trackers.join("|");
    expect(joined).not.toContain(PASSKEY);
    // …but the recognizable structure is preserved.
    expect(parsed.trackers[0]).toBe("https://private.tracker/<redacted>/announce");
  });

  it("strips a query-parameter passkey from the exposed trackers", async () => {
    const announce = `https://private.tracker/announce?passkey=${PASSKEY}&foo=bar`;
    const parsed = await parseTorrentFile(buildSingleFileTorrent({ announce }));
    const joined = parsed.trackers.join("|");
    expect(joined).not.toContain(PASSKEY);
    expect(parsed.trackers[0]).toContain("passkey=<redacted>");
    expect(parsed.trackers[0]).toContain("foo=bar"); // non-secret param preserved
  });

  it("the generated magnet does not leak the passkey", async () => {
    const announce = `https://private.tracker/${PASSKEY}/announce`;
    const parsed = await parseTorrentFile(buildSingleFileTorrent({ announce }));
    const magnet = buildMagnetFromTorrent(parsed);
    expect(magnet).not.toContain(PASSKEY);
  });

  it("sanitizePasskeyFromUrl redacts both shapes directly", () => {
    expect(sanitizePasskeyFromUrl(`https://t/${PASSKEY}/announce`)).toBe(
      "https://t/<redacted>/announce",
    );
    expect(
      sanitizePasskeyFromUrl(`https://t/announce?pid=${PASSKEY}`),
    ).toBe("https://t/announce?pid=<redacted>");
    // A non-secret URL is returned unchanged.
    expect(sanitizePasskeyFromUrl("https://t/announce")).toBe(
      "https://t/announce",
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Malformed-input rejection
// ─────────────────────────────────────────────────────────────────────────────

describe("torrent-file: malformed input rejection", () => {
  it("rejects non-bencode garbage bytes", async () => {
    await expect(
      parseTorrentFile(new Uint8Array([0xff, 0x00, 0x42])),
    ).rejects.toBeInstanceOf(ParseError);
  });

  it("rejects a torrent missing the info dictionary", async () => {
    const bytes = encode({ announce: "udp://x/announce" });
    await expect(parseTorrentFile(bytes)).rejects.toBeInstanceOf(ParseError);
  });

  it("rejects a torrent whose info dict has no name", async () => {
    const bytes = encode({
      info: { length: 10, "piece length": 256, pieces: makePieces(1) },
    });
    await expect(parseTorrentFile(bytes)).rejects.toBeInstanceOf(ParseError);
  });

  it("rejects a top-level bencode list (not a dict)", async () => {
    const bytes = encode([1, 2, 3] as BencodeValue);
    await expect(parseTorrentFile(bytes)).rejects.toBeInstanceOf(ParseError);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// parseTorrentFromUrl — download + parse (fetch is the ONLY boundary mocked,
// per §11.4.27 unit-test allowance; the parse path is the REAL parser).
// ─────────────────────────────────────────────────────────────────────────────
describe("parseTorrentFromUrl", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("downloads and parses a real .torrent, returning the parsed metadata", async () => {
    const bytes = buildSingleFileTorrent({ name: "ubuntu.iso", length: 2048 });
    const ab = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        statusText: "OK",
        headers: { get: () => "application/x-bittorrent" },
        arrayBuffer: async () => ab,
      })),
    );
    const parsed = await parseTorrentFromUrl("https://tracker.example/x.torrent");
    // User-observable outcome: the parsed name + size come from the REAL parser,
    // not the mock. RED-on-regression: if the success branch dropped the
    // `parseTorrentFile(data)` call, name would be "" and this fails.
    expect(parsed.name).toBe("ubuntu.iso");
    expect(parsed.totalSize).toBe(2048);
  });

  it("throws ParseError with the HTTP status on a non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 404,
        statusText: "Not Found",
        headers: { get: () => null },
        arrayBuffer: async () => new ArrayBuffer(0),
      })),
    );
    // RED-on-regression: if the `!response.ok` guard were dropped, an empty
    // body would reach the parser and throw a DIFFERENT (decode) error, so the
    // message assertion below would fail.
    await expect(
      parseTorrentFromUrl("https://tracker.example/missing.torrent"),
    ).rejects.toThrow(/HTTP 404/);
  });

  it("wraps a network/transport failure as a ParseError (not a raw fetch error)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("ECONNREFUSED");
      }),
    );
    // RED-on-regression: without the catch-and-rewrap, the raw Error("ECONNREFUSED")
    // would surface instead of a ParseError and `toBeInstanceOf(ParseError)` fails.
    await expect(
      parseTorrentFromUrl("https://tracker.example/x.torrent"),
    ).rejects.toBeInstanceOf(ParseError);
  });

  it("still parses on an unexpected content-type (warns but does not reject)", async () => {
    const bytes = buildSingleFileTorrent({ name: "weird.iso" });
    const ab = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        statusText: "OK",
        headers: { get: () => "text/html" }, // unexpected — must warn, not fail
        arrayBuffer: async () => ab,
      })),
    );
    const parsed = await parseTorrentFromUrl("https://tracker.example/x.torrent");
    // RED-on-regression: if the content-type check rejected instead of warning,
    // this would throw and the name assertion never runs.
    expect(parsed.name).toBe("weird.iso");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// computeInfohash error path — a non-ParseError thrown inside is wrapped.
// ─────────────────────────────────────────────────────────────────────────────
describe("computeInfohash error handling", () => {
  it("throws a ParseError for a buffer with no extractable info dict", async () => {
    // "de" is a valid empty bencode dict with NO `info` key → extractInfoDictBytes
    // throws a ParseError, which must surface as a ParseError (not a raw throw).
    const notATorrent = ascii("de");
    await expect(computeInfohash(notATorrent)).rejects.toBeInstanceOf(ParseError);
  });

  it("throws a ParseError for entirely non-bencode garbage", async () => {
    const garbage = ascii("this is not bencode at all !!!");
    await expect(computeInfohash(garbage)).rejects.toBeInstanceOf(ParseError);
  });
});
