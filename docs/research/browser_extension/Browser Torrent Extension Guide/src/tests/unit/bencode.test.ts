/**
 * @fileoverview Unit tests for bencode encoder/decoder.
 *
 * Tests encoding and decoding of all bencode types: integers, strings,
 * lists, and dictionaries. Also tests binary data handling and edge cases.
 */

import {
  encode,
  decode,
  bytesToHex,
  hexToBytes,
  type BencodeValue,
} from "../../src/parser/bencode";

describe("Bencode", () => {
  describe("Integers", () => {
    it("encodes positive integer", () => {
      const result = encode(42);
      expect(new TextDecoder().decode(result)).toBe("i42e");
    });

    it("encodes zero", () => {
      const result = encode(0);
      expect(new TextDecoder().decode(result)).toBe("i0e");
    });

    it("encodes negative integer", () => {
      const result = encode(-42);
      expect(new TextDecoder().decode(result)).toBe("i-42e");
    });

    it("decodes positive integer", () => {
      const data = new TextEncoder().encode("i42e");
      expect(decode(data)).toBe(42);
    });

    it("decodes zero", () => {
      const data = new TextEncoder().encode("i0e");
      expect(decode(data)).toBe(0);
    });

    it("decodes negative integer", () => {
      const data = new TextEncoder().encode("i-42e");
      expect(decode(data)).toBe(-42);
    });

    it("throws for non-integer number", () => {
      expect(() => encode(3.14)).toThrow();
    });
  });

  describe("Strings", () => {
    it("encodes empty string", () => {
      const result = encode("");
      expect(new TextDecoder().decode(result)).toBe("0:");
    });

    it("encodes simple string", () => {
      const result = encode("hello");
      expect(new TextDecoder().decode(result)).toBe("5:hello");
    });

    it("encodes string with spaces", () => {
      const result = encode("hello world");
      expect(new TextDecoder().decode(result)).toBe("11:hello world");
    });

    it("decodes simple string", () => {
      const data = new TextEncoder().encode("5:hello");
      expect(decode(data)).toBe("hello");
    });

    it("decodes empty string", () => {
      const data = new TextEncoder().encode("0:");
      expect(decode(data)).toBe("");
    });
  });

  describe("Lists", () => {
    it("encodes empty list", () => {
      const result = encode([]);
      expect(new TextDecoder().decode(result)).toBe("le");
    });

    it("encodes list of integers", () => {
      const result = encode([1, 2, 3]);
      expect(new TextDecoder().decode(result)).toBe("li1ei2ei3ee");
    });

    it("encodes mixed list", () => {
      const result = encode([1, "hello"]);
      expect(new TextDecoder().decode(result)).toBe("li1e5:helloe");
    });

    it("decodes empty list", () => {
      const data = new TextEncoder().encode("le");
      expect(decode(data)).toEqual([]);
    });

    it("decodes list of integers", () => {
      const data = new TextEncoder().encode("li1ei2ei3ee");
      expect(decode(data)).toEqual([1, 2, 3]);
    });
  });

  describe("Dictionaries", () => {
    it("encodes empty dict", () => {
      const result = encode({});
      expect(new TextDecoder().decode(result)).toBe("de");
    });

    it("encodes simple dict with sorted keys", () => {
      const result = encode({ b: 2, a: 1 });
      // Keys must be sorted
      expect(new TextDecoder().decode(result)).toBe("d1:ai1e1:bi2ee");
    });

    it("decodes empty dict", () => {
      const data = new TextEncoder().encode("de");
      const result = decode(data);
      expect(result).toEqual({});
    });

    it("decodes simple dict", () => {
      const data = new TextEncoder().encode("d1:ai1e1:bi2ee");
      const result = decode(data);
      expect(result).toEqual({ a: 1, b: 2 });
    });

    it("decodes nested dict", () => {
      const data = new TextEncoder().encode("d4:infod4:name5:helloee");
      const result = decode(data) as Record<string, unknown>;
      expect(result.info).toEqual({ name: "hello" });
    });
  });

  describe("Nested structures", () => {
    it("encodes list of dicts", () => {
      const result = encode([{ a: 1 }, { b: 2 }]);
      expect(new TextDecoder().decode(result)).toBe("ld1:ai1eed1:bi2eee");
    });

    it("decodes list of dicts", () => {
      const data = new TextEncoder().encode("ld1:ai1eed1:bi2eee");
      const result = decode(data);
      expect(result).toEqual([{ a: 1 }, { b: 2 }]);
    });
  });

  describe("Binary data", () => {
    it("encodes Uint8Array as bytes", () => {
      const bytes = new Uint8Array([0x00, 0x01, 0x02, 0xff]);
      const result = encode(bytes);
      // Should be 4:<4 raw bytes>
      expect(result[0]).toCharCode ? undefined : undefined;
      const prefix = new TextDecoder().decode(result.slice(0, 2));
      expect(prefix).toBe("4:");
    });

    it("decodes to string by default", () => {
      const data = new TextEncoder().encode("5:hello");
      const result = decode(data);
      expect(typeof result).toBe("string");
    });

    it("decodes to Uint8Array in binary mode", () => {
      const data = new TextEncoder().encode("5:hello");
      const result = decode(data, { encoding: "binary" });
      expect(result instanceof Uint8Array).toBe(true);
    });
  });

  describe("Error handling", () => {
    it("throws for unterminated integer", () => {
      const data = new TextEncoder().encode("i42");
      expect(() => decode(data)).toThrow();
    });

    it("throws for empty integer", () => {
      const data = new TextEncoder().encode("ie");
      expect(() => decode(data)).toThrow();
    });

    it("throws for unterminated list", () => {
      const data = new TextEncoder().encode("li42e");
      expect(() => decode(data)).toThrow();
    });

    it("throws for unterminated dict", () => {
      const data = new TextEncoder().encode("d1:ai42e");
      expect(() => decode(data)).toThrow();
    });

    it("throws for invalid start byte", () => {
      const data = new TextEncoder().encode("x");
      expect(() => decode(data)).toThrow();
    });

    it("throws for trailing data", () => {
      const data = new TextEncoder().encode("i42eextra");
      expect(() => decode(data)).toThrow();
    });
  });

  describe("Utility functions", () => {
    it("bytesToHex converts correctly", () => {
      const bytes = new Uint8Array([0x00, 0x0f, 0xff]);
      expect(bytesToHex(bytes)).toBe("000fff");
    });

    it("hexToBytes converts correctly", () => {
      const hex = "000fff";
      const bytes = hexToBytes(hex);
      expect(bytes).toEqual(new Uint8Array([0x00, 0x0f, 0xff]));
    });

    it("hexToBytes and bytesToHex are inverse", () => {
      const original = new Uint8Array([0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0]);
      const hex = bytesToHex(original);
      const recovered = hexToBytes(hex);
      expect(recovered).toEqual(original);
    });
  });

  describe("Torrent-like structure", () => {
    it("round-trips a torrent-like dictionary", () => {
      const torrent: BencodeValue = {
        announce: "udp://tracker.example.com:80",
        "announce-list": [["udp://tracker1.example.com:80"], ["udp://tracker2.example.com:80"]],
        "creation date": 1700000000,
        info: {
          name: "test-file.txt",
          "piece length": 262144,
          pieces: new Uint8Array(20), // SHA1 hash placeholder
          length: 1024,
        },
      };

      const encoded = encode(torrent);
      const decoded = decode(encoded) as Record<string, unknown>;

      expect(decoded.announce).toBe("udp://tracker.example.com:80");
      expect(decoded["creation date"]).toBe(1700000000);

      const info = decoded.info as Record<string, unknown>;
      expect(info.name).toBe("test-file.txt");
      expect(info["piece length"]).toBe(262144);
      expect(info.length).toBe(1024);
    });
  });
});
