/**
 * @fileoverview Unit tests for the bencode parser (parser/bencode.ts).
 *
 * Anti-bluff (Constitution §11.4): imports the REAL module under test (no
 * mocks), every assertion inspects a user-observable outcome (the decoded
 * value, the re-encoded bytes, or the thrown error), and the suite is built to
 * FAIL against a no-op stub of decode/encode — each round-trip asserts the
 * concrete recovered value, not merely "no throw".
 */

import { describe, it, expect } from "vitest";

import {
  encode,
  decode,
  bytesToHex,
  hexToBytes,
  type BencodeValue,
} from "../../src/parser/bencode";
import { ParseError } from "../../src/shared/errors";

/** UTF-8 encode a literal bencode string for decoder inputs. */
const enc = (s: string): Uint8Array => new TextEncoder().encode(s);

describe("bencode: integer type round-trips", () => {
  it("decodes a positive integer to the exact number", () => {
    expect(decode(enc("i42e"))).toBe(42);
  });

  it("decodes zero", () => {
    expect(decode(enc("i0e"))).toBe(0);
  });

  it("decodes a negative integer", () => {
    expect(decode(enc("i-7e"))).toBe(-7);
  });

  it("decodes a large integer", () => {
    expect(decode(enc("i1234567890e"))).toBe(1234567890);
  });

  it("round-trips an integer through encode -> decode", () => {
    const original: BencodeValue = 9001;
    const bytes = encode(original);
    expect(new TextDecoder().decode(bytes)).toBe("i9001e");
    expect(decode(bytes)).toBe(9001);
  });
});

describe("bencode: byte-string type round-trips", () => {
  it("decodes a UTF-8 string to its exact contents", () => {
    expect(decode(enc("5:hello"))).toBe("hello");
  });

  it("decodes an empty string", () => {
    expect(decode(enc("0:"))).toBe("");
  });

  it("decodes multibyte UTF-8 correctly by byte length", () => {
    // "héllo" is 6 UTF-8 bytes (é = 2 bytes).
    const input = enc("6:héllo");
    expect(decode(input)).toBe("héllo");
  });

  it("round-trips a string through encode -> decode", () => {
    const bytes = encode("torrent");
    expect(new TextDecoder().decode(bytes)).toBe("7:torrent");
    expect(decode(bytes)).toBe("torrent");
  });
});

describe("bencode: list type round-trips", () => {
  it("decodes a homogeneous integer list to the exact array", () => {
    expect(decode(enc("li1ei2ei3ee"))).toEqual([1, 2, 3]);
  });

  it("decodes an empty list", () => {
    expect(decode(enc("le"))).toEqual([]);
  });

  it("decodes a mixed-type list", () => {
    expect(decode(enc("l4:spami42ee"))).toEqual(["spam", 42]);
  });

  it("decodes nested lists", () => {
    expect(decode(enc("lli1eeli2eee"))).toEqual([[1], [2]]);
  });

  it("round-trips a list through encode -> decode", () => {
    const original: BencodeValue = ["a", 1, ["b"]];
    const bytes = encode(original);
    expect(decode(bytes)).toEqual(original);
  });
});

describe("bencode: dictionary type round-trips", () => {
  it("decodes a dictionary to the exact object", () => {
    expect(decode(enc("d3:bar4:spam3:fooi42ee"))).toEqual({
      bar: "spam",
      foo: 42,
    });
  });

  it("decodes an empty dictionary", () => {
    expect(decode(enc("de"))).toEqual({});
  });

  it("decodes a nested dictionary", () => {
    expect(decode(enc("d4:infod6:lengthi12eee"))).toEqual({
      info: { length: 12 },
    });
  });

  it("round-trips a dictionary through encode -> decode", () => {
    const original: BencodeValue = { name: "boba", count: 3, tags: ["x"] };
    const bytes = encode(original);
    expect(decode(bytes)).toEqual(original);
  });
});

describe("bencode: dict-key lexicographic-sort invariant", () => {
  it("encodes dictionary keys in lexicographic order regardless of insertion order", () => {
    // Insertion order deliberately NOT sorted.
    const dict: BencodeValue = { zebra: 1, apple: 2, mango: 3 };
    const out = new TextDecoder().decode(encode(dict));
    // Keys must appear sorted: apple < mango < zebra.
    expect(out).toBe("d5:applei2e5:mangoi3e5:zebrai1ee");
  });

  it("places keys with shared prefixes in correct order", () => {
    const dict: BencodeValue = { ab: 1, a: 2, abc: 3 };
    const out = new TextDecoder().decode(encode(dict));
    // Sorted order: "a" < "ab" < "abc".
    expect(out).toBe("d1:ai2e2:abi1e3:abci3ee");
  });

  it("preserves the sorted-key invariant across an encode -> decode -> encode cycle", () => {
    const dict: BencodeValue = { c: 3, a: 1, b: 2 };
    const first = encode(dict);
    const reencoded = encode(decode(first));
    expect(bytesToHex(reencoded)).toBe(bytesToHex(first));
    expect(new TextDecoder().decode(reencoded)).toBe("d1:ai1e1:bi2e1:ci3ee");
  });
});

describe("bencode: binary-safe byte strings", () => {
  it("preserves arbitrary non-UTF-8 bytes via binary encoding", () => {
    // Bytes that are NOT valid standalone UTF-8 (0xff, 0xfe, 0x00).
    const raw = new Uint8Array([0x00, 0xff, 0xfe, 0x80, 0x01]);
    const encoded = encode(raw);
    const decoded = decode(encoded, { encoding: "binary" });
    expect(decoded).toBeInstanceOf(Uint8Array);
    expect(Array.from(decoded as Uint8Array)).toEqual(Array.from(raw));
  });

  it("encodes raw bytes with a correct length prefix and colon", () => {
    const raw = new Uint8Array([0x00, 0xff, 0xfe]);
    const encoded = encode(raw);
    // Prefix "3:" then the three raw bytes.
    expect(encoded[0]).toBe(0x33); // '3'
    expect(encoded[1]).toBe(0x3a); // ':'
    expect(encoded[2]).toBe(0x00);
    expect(encoded[3]).toBe(0xff);
    expect(encoded[4]).toBe(0xfe);
    expect(encoded.length).toBe(5);
  });

  it("round-trips a 20-byte SHA-1-style binary value (info_hash shape)", () => {
    const infoHash = new Uint8Array(20);
    for (let i = 0; i < 20; i++) infoHash[i] = (i * 13 + 7) & 0xff;
    const decoded = decode(encode(infoHash), { encoding: "binary" });
    expect(Array.from(decoded as Uint8Array)).toEqual(Array.from(infoHash));
  });

  it("keeps binary values inside a dictionary intact", () => {
    const dict: BencodeValue = {
      pieces: new Uint8Array([0xde, 0xad, 0xbe, 0xef]),
    };
    const decoded = decode(encode(dict), { encoding: "binary" }) as {
      pieces: Uint8Array;
    };
    expect(Array.from(decoded.pieces)).toEqual([0xde, 0xad, 0xbe, 0xef]);
  });
});

describe("bencode: malformed-input rejection (>= 6 cases)", () => {
  it("1. rejects a truncated integer (no terminator)", () => {
    expect(() => decode(enc("i42"))).toThrow(ParseError);
  });

  it("2. rejects a truncated byte string (length prefix exceeds data)", () => {
    // Claims 10 bytes but only 4 follow.
    expect(() => decode(enc("10:abcd"))).toThrow(ParseError);
  });

  it("3. rejects trailing garbage after a complete value", () => {
    expect(() => decode(enc("i42egarbage"))).toThrow(
      /Trailing data/,
    );
  });

  it("4. rejects a non-digit inside an integer", () => {
    expect(() => decode(enc("i4x2e"))).toThrow(ParseError);
  });

  it("5. rejects an empty integer (i e)", () => {
    expect(() => decode(enc("ie"))).toThrow(ParseError);
  });

  it("6. rejects an unterminated list", () => {
    expect(() => decode(enc("li1e"))).toThrow(ParseError);
  });

  it("7. rejects an unterminated dictionary", () => {
    expect(() => decode(enc("d3:fooi1e"))).toThrow(ParseError);
  });

  it("8. rejects a leading byte that starts no valid type", () => {
    expect(() => decode(enc("x"))).toThrow(ParseError);
  });

  it("9. rejects empty input", () => {
    expect(() => decode(new Uint8Array(0))).toThrow(ParseError);
  });

  it("10. rejects a bad string-length prefix that runs off the end", () => {
    expect(() => decode(enc("5"))).toThrow(ParseError);
  });

  it("11. rejects a non-integer when encoding an integer", () => {
    expect(() => encode(3.14)).toThrow(ParseError);
  });
});

describe("bencode: hex helpers", () => {
  it("converts bytes to a lowercase zero-padded hex string", () => {
    expect(bytesToHex(new Uint8Array([0x00, 0x0f, 0xff]))).toBe("000fff");
  });

  it("round-trips bytes through hex and back", () => {
    const bytes = new Uint8Array([0xde, 0xad, 0xbe, 0xef]);
    expect(Array.from(hexToBytes(bytesToHex(bytes)))).toEqual(
      Array.from(bytes),
    );
  });

  it("rejects an odd-length hex string", () => {
    expect(() => hexToBytes("abc")).toThrow(ParseError);
  });

  it("rejects a non-hex digit", () => {
    expect(() => hexToBytes("zz")).toThrow(ParseError);
  });
});
