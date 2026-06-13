/**
 * @fileoverview SECURITY — tamper / fail-safe tests for the REAL AES-256-GCM
 * credential crypto (`src/shared/crypto.ts`).
 *
 * The Boba API token is encrypted at rest. The security covenant: any
 * tampering with the stored bundle (ciphertext / IV / salt), a wrong
 * passphrase, or a malformed bundle MUST fail safely — the GCM auth tag (or a
 * derived-key mismatch, or a decode error) makes `decrypt()` THROW a
 * `StorageError`; it MUST NEVER return a plaintext (garbage or otherwise) that
 * a caller could mistake for the real secret. A "silent wrong-result" success
 * would leak/garble the credential — the exact failure this suite forbids.
 *
 * These tests exercise the SHIPPED module against REAL WebCrypto (Node's global
 * `crypto.subtle` under jsdom — NO crypto mock). They DELIBERATELY do not
 * duplicate `tests/unit/crypto.test.ts` (which covers the ASCII roundtrip, a
 * single-byte ciphertext flip, a wrong passphrase, and 2-sample salt/IV
 * freshness) — they target the SECURITY/tamper gaps that suite leaves:
 *   - tamper at EVERY ciphertext byte position + truncation + the auth-tag
 *     region, asserting NO plaintext is ever produced (not just "throws");
 *   - tampered IV and tampered salt (untested elsewhere);
 *   - wrong passphrase asserted as a HARD throw, never a silent null/empty;
 *   - malformed / truncated / non-base64 bundles rejected cleanly (no hang);
 *   - byte-exact roundtrip for multibyte unicode + a long secret (proving the
 *     happy path is exact, so the failure tests above are not vacuous);
 *   - salt/IV uniqueness across MANY encryptions (a fixed-IV regression guard —
 *     a fixed IV is catastrophic for GCM).
 *
 * Anti-bluff (Constitution §11.4 / §11.4.1 / §11.4.69, §11.4.50): assertions
 * inspect user-observable outcomes (the rejection AND the absence of any
 * plaintext); each test would FAIL against a no-op / fail-open stub of decrypt.
 * No absolute wall-clock thresholds (§11.4.50) — tamper coverage iterates the
 * real primitive deterministically.
 *
 * @module tests/security/crypto-tamper.test
 */

import { describe, it, expect } from "vitest";
import { encrypt, decrypt, type EncryptedBundle } from "../../src/shared/crypto";
import { StorageError } from "../../src/shared/errors";

const PASSPHRASE = "correct-horse-battery-staple-7187";
const PLAINTEXT = "BOBA-API-TOKEN-fail-safe-secret-value";

/** Decode a base64 bundle field into raw bytes. */
function b64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Encode raw bytes back into a base64 string (mirror of the module helper). */
function bytesToB64(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}

/** Return a copy of `bytes` with the byte at `index` flipped (XOR 0xff). */
function flipByte(bytes: Uint8Array, index: number): Uint8Array {
  const copy = new Uint8Array(bytes);
  copy[index] = (copy[index] ?? 0) ^ 0xff;
  return copy;
}

/**
 * Assert that decrypting `bundle` does NOT yield the original plaintext and does
 * NOT silently succeed: it MUST reject with a StorageError, returning no value.
 * Anti-bluff core: a fail-open decrypt that returned garbage (or the real
 * plaintext under a tampered nonce) would make this FAIL — we capture the
 * resolved value if any and prove no plaintext escaped.
 */
async function expectFailSafe(
  bundle: EncryptedBundle,
  passphrase: string,
): Promise<void> {
  let resolved: string | undefined;
  let threw: unknown;
  try {
    resolved = await decrypt(bundle, passphrase);
  } catch (err) {
    threw = err;
  }
  // It MUST have thrown (no silent success path).
  expect(threw).toBeInstanceOf(StorageError);
  // And NO plaintext may have been produced — not the real one, not garbage.
  expect(resolved).toBeUndefined();
}

describe("crypto tamper — ciphertext integrity (GCM auth tag fails safe)", () => {
  it("flipping ANY single ciphertext byte fails — never returns plaintext (regression: a fix that drops GCM-tag verification would silently return garbage)", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    const ct = b64ToBytes(bundle.ciphertext);
    // GCM output = encrypted body + 16-byte (128-bit) auth tag. Flipping a byte
    // ANYWHERE in this region must trip authentication. Cover every position so
    // a partial-verification regression cannot hide in an un-probed byte.
    expect(ct.length).toBeGreaterThan(16);
    for (let i = 0; i < ct.length; i++) {
      const tamperedBundle: EncryptedBundle = {
        ...bundle,
        ciphertext: bytesToB64(flipByte(ct, i)),
      };
      await expectFailSafe(tamperedBundle, PASSPHRASE);
    }
  });

  it("truncating the ciphertext (cutting into / removing the auth tag) fails safe — no partial-plaintext leak (regression: tag-length confusion)", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    const ct = b64ToBytes(bundle.ciphertext);
    // Drop the final byte (corrupts the 16-byte tag) and drop the whole tag.
    for (const cut of [1, 8, 16]) {
      const truncated = ct.slice(0, Math.max(0, ct.length - cut));
      const tamperedBundle: EncryptedBundle = {
        ...bundle,
        ciphertext: bytesToB64(truncated),
      };
      await expectFailSafe(tamperedBundle, PASSPHRASE);
    }
  });

  it("appending an extra byte to the ciphertext fails safe (length-extension / framing tamper)", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    const ct = b64ToBytes(bundle.ciphertext);
    const extended = new Uint8Array(ct.length + 1);
    extended.set(ct);
    extended[ct.length] = 0x42;
    await expectFailSafe(
      { ...bundle, ciphertext: bytesToB64(extended) },
      PASSPHRASE,
    );
  });
});

describe("crypto tamper — nonce / salt integrity", () => {
  it("flipping ANY single IV byte fails — never returns wrong plaintext (regression: GCM nonce tamper must fail auth, not silently decode)", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    const iv = b64ToBytes(bundle.iv);
    expect(iv.length).toBe(12); // ENCRYPTION.IV_LENGTH_BYTES
    for (let i = 0; i < iv.length; i++) {
      await expectFailSafe(
        { ...bundle, iv: bytesToB64(flipByte(iv, i)) },
        PASSPHRASE,
      );
    }
  });

  it("flipping ANY single salt byte fails — a wrong-salt-derived key must NOT decrypt (regression: salt ignored / hardcoded)", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    const salt = b64ToBytes(bundle.salt);
    expect(salt.length).toBe(16); // ENCRYPTION.SALT_LENGTH_BYTES
    for (let i = 0; i < salt.length; i++) {
      await expectFailSafe(
        { ...bundle, salt: bytesToB64(flipByte(salt, i)) },
        PASSPHRASE,
      );
    }
  });

  it("an IV of the wrong length is rejected (no crash/hang, fails safe)", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    const iv = b64ToBytes(bundle.iv);
    // Too short and too long — neither may yield plaintext.
    await expectFailSafe(
      { ...bundle, iv: bytesToB64(iv.slice(0, 8)) },
      PASSPHRASE,
    );
    const longer = new Uint8Array(iv.length + 4);
    longer.set(iv);
    await expectFailSafe({ ...bundle, iv: bytesToB64(longer) }, PASSPHRASE);
  });
});

describe("crypto tamper — wrong passphrase is a HARD failure (no silent null/empty)", () => {
  it("a wrong passphrase throws StorageError and yields NO value (regression: a fail-open path returning '' or undefined would be mistaken for a secret)", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    // Several distinct wrong passphrases, incl. ones close to the real one.
    for (const wrong of [
      "wrong-passphrase",
      PASSPHRASE + "x",
      PASSPHRASE.slice(0, -1),
      PASSPHRASE.toUpperCase(),
      "🔑-unrelated-🔓",
    ]) {
      await expectFailSafe(bundle, wrong);
    }
    // Control: the CORRECT passphrase still recovers the exact secret — proving
    // the failures above are real auth failures, not a universally-broken decrypt.
    expect(await decrypt(bundle, PASSPHRASE)).toBe(PLAINTEXT);
  });

  it("an empty passphrase is rejected before any crypto runs (guard, not silent success)", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    await expectFailSafe(bundle, "");
  });
});

describe("crypto tamper — malformed / truncated bundles reject cleanly (no crash/hang)", () => {
  it("a non-base64 ciphertext is rejected as a StorageError, not an unhandled crash", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    // '@@@@' and a unicode char are not valid base64 alphabet → atob throws,
    // which decrypt must wrap as StorageError (caller sees a clean failure).
    await expectFailSafe({ ...bundle, ciphertext: "@@@not-base64@@@" }, PASSPHRASE);
    await expectFailSafe({ ...bundle, ciphertext: "ünïcödé" }, PASSPHRASE);
  });

  it("empty string fields (salt / iv / ciphertext) are rejected, never a silent empty success", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    await expectFailSafe({ ...bundle, ciphertext: "" }, PASSPHRASE);
    await expectFailSafe({ ...bundle, iv: "" }, PASSPHRASE);
    await expectFailSafe({ ...bundle, salt: "" }, PASSPHRASE);
  });

  it("a structurally-incomplete bundle (missing fields) is rejected, no hang", async () => {
    const bundle = await encrypt(PLAINTEXT, PASSPHRASE);
    // Drop ciphertext entirely — decrypt must fail safe rather than decode `undefined`.
    const noCipher = {
      salt: bundle.salt,
      iv: bundle.iv,
      version: bundle.version,
    } as unknown as EncryptedBundle;
    await expectFailSafe(noCipher, PASSPHRASE);

    // Garbage object with no real fields.
    const garbage = {
      salt: "x",
      iv: "y",
      ciphertext: "z",
      version: 1,
    } as EncryptedBundle;
    await expectFailSafe(garbage, PASSPHRASE);
  });
});

describe("crypto roundtrip — byte-exact for ASCII / unicode / long secrets (proves failure tests are not vacuous)", () => {
  const cases: ReadonlyArray<readonly [string, string]> = [
    ["ascii token", "boba_api_token_AbC123-_=.~"],
    ["multibyte unicode", "пароль-🔐-密码-naïve-Ω≈ç√∫˜µ"],
    ["embedded control/whitespace", "line1\nline2\ttab \x01\x1f end"],
    ["long secret (8 KiB)", "S".repeat(8192)],
    ["single char", "x"],
  ];

  for (const [label, secret] of cases) {
    it(`decrypt(encrypt(${label})) === the EXACT original (no garbling)`, async () => {
      const bundle = await encrypt(secret, PASSPHRASE);
      const recovered = await decrypt(bundle, PASSPHRASE);
      expect(recovered).toBe(secret);
      // The ciphertext must not contain the plaintext (real encryption, not echo).
      expect(atob(bundle.ciphertext)).not.toContain(secret);
    });
  }
});

describe("crypto — salt/IV uniqueness across many encryptions (fixed-IV regression guard)", () => {
  it("encrypting the SAME plaintext N times yields all-distinct salt, IV, and ciphertext (a fixed IV would be catastrophic for GCM)", async () => {
    const N = 12;
    const salts = new Set<string>();
    const ivs = new Set<string>();
    const cts = new Set<string>();
    for (let i = 0; i < N; i++) {
      const b = await encrypt(PLAINTEXT, PASSPHRASE);
      salts.add(b.salt);
      ivs.add(b.iv);
      cts.add(b.ciphertext);
      // Each still decrypts to the exact secret.
      expect(await decrypt(b, PASSPHRASE)).toBe(PLAINTEXT);
    }
    // All N must be unique — any collision signals a fixed/derived-from-fixed
    // salt or IV (a fixed-IV GCM regression leaks keystream across messages).
    expect(salts.size).toBe(N);
    expect(ivs.size).toBe(N);
    expect(cts.size).toBe(N);
  });
});
