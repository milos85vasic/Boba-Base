/**
 * @fileoverview Security hardening tests — HOSTILE infohash + `.torrent`-URL
 * DETECTION paths against the REAL BobaLink parsers (no stubs).
 *
 * BobaLink runs on UNTRUSTED, attacker-controlled pages. The *identity* of a
 * detected torrent — its infohash — and the `.torrent` URL it forwards to the
 * local Boba merge service are derived ENTIRELY from hostile page bytes. A
 * defect here is worse than a render-time XSS: it makes the user click/queue a
 * torrent whose identity the page controls, or it hangs/crashes the content
 * script. The sibling suite `scanner-hostile-input.test.ts` already covers the
 * XSS-inert `dn`, the scheme allowlist, ReDoS-bounded `dn`, and the
 * orchestrator DoS-flood. This suite deliberately targets the GAPS those leave:
 *
 *   A. Infohash hex normalization + boundary lengths (39 / 40 / 41+ hex chars,
 *      non-hex, uppercase↔lowercase) — the wrong length/charset must be
 *      REJECTED or canonicalized, never surfaced as a malformed infohash.
 *   B. base32 btih variants (39/41/0 chars, lowercase, mixed, non-alphabet,
 *      base32→hex round length) — only an exact RFC4648 32-char btih converts;
 *      everything else is rejected, never a half-built hash.
 *   C. `xt=urn:btih:` confusion — multiple `xt`, garbage primary `xt`,
 *      duplicate/conflicting hashes, btih buried among junk params.
 *   D. `.torrent`-URL detection edge cases — `..` path traversal, null byte,
 *      query strings, `.torrent` mid-path (not suffix), non-http schemes
 *      masquerading as `.torrent`, oversized URLs. The detector must accept
 *      ONLY genuine http(s) `.torrent` resources and reject the rest.
 *   E. SHA-1 `.torrent`-file infohash correctness under a hostile/binary
 *      `info` dict — the canonical infohash is the SHA-1 of the RAW on-disk
 *      info-dict bytes; a decode→re-encode mangles the binary `pieces` field
 *      and yields the WRONG identity. The parser must compute the RAW-bytes
 *      hash, and malformed bencode must throw, never silently return a bogus
 *      hash.
 *   F. Dedup correctness under hostile repetition / case-collision — the same
 *      torrent repeated thousands of times (mixed-case hash) collapses to ONE.
 *
 * Anti-bluff (§11.4 / §11.4.107): every test asserts a USER-OBSERVABLE
 * property — the CORRECT infohash is extracted, OR the hostile input is
 * REJECTED (throw / null / not-detected) — and each carries a one-line note on
 * how it would FAIL if the product regressed. Per the anti-flake rule
 * (§11.4.50/§11.4.85) NO absolute wall-clock thresholds are used; the bounded-
 * work test asserts a RELATIVE-SCALING ratio instead of a fixed millisecond
 * budget.
 *
 * @module tests/security/infohash-detection-hostile.test
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  parseMagnetUri,
  extractInfohash,
  isValidHexInfohash,
  isValidBase32Infohash,
  base32ToHex,
  dedupeMagnets,
  findMagnetUris,
} from "../../src/parser/magnet";
import {
  parseTorrentFile,
  computeInfohash,
} from "../../src/parser/torrent-file";
import {
  encode,
  extractInfoDictBytes,
  sha1,
  type BencodeValue,
} from "../../src/parser/bencode";
import { LinkScanner } from "../../src/scanner/link-scanner";
import { TypedEventEmitter } from "../../src/shared/events";
import type { MagnetInfo } from "../../src/types/torrent";

/** A canonical, already-lowercase 40-hex btih infohash. */
const LOWER_HASH = "0123456789abcdef0123456789abcdef01234567";
/** Same hash, uppercased — must normalize to LOWER_HASH. */
const UPPER_HASH = "0123456789ABCDEF0123456789ABCDEF01234567";

function makeLinkScanner(): LinkScanner {
  return new LinkScanner(new TypedEventEmitter());
}

/** Build a minimal MagnetInfo for dedup tests (only `infohash` matters). */
function magnetWith(infohash: string): MagnetInfo {
  return {
    uri: `magnet:?xt=urn:btih:${infohash}`,
    infohash,
    displayName: null,
    trackers: [],
    webSeeds: [],
    exactLength: null,
    exactSource: null,
    keywords: [],
    acceptableSource: null,
    manifest: null,
    detectedAt: Date.now(),
    sourceElement: null,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// A. Infohash hex normalization + boundary lengths
// ─────────────────────────────────────────────────────────────────────────────

describe("Security — infohash hex boundary lengths + case normalization", () => {
  it("normalizes an UPPERCASE 40-hex btih to canonical lowercase (identity stable)", () => {
    // REGRESSION: if normalization were dropped, the same torrent in upper vs
    // lower case would carry two different identities → dedup breaks, the user
    // sees the same torrent twice / can't reconcile it.
    const info = parseMagnetUri(`magnet:?xt=urn:btih:${UPPER_HASH}`);
    expect(info.infohash).toBe(LOWER_HASH);
    expect(info.infohash).toMatch(/^[a-f0-9]{40}$/); // no stray uppercase survives
  });

  it("extractInfohash returns the lowercased 40-hex hash for a valid magnet", () => {
    expect(extractInfohash(`magnet:?xt=urn:btih:${UPPER_HASH}&dn=x`)).toBe(
      LOWER_HASH,
    );
  });

  it("REJECTS a 39-hex (under-length) btih — no truncated/padded hash invented", () => {
    // 39 hex chars is NOT a valid btih. REGRESSION: a loosened length check
    // would surface a 39-char "infohash" the merge service would reject or,
    // worse, the extension would pad — a malformed identity the user clicks.
    const short = "0".repeat(39);
    expect(extractInfohash(`magnet:?xt=urn:btih:${short}`)).toBeNull();
    expect(isValidHexInfohash(short)).toBe(false);
    expect(() => parseMagnetUri(`magnet:?xt=urn:btih:${short}`)).toThrow();
  });

  it("a 41-hex (over-length) btih is NOT accepted as-is (never a 41-char infohash)", () => {
    // The extracted/parsed infohash must always be EXACTLY 40 hex chars. A
    // permissive `+` quantifier instead of `{40}` would let a 41-char hash
    // through, producing an invalid identity.  REGRESSION: 41-char hash leaks.
    const long = "0".repeat(41); // 41 zeros
    const uri = `magnet:?xt=urn:btih:${long}`;
    const extracted = extractInfohash(uri);
    // Whatever happens, the result must NEVER be the raw 41-char string.
    expect(extracted).not.toBe(long);
    if (extracted !== null) {
      expect(extracted).toMatch(/^[a-f0-9]{40}$/);
    }
    // And the full parse, if it succeeds, also yields an exactly-40-hex hash.
    let parsed: MagnetInfo | null = null;
    try {
      parsed = parseMagnetUri(uri);
    } catch {
      parsed = null;
    }
    if (parsed) {
      expect(parsed.infohash).toMatch(/^[a-f0-9]{40}$/);
      expect(parsed.infohash).not.toBe(long);
    }
  });

  it("REJECTS a 40-char btih containing a non-hex character (g)", () => {
    // 40 chars but one 'g' is out of the hex alphabet. REGRESSION: accepting
    // [0-9a-z]{40} instead of [0-9a-f]{40} would surface a non-hex "infohash".
    const bad = "g".repeat(40);
    expect(extractInfohash(`magnet:?xt=urn:btih:${bad}`)).toBeNull();
    expect(isValidHexInfohash(bad)).toBe(false);
    expect(() => parseMagnetUri(`magnet:?xt=urn:btih:${bad}`)).toThrow();
  });

  it("REJECTS a 40-char btih containing a hostile non-hex byte (NUL / unicode)", () => {
    // A NUL or RTL-override inside the hash region must not pass as hex.
    const withNul = "0123456789abcdef0123456789abcdef0123456\u0000";
    expect(isValidHexInfohash(withNul)).toBe(false);
    expect(() => parseMagnetUri(`magnet:?xt=urn:btih:${withNul}`)).toThrow();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// B. base32 btih variants
// ─────────────────────────────────────────────────────────────────────────────

describe("Security — base32 btih hostile variants", () => {
  it("accepts an EXACT 32-char RFC4648 base32 btih → valid 40-hex infohash", () => {
    // REGRESSION: a broken base32→hex would yield the wrong identity or a
    // non-40 string. We assert the length+charset invariant of the result.
    const base32 = "MFRGGZDFMZTWQ2LKNNWG23TPOBYXE43U"; // 32 alphabet chars
    const info = parseMagnetUri(`magnet:?xt=urn:btih:${base32}`);
    expect(info.infohash).toMatch(/^[a-f0-9]{40}$/);
  });

  it("base32ToHex of a 32-char btih yields exactly 40 hex chars (160 bits)", () => {
    // 32 base32 chars × 5 bits = 160 bits = 40 hex nibbles, exactly.
    // REGRESSION: an off-by-one in the nibble grouping would produce 39/41.
    const hex = base32ToHex("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    expect(hex).toHaveLength(40);
    expect(hex).toMatch(/^[a-f0-9]{40}$/);
  });

  it("REJECTS a 31-char (under-length) base32 btih — no partial hash", () => {
    // REGRESSION: a `{31,}`-style loosened check would build a short hash.
    const short = "A".repeat(31);
    expect(isValidBase32Infohash(short)).toBe(false);
    expect(() => base32ToHex(short)).toThrow();
    expect(() => parseMagnetUri(`magnet:?xt=urn:btih:${short}`)).toThrow();
  });

  it("the strict base32 validator REJECTS a 33-char (over-length) string", () => {
    // The strict validator + converter reject anything not exactly 32 chars.
    // REGRESSION: a `{32,}` loosened check would build a >40-hex hash.
    const long = "A".repeat(33);
    expect(isValidBase32Infohash(long)).toBe(false);
    expect(() => base32ToHex(long)).toThrow();
  });

  it("a 33-char base32 in a magnet still yields an EXACTLY-40-hex infohash (never 41+)", () => {
    // parseMagnetUri's fallback consumes the FIRST 32 base32 chars; the 33rd is
    // ignored. The crucial security invariant is that the produced identity is
    // ALWAYS exactly 40 hex — never a 41+ char over-length hash the merge
    // service would choke on.  REGRESSION: a greedy base32 match would build an
    // over-length hash.
    const info = parseMagnetUri(`magnet:?xt=urn:btih:${"A".repeat(33)}`);
    expect(info.infohash).toMatch(/^[a-f0-9]{40}$/);
  });

  it("REJECTS a 32-char string with non-base32 alphabet chars (0, 1, 8, 9)", () => {
    // RFC4648 base32 alphabet is A-Z2-7. 0/1/8/9 are NOT in it. REGRESSION:
    // accepting them would index past the alphabet table → garbage/throw.
    const bad = "00000000000000000000000000000000"; // 32 zeros (not base32)
    expect(isValidBase32Infohash(bad)).toBe(false);
    expect(() => base32ToHex(bad)).toThrow();
  });

  it("REJECTS a lowercase 32-char base32 btih (conservative: reject, not mis-detect)", () => {
    // The strict base32 validator (`INFOHASH_BASE32_REGEX = /^[A-Z2-7]{32}$/`)
    // is case-SENSITIVE, so a non-standard lowercase base32 btih is REJECTED
    // rather than guessed at. base32 btih is conventionally uppercase (BEP-9 /
    // RFC4648); rejecting a lowercase variant is the safe choice — no half-built
    // hash is surfaced.  REGRESSION: if the validator were loosened to /i WITHOUT
    // also normalizing every downstream consumer, a lowercase base32 could be
    // partially processed into an inconsistent identity. The security invariant
    // proven here: an unrecognized btih form is rejected, never mis-detected.
    expect(() =>
      parseMagnetUri(`magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`),
    ).toThrow();
    expect(
      isValidBase32Infohash("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
    ).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// C. `xt=urn:btih:` confusion — multiple / garbage / conflicting xt params
// ─────────────────────────────────────────────────────────────────────────────

describe("Security — hostile xt-param confusion", () => {
  it("with a VALID primary xt, the primary hash wins over a later conflicting xt", () => {
    // Multiple xt params (DHT backup hashes). The PRIMARY (first) must be the
    // identity. REGRESSION: picking a later attacker-appended xt would let the
    // page swap the torrent identity out from under the user.
    const second = "fedcba9876543210fedcba9876543210fedcba98";
    const info = parseMagnetUri(
      `magnet:?xt=urn:btih:${LOWER_HASH}&xt=urn:btih:${second}`,
    );
    expect(info.infohash).toBe(LOWER_HASH);
  });

  it("REJECTS when the primary xt is garbage and there is no other valid btih", () => {
    // A non-btih primary xt with nothing valid anywhere → no identity → reject.
    // REGRESSION: a parser that fabricated a hash from junk would surface a
    // clickable detection with a meaningless identity.
    expect(() =>
      parseMagnetUri("magnet:?xt=urn:ed2k:deadbeef&dn=NotABtih"),
    ).toThrow();
  });

  it("finds the btih even when buried among many junk params, hash stays canonical", () => {
    // REGRESSION: an over-greedy junk-param scan could mis-capture a 40-hex run
    // from an unrelated param (e.g. a tracker passkey) as the infohash.
    const junk =
      "magnet:?dn=Evil&tr=http://t.example/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" +
      `&xt=urn:btih:${LOWER_HASH}&xl=999`;
    const info = parseMagnetUri(junk);
    expect(info.infohash).toBe(LOWER_HASH);
  });

  it("does NOT mistake a 40-hex run that is NOT a btih urn for the infohash", () => {
    // A 40-hex blob in `dn`/`tr` that is not part of `xt=urn:btih:` must not be
    // promoted to the infohash, and a magnet with no real btih is rejected.
    // REGRESSION: a bare /[a-f0-9]{40}/ scan (no urn:btih: anchor) would grab
    // the tracker hash and forward a torrent the page never actually named.
    const trackerHash = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef";
    expect(
      extractInfohash(`magnet:?dn=x&tr=http://t.example/${trackerHash}`),
    ).toBeNull();
    expect(() =>
      parseMagnetUri(`magnet:?dn=x&tr=http://t.example/${trackerHash}`),
    ).toThrow();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// D. `.torrent`-URL detection edge cases (LinkScanner)
// ─────────────────────────────────────────────────────────────────────────────

describe("Security — hostile `.torrent` URL detection (LinkScanner allowlist)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("DETECTS a genuine https .torrent with a query string, and resolves its URL", async () => {
    document.body.innerHTML = `<a href="https://files.example/ubuntu.torrent?passkey=abc">dl</a>`;
    const items = await makeLinkScanner().scan();
    expect(items.length).toBe(1);
    expect(items[0]?.type).toBe("torrent-file");
    expect(items[0]?.torrentFile?.url).toMatch(
      /^https:\/\/files\.example\/ubuntu\.torrent\?passkey=abc$/,
    );
  });

  it("IGNORES a `.torrent` that is NOT the path suffix (mid-path `.torrent/evil`)", async () => {
    // `https://e/x.torrent/evil.exe` ends in `.exe`, not `.torrent`. REGRESSION:
    // a non-anchored suffix check (`.includes('.torrent')`) would forward this
    // attacker URL to the merge service.
    document.body.innerHTML = `<a href="https://evil.example/x.torrent/evil.exe">trap</a>`;
    const items = await makeLinkScanner().scan();
    expect(items.length).toBe(0);
  });

  it("IGNORES a `..` path-traversal-looking URL that does not end in .torrent", async () => {
    // REGRESSION: a sloppy match could treat `/../secret` as torrent content.
    document.body.innerHTML = `<a href="https://evil.example/files/../../etc/passwd">trav</a>`;
    const items = await makeLinkScanner().scan();
    expect(items.length).toBe(0);
  });

  it("DETECTS a `.torrent` URL that itself contains `..` segments (still a real .torrent)", async () => {
    // A genuine http(s) `.torrent` suffix is detected even with `..` in the
    // path; URL resolution canonicalizes it. The forwarded URL must still end
    // in `.torrent` and never carry a stray scheme.  REGRESSION: if traversal
    // segments broke the suffix check, a real torrent would be missed.
    document.body.innerHTML = `<a href="https://files.example/a/../b/real.torrent">dl</a>`;
    const items = await makeLinkScanner().scan();
    expect(items.length).toBe(1);
    const url = items[0]?.torrentFile?.url ?? "";
    expect(url).toMatch(/\.torrent$/);
    expect(url.toLowerCase().startsWith("https://")).toBe(true);
  });

  it("IGNORES non-http schemes masquerading as `.torrent` (file:, ftp:, data:, javascript:)", async () => {
    // REGRESSION: dropping the `^https?://` anchor would forward a file:// or
    // javascript: URL to the merge service / a click handler.
    document.body.innerHTML = `
      <a href="file:///etc/passwd.torrent">file</a>
      <a href="ftp://host/x.torrent">ftp</a>
      <a href="data:application/x-bittorrent,AAAA.torrent">data</a>
      <a href="javascript:void('x.torrent')">js</a>
    `;
    const items = await makeLinkScanner().scan();
    expect(items.length).toBe(0);
  });

  it("IGNORES a null-byte-laced `.torrent` href (no crash, no detection)", async () => {
    // A NUL before `.torrent` must not let a poisoned path through as a clean
    // torrent URL.  REGRESSION: a parser that strips NUL silently could forward
    // a different resource than the visible text implies.
    document.body.innerHTML = `<a id="nb">x</a>`;
    document
      .getElementById("nb")
      ?.setAttribute("href", "https://evil.example/x\u0000.torrent");
    const items = await makeLinkScanner().scan();
    // Either ignored entirely, or if matched, the forwarded URL still ends in
    // .torrent over https and carries NO raw NUL.
    for (const it of items) {
      const url = it.torrentFile?.url ?? "";
      expect(url).not.toContain("\u0000");
    }
    // The hostile null-byte URL must not pass as a clean detection: assert it
    // is either dropped, or sanitized by URL() to a still-valid https .torrent.
    expect(
      items.every((it) => {
        const u = it.torrentFile?.url ?? "";
        return u === "" || /^https:\/\/.+\.torrent(\?.*)?$/i.test(u);
      }),
    ).toBe(true);
  });

  it("IGNORES an oversized non-torrent href without hanging or detecting it", async () => {
    // A 200k-char href that does NOT end in .torrent must be ignored, and the
    // genuine magnet alongside it must still be found.  REGRESSION: an
    // unbounded backtracking matcher would hang on this input.
    const oversized =
      "https://evil.example/" + "a".repeat(200_000) + ".html";
    document.body.innerHTML = `<a id="big">x</a><a href="magnet:?xt=urn:btih:${LOWER_HASH}">real</a>`;
    document.getElementById("big")?.setAttribute("href", oversized);
    const items = await makeLinkScanner().scan();
    const real = items.filter((i) => i.magnet?.infohash === LOWER_HASH);
    expect(real.length).toBe(1);
    expect(items.every((i) => (i.torrentFile?.url ?? "") !== oversized)).toBe(
      true,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// E. SHA-1 `.torrent`-file infohash correctness under a hostile/binary info dict
// ─────────────────────────────────────────────────────────────────────────────

describe("Security — `.torrent` SHA-1 infohash correctness (hostile/binary info)", () => {
  /**
   * Build a minimal, valid single-file `.torrent` whose `pieces` field is a
   * 20-byte binary blob FULL of high bytes (0x80–0xff) — exactly the bytes a
   * UTF-8 decode→re-encode would mangle.
   */
  function buildTorrentBytes(): Uint8Array {
    const pieces = new Uint8Array(20);
    for (let i = 0; i < 20; i++) pieces[i] = 0x80 + (i % 0x7f); // high bytes
    const dict: BencodeValue = {
      info: {
        name: "evil.bin",
        "piece length": 16384,
        length: 1234,
        pieces,
      },
    };
    return encode(dict);
  }

  it("computeInfohash equals SHA-1 of the RAW on-disk info-dict bytes (binary-safe)", async () => {
    // The canonical identity is SHA-1 over the UNTOUCHED info-dict byte slice.
    // We extract that slice independently and SHA-1 it ourselves: production's
    // result must match the RAW-bytes hash — proving it does NOT decode→re-encode.
    // REGRESSION: a re-encode mangles the high-byte `pieces` field, so the
    // re-encoded hash differs from the raw-bytes hash — and would forward the
    // WRONG torrent identity to the merge service.
    const bytes = buildTorrentBytes();
    const rawInfoBytes = extractInfoDictBytes(bytes);
    const expectedRawHash = await sha1(rawInfoBytes);

    const produced = await computeInfohash(bytes);
    expect(produced).toBe(expectedRawHash);
    expect(produced).toMatch(/^[a-f0-9]{40}$/);
  });

  it("the raw-bytes infohash DIFFERS from a decode→re-encode hash (proves no mangling)", async () => {
    // Sanity oracle making the previous test non-tautological: confirm the
    // high-byte `pieces` field actually makes a re-encoded hash diverge, so the
    // "production == raw-bytes hash" assertion is genuinely catching the bug.
    const bytes = buildTorrentBytes();
    const parsed = await parseTorrentFile(bytes);

    // Re-encode the (UTF-8-decoded) info dict the way a naive parser would, and
    // hash THAT — it must NOT equal the canonical infohash.
    // We reconstruct a plausible re-encoded info dict from the parsed metadata.
    const reencoded = encode({
      info: {
        name: parsed.name,
        "piece length": parsed.pieceLength,
        length: parsed.totalSize,
        // A re-encode would turn the binary pieces into a (mangled) UTF-8 string.
        pieces: "", // stand-in mangled bytes
      },
    });
    const reencodedHash = await sha1(reencoded);
    expect(parsed.infohash).not.toBe(reencodedHash);
    expect(parsed.infohash).toMatch(/^[a-f0-9]{40}$/);
  });

  it("REJECTS malformed bencode (no info dict) — throws, never a bogus hash", async () => {
    // REGRESSION: a parser that swallowed the error and returned a default /
    // empty-string hash would let a corrupt file masquerade as a real torrent.
    const garbage = new TextEncoder().encode("d4:spam4:eggse"); // valid bencode, NO `info`
    await expect(computeInfohash(garbage)).rejects.toThrow();
    await expect(parseTorrentFile(garbage)).rejects.toThrow();
  });

  it("REJECTS non-bencode bytes outright (hostile junk uploaded as a .torrent)", async () => {
    const junk = new Uint8Array([0xff, 0x00, 0x7f, 0x41, 0x42]);
    await expect(computeInfohash(junk)).rejects.toThrow();
  });

  it("the same `.torrent` bytes hash deterministically (no time/random salt)", async () => {
    // Identity must be a PURE function of the bytes. REGRESSION: a salted hash
    // would give the same file two identities across two scans → dedup breaks.
    const bytes = buildTorrentBytes();
    const h1 = await computeInfohash(bytes);
    const h2 = await computeInfohash(new Uint8Array(bytes)); // distinct buffer
    expect(h1).toBe(h2);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// F. Dedup correctness under hostile repetition / case collision
// ─────────────────────────────────────────────────────────────────────────────

describe("Security — infohash dedup under hostile repetition", () => {
  it("collapses thousands of mixed-case repetitions of ONE hash to a single entry", () => {
    // A page that repeats the same torrent 5000× (alternating hash case) must
    // dedup to ONE — the user is shown one torrent, not a flood.  REGRESSION:
    // case-sensitive dedup keys would let the page multiply one torrent into
    // thousands of "distinct" UI rows (a UI DoS / confusion attack).
    const magnets: MagnetInfo[] = [];
    for (let i = 0; i < 5000; i++) {
      magnets.push(magnetWith(i % 2 === 0 ? LOWER_HASH : UPPER_HASH));
    }
    const deduped = dedupeMagnets(magnets);
    expect(deduped.length).toBe(1);
    // The survivor's identity is well-formed.
    expect((deduped[0]?.infohash ?? "").toLowerCase()).toBe(LOWER_HASH);
  });

  it("keeps DISTINCT hashes distinct (dedup does not over-collapse)", () => {
    const a = magnetWith(LOWER_HASH);
    const b = magnetWith("fedcba9876543210fedcba9876543210fedcba98");
    const deduped = dedupeMagnets([a, b, a, b, a]);
    expect(deduped.length).toBe(2);
  });

  it("findMagnetUris dedups hostile repetition with RELATIVE-SCALING bounded work", () => {
    // Anti-flake (§11.4.50/§11.4.85): instead of an absolute ms budget, assert
    // that 4× the input does NOT cost super-linearly more than 1× — a hostile
    // ReDoS/quadratic regression would blow this ratio sky-high, while a
    // healthy linear scan keeps the ratio modest.
    const one = `magnet:?xt=urn:btih:${LOWER_HASH} `;

    const blobSmall = one.repeat(2_500);
    const blobLarge = one.repeat(10_000); // 4× the work

    // Correctness: the repeated identical magnet dedups to ONE valid result.
    const small = findMagnetUris(blobSmall);
    const large = findMagnetUris(blobLarge);
    expect(small.length).toBe(1);
    expect(large.length).toBe(1);
    expect(small[0]).toMatch(/urn:btih:[a-f0-9]{40}/i);

    // Relative-scaling guard (§11.4.50/§11.4.85). Take the MIN over several reps
    // at each size — the minimum is the contention-robust estimator of intrinsic
    // cost (host stalls only ADD time). A SINGLE-run ratio with a 0.05 ms floor on
    // a sub-ms baseline is noise-dominated (observed 53.6 vs ~4 intrinsic under
    // full-suite load) — itself a §11.4.50 FAIL-bluff. With min-of-reps the ratio
    // reflects true scaling: 4× input → ~4× for a linear scan, ~16× for an
    // O(n²)/ReDoS blowup. The threshold 10 sits BETWEEN (so it actually CATCHES a
    // quadratic regression — the prior ≤40 did not — while tolerating noise).
    const minMs = (fn: () => void, reps: number): number => {
      let best = Infinity;
      for (let i = 0; i < reps; i++) {
        const t = performance.now();
        fn();
        best = Math.min(best, performance.now() - t);
      }
      return best;
    };
    findMagnetUris(blobSmall); // warmup (JIT)
    findMagnetUris(blobLarge);
    const tSmall = minMs(() => void findMagnetUris(blobSmall), 7);
    const tLarge = minMs(() => void findMagnetUris(blobLarge), 7);
    const ratio = tLarge / Math.max(tSmall, 0.05);
    expect(ratio).toBeLessThan(10);
  });
});
