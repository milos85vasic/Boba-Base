/**
 * @fileoverview Anti-bluff unit tests for the REAL error taxonomy module.
 *
 * Imports the production `src/shared/errors.ts`. Asserts user-observable
 * outcomes: each subclass carries the correct code/statusCode/recoverable
 * fields, getUserMessage produces the expected human text, instanceof works
 * across the chain, and normalizeError coerces arbitrary values. Includes the
 * fixed RateLimitError / ServerError contracts (correct names + retryAfter).
 *
 * @module tests/unit/errors.test
 */

import { describe, it, expect } from "vitest";
import {
  BobaLinkError,
  AuthError,
  NetworkError,
  TorrentError,
  ParseError,
  ConfigError,
  StorageError,
  RateLimitError,
  ServerError,
  isBobaLinkError,
  normalizeError,
} from "../../src/shared/errors";

describe("BobaLinkError base", () => {
  it("defaults code to BOBA_UNKNOWN, non-recoverable, null statusCode", () => {
    const e = new BobaLinkError("boom");
    expect(e.code).toBe("BOBA_UNKNOWN");
    expect(e.statusCode).toBeNull();
    expect(e.recoverable).toBe(false);
    expect(e).toBeInstanceOf(Error);
    expect(e.getUserMessage()).toBe("boom");
  });

  it("freezes context and toJSON exposes structured fields", () => {
    const e = new BobaLinkError("x", { context: { a: 1 } });
    expect(Object.isFrozen(e.context)).toBe(true);
    const json = e.toJSON();
    expect(json.code).toBe("BOBA_UNKNOWN");
    expect(json.message).toBe("x");
  });
});

describe("error subclasses carry the right taxonomy", () => {
  it("AuthError → BOBA_AUTH_FAILED, 401, recoverable", () => {
    const e = new AuthError("nope");
    expect(e.name).toBe("AuthError");
    expect(e.code).toBe("BOBA_AUTH_FAILED");
    expect(e.statusCode).toBe(401);
    expect(e.recoverable).toBe(true);
    expect(e).toBeInstanceOf(BobaLinkError);
    expect(e.getUserMessage()).toContain("Authentication failed");
  });

  it("NetworkError → BOBA_NETWORK_ERROR, null status, recoverable", () => {
    const e = new NetworkError("offline");
    expect(e.code).toBe("BOBA_NETWORK_ERROR");
    expect(e.statusCode).toBeNull();
    expect(e.recoverable).toBe(true);
  });

  it("TorrentError → BOBA_TORRENT_ERROR, 400", () => {
    const e = new TorrentError("bad");
    expect(e.code).toBe("BOBA_TORRENT_ERROR");
    expect(e.statusCode).toBe(400);
  });

  it("ParseError → BOBA_PARSE_ERROR, NOT recoverable", () => {
    const e = new ParseError("malformed");
    expect(e.code).toBe("BOBA_PARSE_ERROR");
    expect(e.recoverable).toBe(false);
  });

  it("ConfigError → BOBA_CONFIG_ERROR, recoverable", () => {
    const e = new ConfigError("bad config");
    expect(e.code).toBe("BOBA_CONFIG_ERROR");
    expect(e.recoverable).toBe(true);
  });

  it("StorageError → BOBA_STORAGE_ERROR, recoverable", () => {
    const e = new StorageError("io");
    expect(e.code).toBe("BOBA_STORAGE_ERROR");
    expect(e.recoverable).toBe(true);
  });
});

describe("RateLimitError (fixed name + retryAfter)", () => {
  it("is named RateLimitError with code BOBA_RATE_LIMITED, status 429, retryAfter", () => {
    const e = new RateLimitError("slow down", 5000);
    expect(e.name).toBe("RateLimitError");
    expect(e.code).toBe("BOBA_RATE_LIMITED");
    expect(e.statusCode).toBe(429);
    expect(e.recoverable).toBe(true);
    expect(e.retryAfter).toBe(5000);
    expect(e.getUserMessage()).toContain("5 seconds");
  });
});

describe("ServerError (fixed name + status-driven recoverability)", () => {
  it("is named ServerError with code BOBA_SERVER_<status>", () => {
    const e = new ServerError("oops", 503);
    expect(e.name).toBe("ServerError");
    expect(e.code).toBe("BOBA_SERVER_503");
    expect(e.statusCode).toBe(503);
    expect(e.recoverable).toBe(true); // >= 500
  });

  it("is non-recoverable for a 4xx (other than 429)", () => {
    const e = new ServerError("client error", 404);
    expect(e.recoverable).toBe(false);
  });

  it("is recoverable for a 429", () => {
    const e = new ServerError("rate", 429);
    expect(e.recoverable).toBe(true);
  });
});

describe("isBobaLinkError / normalizeError", () => {
  it("isBobaLinkError discriminates correctly", () => {
    expect(isBobaLinkError(new AuthError("x"))).toBe(true);
    expect(isBobaLinkError(new Error("x"))).toBe(false);
    expect(isBobaLinkError("x")).toBe(false);
  });

  it("normalizeError passes through BobaLinkError unchanged", () => {
    const original = new TorrentError("keep me");
    expect(normalizeError(original)).toBe(original);
  });

  it("normalizeError wraps a plain Error preserving the message + cause", () => {
    const src = new Error("native failure");
    const norm = normalizeError(src, { ctx: "test" });
    expect(norm).toBeInstanceOf(BobaLinkError);
    expect(norm.message).toBe("native failure");
    expect(norm.cause).toBe(src);
    expect(norm.context.ctx).toBe("test");
  });

  it("normalizeError coerces a string and unknown value", () => {
    expect(normalizeError("string error").message).toBe("string error");
    const fromUnknown = normalizeError(42);
    expect(fromUnknown.message).toBe("An unknown error occurred");
    expect(fromUnknown.context.originalValue).toBe(42);
  });
});
