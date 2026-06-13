/**
 * @fileoverview HOSTILE-INPUT robustness tests for the REAL bencode decoder +
 * .torrent-file parser + infohash computation (parser/bencode.ts,
 * parser/torrent-file.ts).
 *
 * THREAT MODEL. A `.torrent` file is attacker-controlled binary that a private
 * tracker page hands the extension. The bencode decoder runs in the background
 * service-worker; an adversarial blob must never (a) hang the worker, (b) crash
 * it uncatchably, (c) mis-parse into a partial/bogus structure, nor (d) produce
 * a bogus infohash. These tests feed the REAL parser deliberately malformed and
 * adversarial bencode in BOUNDED time and assert it rejects cleanly (throws a
 * catchable error / returns), never a silent partial mis-parse and never a hang.
 *
 * ANTI-BLUFF (Constitution §11.4 / §11.4.1 / §11.4.6 / §11.4.50):
 *   - Imports the REAL modules under test (no stub, no mock).
 *   - Every assertion inspects a user-observable outcome — the thrown error, the
 *     decoded value, the byte-exact infohash — NOT merely "did not throw".
 *   - The decoder is LENIENT in places the bencode spec is strict (leading-zero
 *     and negative-zero integers). These tests assert what the code ACTUALLY
 *     does (proven by an out-of-band probe in the authoring session), NOT what
 *     the spec idealizes — pinning real behavior so a future regression is
 *     caught, and avoiding a FAIL-bluff (§11.4.1) that asserts spec-fiction.
 *   - "Bounded time" is asserted by RELATIVE SCALING against a baseline parse,
 *     never an absolute wall-clock ms threshold (§11.4.50 forbids hardcoded
 *     timing literals — they are machine/load dependent and flaky).
 *
 * SCOPE — gaps left by the sibling suites (intentionally NON-overlapping):
 *   - tests/unit/bencode.test.ts already covers simple truncation, trailing
 *     garbage, non-digit-in-int, empty-int `ie`, unterminated list/dict, bad
 *     leading byte, empty input, off-end length `5`.
 *   - tests/unit/torrent-file.test.ts already covers missing-info, no-name,
 *     top-level-list, garbage bytes, and the infohash determinism/correctness.
 *   - tests/security/infohash-detection-hostile.test.ts covers infohash
 *     hex/base32 detection, .torrent SHA-1 correctness, and URL allowlisting.
 * This file targets the PARSER-ROBUSTNESS gaps those leave: adversarial bencode
 * STRUCTURE — deep truncation positions, hostile length prefixes, integer-form
 * edge cases, stack-depth bounds, wrong-typed/duplicate `info`, and raw-byte
 * (NUL / high-byte) infohash exactness.
 *
 * NOTE on NUL bytes: control/NUL bytes are written with `\x00`-style ESCAPES
 * and assembled via `bytes()` — NEVER a raw NUL in the source (a raw NUL makes
 * git store the file as binary).
 */

import { describe, it, expect } from "vitest";

import {
  decode,
  extractInfoDictBytes,
  type BencodeValue,
} from "../../src/parser/bencode";
import {
  parseTorrentFile,
  computeInfohash,
} from "../../src/parser/torrent-file";
import { ParseError } from "../../src/shared/errors";

// ─────────────────────────────────────────────────────────────────────────────
// Byte helpers — adversarial inputs are built from char codes (incl. NUL via
// escape), never raw control bytes in the file.
// ─────────────────────────────────────────────────────────────────────────────

/** UTF-8 encode an ASCII/printable literal bencode string. */
const enc = (s: string): Uint8Array => new TextEncoder().encode(s);

/** Build a byte array from a latin1/escape string so NUL/high bytes are exact. */
function bytes(s: string): Uint8Array {
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i) & 0xff;
  return out;
}

/** Concatenate byte chunks (hand-assemble a root .torrent buffer). */
function concat(...chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.length;
  }
  return out;
}

/** Independent SHA-1 oracle over raw bytes (does NOT touch the parser). */
async function sha1Hex(raw: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-1", new Uint8Array(raw));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** A nested-list bencode buffer of depth `n`: `l…l e…e`. */
function nestedLists(n: number): Uint8Array {
  return enc("l".repeat(n) + "e".repeat(n));
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. Truncation at every structural boundary
//
// Regression: a truncated buffer must reject cleanly (throw ParseError) — it
// must NEVER return a partial/half-built value, and must NEVER read off the end
// into `undefined`-arithmetic. A no-op stub that returned `{}`/`undefined` on
// any of these would FAIL these tests.
// ─────────────────────────────────────────────────────────────────────────────

describe("hostile bencode: truncation at structural boundaries rejects cleanly", () => {
  // Each case cuts the input at a different position so the decoder is forced to
  // hit "unexpected end" from a DIFFERENT internal state (mid-string-content,
  // mid-key, after-key-before-value, mid-nested-dict, mid-integer-digits).
  const truncated: Array<[string, Uint8Array]> = [
    ["mid string content (claims 5, gives 2)", enc("5:ab")],
    ["string length prefix then bare colon, no body", enc("3:")],
    ["dict opened, key only, no value", enc("d3:key")],
    ["dict, key + value, no terminating 'e'", enc("d3:keyi1e")],
    ["dict, key + value-key, value-value missing", enc("d3:key3:val3:key")],
    ["nested dict inner unterminated", enc("d4:infod1:ai1e")],
    ["list with one item, no terminator", enc("l3:abc")],
    ["nested list inner unterminated", enc("lli1e")],
    ["integer opened, sign only, no digits, no 'e'", enc("i-")],
    ["integer digits, no terminator", enc("i123")],
    ["lone 'd' (empty dict body, no end)", enc("d")],
    ["lone 'l' (empty list body, no end)", enc("l")],
    ["lone 'i' (no digits, no end)", enc("i")],
  ];

  for (const [label, input] of truncated) {
    it(`rejects: ${label}`, () => {
      // Must throw — and specifically a ParseError, never a RangeError/TypeError
      // from undefined-arithmetic, never a silent partial return.
      let threw = false;
      let value: unknown;
      try {
        value = decode(input);
      } catch (e) {
        threw = true;
        expect(e).toBeInstanceOf(ParseError);
      }
      expect(threw).toBe(true);
      // The partial value must never have been produced.
      expect(value).toBeUndefined();
    });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. Hostile length prefixes
//
// Regression: a string length that exceeds the available bytes must be rejected
// by the over-length guard BEFORE any allocation/slice — never an OOM attempt,
// never a hang, never a slice of garbage past the buffer end. A non-numeric or
// fractional length must be rejected at the digit check.
// ─────────────────────────────────────────────────────────────────────────────

describe("hostile bencode: invalid/oversized length prefixes reject without allocation", () => {
  it("rejects a length far larger than the data (claims 999999, has 3)", () => {
    expect(() => decode(enc("999999:abc"))).toThrow(ParseError);
  });

  it("rejects a length that overflows JS Number precision and still exceeds data", () => {
    // 22 nines: length parses to a (lossy) huge float but the over-length guard
    // (pos + length > data.length) fires regardless — clean reject, no hang, no
    // attempted allocation of a multi-exabyte buffer.
    expect(() => decode(enc("9999999999999999999999:x"))).toThrow(ParseError);
  });

  it("the oversized-length rejection mentions the over-extent (not a generic crash)", () => {
    // User-observable: the error explains the length exceeds the data, proving
    // the over-length guard fired (not an undefined-read TypeError).
    expect(() => decode(enc("100:short"))).toThrow(/extends past end of data/);
  });

  it("rejects a fractional length prefix '1.5:' at the digit check", () => {
    expect(() => decode(enc("1.5:ab"))).toThrow(/Invalid digit in string length/);
  });

  it("rejects a negative length '-1:a' (the '-' is not a valid value start)", () => {
    // '-' begins no bencode type, so the top-level value dispatch rejects it.
    expect(() => decode(enc("-1:a"))).toThrow(ParseError);
  });

  it("rejects a length prefix that runs to EOF with no colon", () => {
    // ACTUAL behavior (proven by run): digits parse to EOF, the loop exits
    // without a colon, and the over-length guard then fires ("extends past end")
    // because the claimed length has zero bytes after it. Still a clean
    // ParseError — never a hang, never a partial value.
    expect(() => decode(enc("12345"))).toThrow(/extends past end of data/);
  });

  it("rejects a colon-less length whose ONLY content is digits, with no body bytes at all", () => {
    // The distinct "Unterminated string length prefix" path requires NO digits
    // before EOF; a lone non-colon, non-digit-after-start is covered elsewhere.
    // Here we simply assert the colon-less digit run is a ParseError (the class
    // that matters for the threat model), independent of the exact message.
    expect(() => decode(enc("7"))).toThrow(ParseError);
  });

  it("accepts a zero-length string (boundary, not hostile) — proves the guard is not over-eager", () => {
    // Anti-bluff counter-case: '0:' is VALID and must decode to "" — this proves
    // the length-guard rejects only genuine over-extents, not all length=0.
    expect(decode(enc("0:"))).toBe("");
  });

  it("rejects a NUL byte injected into the length-prefix digits", () => {
    // Hostile: "3" + NUL + ":ab" — the NUL is a non-digit, rejected at the
    // digit check (NUL written via escape, never raw in the source).
    expect(() => decode(bytes("3\x00:ab"))).toThrow(/Invalid digit in string length/);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. Malformed integers — assert the parser's ACTUAL (lenient) behavior
//
// The spec forbids leading zeros (i03e) and negative zero (i-0e). This decoder
// is LENIENT: it accepts them and returns the numeric value. We pin the ACTUAL
// behavior (proven by an out-of-band probe in the authoring session), NOT the
// spec ideal — a test asserting "i03e throws" would be a FAIL-bluff (§11.4.1)
// because the code does not throw. The genuinely malformed forms (double sign,
// leading '+', non-digit, trailing sign, empty) ARE rejected, and we pin those.
// ─────────────────────────────────────────────────────────────────────────────

describe("hostile bencode: integer edge forms — ACTUAL parser behavior pinned", () => {
  // ACCEPTED by this (lenient) decoder — value pinned exactly. `i-0e` decodes
  // to NEGATIVE zero (proven by run): the parser applies the leading '-' to a
  // computed 0. We pin -0 with Object.is so the sign is part of the contract.
  const accepted: Array<[string, number]> = [
    ["leading-zero positive 'i03e'", 3],
    ["multi leading-zero 'i007e'", 7],
    ["all-zero 'i00e'", 0],
    ["leading-zero negative 'i-05e'", -5],
  ];
  for (const [label, expected] of accepted) {
    it(`accepts (lenient) ${label} -> ${expected}`, () => {
      const bencode = label.match(/'(.+)'/)?.[1] ?? "";
      // Pin the EXACT recovered number (not "no throw") — a stub returning
      // undefined/0-for-all would fail this.
      expect(decode(enc(bencode))).toBe(expected);
    });
  }

  it("accepts (lenient) negative-zero 'i-0e' and yields exactly -0 (sign pinned)", () => {
    // ACTUAL behavior: the lenient decoder produces -0, NOT +0. Object.is
    // distinguishes them; a future change to normalize -0→+0 would be caught.
    const got = decode(enc("i-0e"));
    expect(Object.is(got, -0)).toBe(true);
  });

  // REJECTED — genuinely malformed integer forms.
  const rejected: Array<[string, string]> = [
    ["double sign 'i--5e'", "i--5e"],
    ["leading plus 'i+5e'", "i+5e"],
    ["trailing sign 'i5-e'", "i5-e"],
    ["non-digit body 'i4x2e'", "i4x2e"],
    ["empty integer 'ie'", "ie"],
    ["sign only 'i-e'", "i-e"],
  ];
  for (const [label, input] of rejected) {
    it(`rejects ${label}`, () => {
      expect(() => decode(enc(input))).toThrow(ParseError);
    });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. Deep nesting — terminates in BOUNDED time, never hangs
//
// Regression: a deeply-nested structure must terminate (parse OR throw) in time
// that scales benignly with depth — it must NOT hang. This recursive-descent
// decoder hits the V8 call-stack limit on very deep input and throws a CATCHABLE
// RangeError (proven by probe: depth 1000 parses, depth 5000 throws RangeError);
// it does NOT spin/hang and does NOT crash uncatchably. We assert both the
// bounded-time property (relative scaling, NO absolute ms) AND that the top-level
// parseTorrentFile wrapper converts the RangeError into a ParseError.
// ─────────────────────────────────────────────────────────────────────────────

describe("hostile bencode: deep nesting terminates in bounded time (no hang)", () => {
  it("a shallow-nesting decode is the baseline (parses to nested arrays)", () => {
    // Depth 50 must parse correctly — proves the decoder handles legitimate
    // nesting before we stress the bound.
    const out = decode(nestedLists(50));
    expect(Array.isArray(out)).toBe(true);
  });

  it("deep nesting either parses or throws — but ALWAYS terminates (relative-scaling bound)", () => {
    // Time a baseline (moderate depth) and a deep input; the deep input must NOT
    // take dramatically (orders of magnitude) longer than baseline — i.e. it
    // terminates, it does not hang. NO absolute ms threshold (§11.4.50): we use
    // a generous relative ceiling that only an actual HANG (effectively
    // unbounded) would breach.
    const time = (fn: () => void): number => {
      const t0 = performance.now();
      try {
        fn();
      } catch {
        /* throwing (RangeError/ParseError) is a valid bounded outcome */
      }
      return performance.now() - t0;
    };

    const baseline = time(() => decode(nestedLists(200)));
    const deep = time(() => decode(nestedLists(50_000)));

    // A hang would make `deep` effectively unbounded relative to `baseline`.
    // Allow a very wide margin (deep does far more work) but require it to be
    // FINITE and bounded: deep must complete within a large multiple of the
    // baseline plus a small floor (baseline can round to ~0ms on a fast host).
    const ceiling = (baseline + 1) * 5000;
    expect(deep).toBeLessThan(ceiling);
  });

  it("deep nesting that overflows the stack is reported as ParseError by parseTorrentFile (catchable, not a crash)", async () => {
    // Wrap a stack-busting nested list as a torrent `info` value and feed the
    // top-level parser. The RangeError from stack exhaustion must be caught and
    // surfaced as a ParseError — never propagate as an uncatchable worker crash.
    const deepInfo = nestedLists(50_000); // overflows recursion
    const torrent = concat(enc("d4:info"), deepInfo, enc("e"));
    await expect(parseTorrentFile(torrent)).rejects.toBeInstanceOf(ParseError);
  });

  it("decode of a stack-busting buffer throws (does not return a partial value)", () => {
    // Direct decode: the result must be a thrown error, never a silently
    // truncated partial structure.
    let threw = false;
    try {
      decode(nestedLists(50_000));
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. Wrong-typed / duplicate / missing `info` — infohash compute does not
//    return a bogus identity through the FULL parser path.
//
// Regression: parseTorrentFile must REJECT a torrent whose `info` is not a
// dictionary (list / int / string), and one that has no `info` at all, rather
// than computing/returning a hash over a non-dict. (The lower-level
// computeInfohash hashes whatever raw `info` byte-slice it finds and is NOT the
// validation layer — pinned separately below so the layering is explicit.)
// ─────────────────────────────────────────────────────────────────────────────

describe("hostile bencode: wrong-typed / duplicate / missing info dict", () => {
  it("parseTorrentFile rejects info-as-list (not a dict)", async () => {
    await expect(parseTorrentFile(enc("d4:infoli1eee"))).rejects.toBeInstanceOf(
      ParseError,
    );
  });

  it("parseTorrentFile rejects info-as-integer (not a dict)", async () => {
    await expect(parseTorrentFile(enc("d4:infoi5ee"))).rejects.toBeInstanceOf(
      ParseError,
    );
  });

  it("parseTorrentFile rejects info-as-string (not a dict)", async () => {
    await expect(parseTorrentFile(enc("d4:info3:abce"))).rejects.toBeInstanceOf(
      ParseError,
    );
  });

  it("parseTorrentFile rejects a torrent with no 'info' key at all", async () => {
    await expect(
      parseTorrentFile(enc("d8:announce5:hello4:spam3:abce")),
    ).rejects.toBeInstanceOf(ParseError);
  });

  it("extractInfoDictBytes throws when the root is not a dictionary", () => {
    // A top-level list / integer has no info dict to extract.
    expect(() => extractInfoDictBytes(enc("li1ei2ee"))).toThrow(ParseError);
    expect(() => extractInfoDictBytes(enc("i5e"))).toThrow(ParseError);
  });

  it("extractInfoDictBytes throws when the dict has no 'info' key", () => {
    expect(() => extractInfoDictBytes(enc("d3:foo3:bare"))).toThrow(
      /missing required 'info'/,
    );
  });

  it("duplicate 'info' keys: extractInfoDictBytes binds the FIRST occurrence (deterministic, not the later attacker-appended one)", () => {
    // d 4:info d1:ai1e e  4:info d1:bi2e e  e
    // First info = d1:ai1ee (8 bytes). A parser that bound the LAST info, or
    // concatenated both, would give a different slice — pinning the first
    // occurrence proves a stable, predictable infohash basis.
    const dup = enc("d4:infod1:ai1ee4:infod1:bi2eee");
    const slice = extractInfoDictBytes(dup);
    expect(new TextDecoder().decode(slice)).toBe("d1:ai1ee");
  });

  it("the duplicate-info infohash equals SHA-1 of the FIRST info slice (no bogus hash)", async () => {
    const dup = enc("d4:infod1:ai1ee4:infod1:bi2eee");
    const firstInfoSlice = enc("d1:ai1ee");
    const expected = await sha1Hex(firstInfoSlice);
    const got = await computeInfohash(dup);
    expect(got).toBe(expected);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 6. Binary-safe: infohash is byte-exact over RAW info bytes (NUL + high bytes)
//
// Regression: the infohash is SHA-1 of the RAW on-disk `info` bytes. If the
// parser decode→re-encoded the dict (or UTF-8-mangled the binary `pieces`), the
// NUL/high bytes would be corrupted and the hash would diverge from the
// independent oracle. The hostile bytes (NUL, 0x80–0xff) are written with
// ESCAPES and assembled via bytes(), never raw in the source file.
// ─────────────────────────────────────────────────────────────────────────────

describe("hostile bencode: binary-safe infohash over raw NUL/high bytes", () => {
  it("decodes a byte-string containing NUL + high bytes byte-exactly (binary mode)", () => {
    // 5 hostile bytes: NUL, 0xff, 0xfe, 0x80, 0x01 — written via escapes.
    const payload = bytes("\x00\xff\xfe\x80\x01");
    const buf = concat(enc("5:"), payload);
    const decoded = decode(buf, { encoding: "binary" });
    expect(decoded).toBeInstanceOf(Uint8Array);
    expect(Array.from(decoded as Uint8Array)).toEqual([0x00, 0xff, 0xfe, 0x80, 0x01]);
  });

  it("infohash of an info dict with NUL/high-byte 'pieces' equals the raw-slice SHA-1 oracle", async () => {
    // Assemble an info dict by hand whose `pieces` is 20 raw bytes including NUL
    // and the full 0x80–0xff range — the bytes that a UTF-8 decode→re-encode
    // would demonstrably corrupt. The infohash must equal SHA-1 over THIS exact
    // on-disk info slice.
    //
    // pieces content (20 bytes), NUL + high bytes via escapes:
    const pieces = bytes(
      "\x00\xff\xfe\x80\x81\x90\xab\xcd\xef\xc0\x00\x7f\x80\xff\x01\x02\xfd\xfc\xfb\x00",
    );
    expect(pieces.length).toBe(20);
    // Sanity: the fixture really contains NUL and high bytes.
    expect(Array.from(pieces)).toContain(0x00);
    expect(Array.from(pieces)).toContain(0xff);
    expect(Array.from(pieces)).toContain(0x80);

    // info dict bytes, hand-built: d 6:length i1024e 4:name 8:test.iso
    //                              12:piece length i256e 6:pieces 20:<pieces> e
    const infoBytes = concat(
      enc("d6:lengthi1024e4:name8:test.iso12:piece lengthi256e6:pieces20:"),
      pieces,
      enc("e"),
    );
    // root: d 4:info <infoBytes> e
    const torrent = concat(enc("d4:info"), infoBytes, enc("e"));

    // Independent oracle: SHA-1 over the raw info slice (NO parser involved).
    const expected = await sha1Hex(infoBytes);

    const fullParsed = await parseTorrentFile(torrent);
    const quick = await computeInfohash(torrent);

    // Both parser paths must reproduce the byte-exact raw-info-dict identity.
    expect(quick).toBe(expected);
    expect(fullParsed.infohash).toBe(expected);
    expect(fullParsed.infohash).toMatch(/^[a-f0-9]{40}$/);
    // 20-byte pieces ⇒ exactly 1 piece, counted from the lossless binary slice
    // (a UTF-8 mis-decode of the high bytes would mis-count).
    expect(fullParsed.numPieces).toBe(1);
  });

  it("a single flipped NUL→high byte in 'pieces' changes the infohash (raw-byte sensitivity)", async () => {
    const mk = (lastByte: number): Uint8Array => {
      const pieces = new Uint8Array(20);
      pieces.fill(0x00);
      pieces[19] = lastByte;
      return concat(
        enc("d6:lengthi1024e4:name8:test.iso12:piece lengthi256e6:pieces20:"),
        pieces,
        enc("e"),
      );
    };
    const a = concat(enc("d4:info"), mk(0x00), enc("e"));
    const b = concat(enc("d4:info"), mk(0xff), enc("e"));
    const ha = await computeInfohash(a);
    const hb = await computeInfohash(b);
    // The raw bytes differ by ONE byte ⇒ the infohash MUST differ. Equal hashes
    // would prove the high byte was UTF-8-mangled into the same value (the bug).
    expect(ha).not.toBe(hb);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 7. Trailing-data / embedded-terminator adversarial structure
//
// Regression: the decoder must consume EXACTLY the input and reject trailing
// attacker bytes — a tolerant parser that ignored trailing data could be tricked
// into hashing one structure while the rest of the file says another.
// ─────────────────────────────────────────────────────────────────────────────

describe("hostile bencode: exact-consumption (no trailing-data tolerance)", () => {
  it("rejects a valid dict followed by attacker trailing bytes", () => {
    expect(() => decode(enc("d3:fooi1eeEXTRA"))).toThrow(/Trailing data/);
  });

  it("rejects a valid integer followed by a second value", () => {
    expect(() => decode(enc("i1ei2e"))).toThrow(/Trailing data/);
  });

  it("rejects a stray 'e' (container terminator at top level)", () => {
    // 'e' is not a valid value start at top level.
    expect(() => decode(enc("e"))).toThrow(ParseError);
  });

  it("rejects a dict key that is not a byte-string (e.g. an integer key)", () => {
    // d i1e i2e e — key position holds an integer, which the decoder treats as
    // an invalid value start for a key (a dict key MUST be a byte string).
    expect(() => decode(enc("di1ei2ee"))).toThrow(ParseError);
  });
});

// Keep the bencode type import referenced (type-only usage proof).
const _typeProbe: BencodeValue = 0;
void _typeProbe;
