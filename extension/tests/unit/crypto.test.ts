/**
 * @fileoverview Anti-bluff unit tests for the REAL crypto module.
 *
 * §11.4.1 / F crypto.test REWRITE: these tests import the production
 * `src/shared/crypto.ts` (NOT an inline copy) so they genuinely exercise the
 * shipped AES-256-GCM + PBKDF2 primitive and FAIL against a no-op stub.
 *
 * Every assertion is on a user-observable outcome: a roundtrip recovers the
 * exact plaintext; a wrong key throws; tampering is detected by the GCM auth
 * tag; salt + IV are fresh per operation (ciphertext is non-deterministic).
 *
 * @module tests/unit/crypto.test
 */

import { describe, it, expect } from "vitest";
import {
  encrypt,
  decrypt,
  generateSecurePassphrase,
  isEncrypted,
  sha256,
  simpleHash,
  type EncryptedBundle,
} from "../../src/shared/crypto";
import { StorageError } from "../../src/shared/errors";

const PASSPHRASE = "correct-horse-battery-staple-7187";
const PLAINTEXT = "SECRET-TOKEN-roundtrip-value";

describe("crypto.encrypt / decrypt — real module", () => {
  it("roundtrips: decrypt(encrypt(x)) === x for the correct passphrase", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    const recovered = await decrypt(bundle, PASSPHRASE);
    expect(recovered).toBe(PLAINTEXT);
  });

  it("produces a structurally valid base64 bundle (salt/iv/ciphertext/version)", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    expect(isEncrypted(bundle)).toBe(true);
    expect(bundle.version).toBe(1);
    // base64 strings decode without throwing
    expect(() => atob(bundle.salt)).not.toThrow();
    expect(() => atob(bundle.iv)).not.toThrow();
    expect(() => atob(bundle.ciphertext)).not.toThrow();
    // ciphertext does not leak the plaintext
    expect(atob(bundle.ciphertext)).not.toContain(PLAINTEXT);
  });

  it("throws StorageError when the wrong passphrase is supplied", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    await expect(decrypt(bundle, "wrong-passphrase")).rejects.toBeInstanceOf(
      StorageError,
    );
  });

  it("detects tampering: a flipped ciphertext byte fails the GCM auth tag", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    const raw = atob(bundle.ciphertext);
    const bytes = Uint8Array.from(raw, (c) => c.charCodeAt(0));
    bytes[0] = (bytes[0] ?? 0) ^ 0xff; // flip the first byte
    let tampered = "";
    for (const b of bytes) tampered += String.fromCharCode(b);
    const tamperedBundle: EncryptedBundle = {
      ...bundle,
      ciphertext: btoa(tampered),
    };
    await expect(decrypt(tamperedBundle, PASSPHRASE)).rejects.toBeInstanceOf(
      StorageError,
    );
  });

  it("uses a fresh salt + IV per operation (ciphertext is non-deterministic)", async () => {
    const a = await encrypt(PLAINTEXT, PASSPHRASE);
    const b = await encrypt(PLAINTEXT, PASSPHRASE);
    expect(a.salt).not.toBe(b.salt);
    expect(a.iv).not.toBe(b.iv);
    expect(a.ciphertext).not.toBe(b.ciphertext);
    // both still decrypt to the same plaintext
    expect(await decrypt(a, PASSPHRASE)).toBe(PLAINTEXT);
    expect(await decrypt(b, PASSPHRASE)).toBe(PLAINTEXT);
  });

  it("rejects empty plaintext and empty passphrase", async () => {
    await expect(encrypt("", PASSPHRASE)).rejects.toBeInstanceOf(StorageError);
    await expect(encrypt(PLAINTEXT, "")).rejects.toBeInstanceOf(StorageError);
  });

  it("Plan E T2: the reference shipped/empty keys cannot decrypt this design's bundle", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    // Both reference-impl keys MUST fail (proves no shipped/embedded key works).
    await expect(decrypt(bundle, "bobalink-extension")).rejects.toBeInstanceOf(
      StorageError,
    );
    await expect(decrypt(bundle, "")).rejects.toBeInstanceOf(StorageError);
    // Only the real session passphrase recovers the value.
    expect(await decrypt(bundle, PASSPHRASE)).toBe(PLAINTEXT);
  });
});

describe("crypto helpers — real module", () => {
  it("generateSecurePassphrase returns a fresh non-empty base64 string each call", () => {
    const a = generateSecurePassphrase();
    const b = generateSecurePassphrase();
    expect(a.length).toBeGreaterThan(0);
    expect(a).not.toBe(b);
    expect(() => atob(a)).not.toThrow();
  });

  it("isEncrypted is a precise structural guard", () => {
    expect(isEncrypted({ salt: "a", iv: "b", ciphertext: "c", version: 1 })).toBe(
      true,
    );
    expect(isEncrypted({ salt: "a", iv: "b", ciphertext: "c" })).toBe(false);
    expect(isEncrypted("not-a-bundle")).toBe(false);
    expect(isEncrypted(null)).toBe(false);
  });

  it("sha256 produces a stable 64-char hex digest", async () => {
    const h1 = await sha256("hello");
    const h2 = await sha256("hello");
    expect(h1).toBe(h2);
    expect(h1).toMatch(/^[0-9a-f]{64}$/);
    expect(await sha256("world")).not.toBe(h1);
  });

  it("simpleHash is deterministic and non-negative", () => {
    expect(simpleHash("abc")).toBe(simpleHash("abc"));
    expect(simpleHash("abc")).toBeGreaterThanOrEqual(0);
    expect(simpleHash("abc")).not.toBe(simpleHash("abd"));
  });
});
