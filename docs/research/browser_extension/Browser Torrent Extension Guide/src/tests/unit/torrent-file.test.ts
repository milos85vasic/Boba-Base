/**
 * @fileoverview Unit tests for torrent file parser.
 *
 * Tests parsing of .torrent files including infohash computation,
 * metadata extraction, and file information.
 */

import {
  parseTorrentFile,
  computeInfohash,
} from "../../src/parser/torrent-file";
import { encode } from "../../src/parser/bencode";

describe("Torrent File Parser", () => {
  /**
   * Create a minimal valid torrent file as Uint8Array.
   */
  function createMinimalTorrent(): Uint8Array {
    const torrent = {
      announce: "udp://tracker.example.com:80",
      info: {
        name: "test-file.txt",
        "piece length": 262144,
        pieces: new Uint8Array(20).fill(0xab), // 20-byte SHA1 placeholder
        length: 1024,
      },
    };
    return encode(torrent);
  }

  /**
   * Create a multi-file torrent.
   */
  function createMultiFileTorrent(): Uint8Array {
    const torrent = {
      announce: "udp://tracker.example.com:80",
      "announce-list": [
        ["udp://tracker1.example.com:80"],
        ["udp://tracker2.example.com:80"],
      ],
      "creation date": 1700000000,
      comment: "Test torrent",
      info: {
        name: "test-folder",
        "piece length": 262144,
        pieces: new Uint8Array(20).fill(0xcd),
        files: [
          { length: 512, path: ["file1.txt"] },
          { length: 1024, path: ["subdir", "file2.txt"] },
        ],
      },
    };
    return encode(torrent);
  }

  describe("computeInfohash", () => {
    it("computes consistent 40-char hex infohash", async () => {
      const data = createMinimalTorrent();
      const hash = await computeInfohash(data);

      expect(hash).toBeDefined();
      expect(hash.length).toBe(40);
      expect(hash).toMatch(/^[a-f0-9]{40}$/);
    });

    it("computes different hash for different content", async () => {
      const data1 = createMinimalTorrent();
      const data2 = createMultiFileTorrent();

      const hash1 = await computeInfohash(data1);
      const hash2 = await computeInfohash(data2);

      expect(hash1).not.toBe(hash2);
    });

    it("computes same hash for identical content", async () => {
      const data = createMinimalTorrent();

      const hash1 = await computeInfohash(data);
      const hash2 = await computeInfohash(data);

      expect(hash1).toBe(hash2);
    });

    it("throws for invalid torrent data", async () => {
      const invalidData = new TextEncoder().encode("not a torrent");
      await expect(computeInfohash(invalidData)).rejects.toThrow();
    });

    it("throws for torrent without info dict", async () => {
      const noInfo = encode({ announce: "udp://tracker.example.com:80" });
      await expect(computeInfohash(noInfo)).rejects.toThrow();
    });
  });

  describe("parseTorrentFile", () => {
    it("parses minimal single-file torrent", async () => {
      const data = createMinimalTorrent();
      const result = await parseTorrentFile(data);

      expect(result.infohash).toMatch(/^[a-f0-9]{40}$/);
      expect(result.name).toBe("test-file.txt");
      expect(result.pieceLength).toBe(262144);
      expect(result.numPieces).toBe(1);
      expect(result.totalSize).toBe(1024);
      expect(result.files.length).toBe(1);
      expect(result.files[0].fullPath).toBe("test-file.txt");
      expect(result.files[0].length).toBe(1024);
    });

    it("parses multi-file torrent", async () => {
      const data = createMultiFileTorrent();
      const result = await parseTorrentFile(data);

      expect(result.name).toBe("test-folder");
      expect(result.files.length).toBe(2);
      expect(result.totalSize).toBe(1536); // 512 + 1024
    });

    it("extracts tracker URLs", async () => {
      const data = createMinimalTorrent();
      const result = await parseTorrentFile(data);

      expect(result.trackers.length).toBeGreaterThan(0);
      expect(result.trackers[0]).toBe("udp://tracker.example.com:80");
    });

    it("extracts multiple trackers from announce-list", async () => {
      const data = createMultiFileTorrent();
      const result = await parseTorrentFile(data);

      expect(result.trackers.length).toBe(2);
    });

    it("extracts metadata", async () => {
      const data = createMultiFileTorrent();
      const result = await parseTorrentFile(data);

      expect(result.creationDate).toBe(1700000000);
      expect(result.comment).toBe("Test torrent");
    });

    it("handles private flag", async () => {
      const torrent = {
        announce: "udp://tracker.example.com:80",
        info: {
          name: "private-file.txt",
          "piece length": 262144,
          pieces: new Uint8Array(20),
          length: 100,
          private: 1,
        },
      };
      const data = encode(torrent);
      const result = await parseTorrentFile(data);

      expect(result.isPrivate).toBe(true);
    });

    it("defaults private flag to false", async () => {
      const data = createMinimalTorrent();
      const result = await parseTorrentFile(data);

      expect(result.isPrivate).toBe(false);
    });

    it("throws for non-dictionary data", async () => {
      const invalidData = new TextEncoder().encode("i42e"); // Just an integer
      await expect(parseTorrentFile(invalidData)).rejects.toThrow();
    });

    it("throws for torrent without info", async () => {
      const noInfo = encode({ announce: "tracker" });
      await expect(parseTorrentFile(noInfo)).rejects.toThrow();
    });

    it("throws for torrent without name", async () => {
      const noName = encode({
        announce: "tracker",
        info: {
          "piece length": 100,
          pieces: new Uint8Array(20),
          length: 100,
        },
      });
      await expect(parseTorrentFile(noName)).rejects.toThrow();
    });

    it("calculates correct number of pieces", async () => {
      const data = createMinimalTorrent();
      const result = await parseTorrentFile(data);

      // pieces field is 20 bytes = 1 piece
      expect(result.numPieces).toBe(1);
    });
  });

  describe("File information", () => {
    it("correctly builds file paths for multi-file torrents", async () => {
      const data = createMultiFileTorrent();
      const result = await parseTorrentFile(data);

      expect(result.files[0].path).toEqual(["file1.txt"]);
      expect(result.files[0].fullPath).toBe("file1.txt");

      expect(result.files[1].path).toEqual(["subdir", "file2.txt"]);
      expect(result.files[1].fullPath).toBe("subdir/file2.txt");
    });
  });
});
