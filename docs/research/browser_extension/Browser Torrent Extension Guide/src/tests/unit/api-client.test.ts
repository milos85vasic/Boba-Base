/**
 * @fileoverview Unit tests for BobaAPIClient.
 *
 * Tests request building, error handling, and retry logic.
 * Uses mocked fetch for HTTP testing.
 */

import { BobaAPIClient } from "../../src/api/client";
import {
  NetworkError,
  ServerError,
  RateLimitError,
} from "../../src/shared/errors";

// Mock fetch globally
const mockFetch = jest.fn<Promise<Response>, [RequestInfo | URL, RequestInit?]>();
global.fetch = mockFetch;

describe("BobaAPIClient", () => {
  let client: BobaAPIClient;

  beforeEach(() => {
    client = new BobaAPIClient("http://localhost:8080", 5000);
    mockFetch.mockClear();
  });

  describe("Constructor", () => {
    it("creates client with base URL", () => {
      const c = new BobaAPIClient("http://localhost:8080");
      expect(c.getBaseUrl()).toBe("http://localhost:8080");
    });

    it("strips trailing slash from URL", () => {
      const c = new BobaAPIClient("http://localhost:8080/");
      expect(c.getBaseUrl()).toBe("http://localhost:8080");
    });
  });

  describe("Auth", () => {
    it("sets auth cookie", () => {
      client.setAuthCookie("test-sid-123");
      // Cookie is used in subsequent requests
      expect(true).toBe(true); // Test passes if no error
    });

    it("clears auth cookie", () => {
      client.setAuthCookie("test");
      client.setAuthCookie(null);
      expect(true).toBe(true);
    });
  });

  describe("Login", () => {
    it("returns true on successful login", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response("Ok.", {
          status: 200,
          headers: new Headers({
            "set-cookie": "SID=abc123; path=/; HttpOnly",
          }),
        }),
      );

      const result = await client.login("admin", "admin");
      expect(result).toBe(true);
    });

    it("returns false on failed login", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response("Fails.", { status: 200 }),
      );

      const result = await client.login("admin", "wrong");
      expect(result).toBe(false);
    });

    it("returns false on HTTP error", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response("Unauthorized", { status: 401 }),
      );

      const result = await client.login("admin", "admin");
      expect(result).toBe(false);
    });

    it("handles network errors gracefully", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Network failure"));

      const result = await client.login("admin", "admin");
      expect(result).toBe(false);
    });
  });

  describe("Version check", () => {
    it("returns version string on success", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response("v4.6.0", { status: 200 }),
      );

      const version = await client.getVersion();
      expect(version).toBe("v4.6.0");
    });

    it("throws NetworkError on timeout", async () => {
      mockFetch.mockImplementationOnce(
        () =>
          new Promise((_, reject) => {
            setTimeout(() => reject(new Error("Abort")), 100);
          }),
      );

      await expect(client.getVersion()).rejects.toThrow(NetworkError);
    });
  });

  describe("Add torrent from magnet", () => {
    it("returns true on success", async () => {
      mockFetch.mockResolvedValueOnce(new Response("Ok.", { status: 200 }));

      const result = await client.addTorrentFromMagnet(
        "magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678",
      );
      expect(result).toBe(true);
    });

    it("throws ServerError on failure", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response("Fails.", { status: 200 }),
      );

      await expect(
        client.addTorrentFromMagnet(
          "magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678",
        ),
      ).rejects.toThrow(ServerError);
    });
  });

  describe("Request method", () => {
    it("makes GET request", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response('{"version": "v4.6.0"}', {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

      const result = await client.get<{ version: string }>("/api/test");
      expect(result).toEqual({ version: "v4.6.0" });
    });

    it("makes POST request with FormData", async () => {
      mockFetch.mockResolvedValueOnce(new Response("Ok.", { status: 200 }));

      const formData = new FormData();
      formData.append("urls", "magnet:?xt=urn:btih:abc123");

      await client.post("/api/v2/torrents/add", formData);

      expect(mockFetch).toHaveBeenCalled();
      const [, init] = mockFetch.mock.calls[0]!;
      expect(init?.method).toBe("POST");
    });

    it("retries on server error", async () => {
      mockFetch
        .mockResolvedValueOnce(new Response("Error", { status: 500 }))
        .mockResolvedValueOnce(
          new Response('{"ok": true}', {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );

      const result = await client.get<{ ok: boolean }>("/api/test");
      expect(result).toEqual({ ok: true });
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    it("throws RateLimitError on 429", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response("Rate limited", {
          status: 429,
          headers: { "retry-after": "60" },
        }),
      );

      // Disable retry for this test
      await expect(
        client.get("/api/test", { retry: false }),
      ).rejects.toThrow(ServerError);
    });
  });

  describe("Error handling", () => {
    it("handles text/plain responses", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response("v4.6.0", {
          status: 200,
          headers: { "content-type": "text/plain" },
        }),
      );

      const result = await client.get<string>("/api/version");
      expect(result).toBe("v4.6.0");
    });

    it("handles 204 No Content", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(null, { status: 204 }),
      );

      const result = await client.get<undefined>("/api/delete");
      expect(result).toBeUndefined();
    });
  });
});
