/**
 * @fileoverview SECURITY — no hard-coded secret / fixed encryption key (§11.4.10).
 *
 * Reads the REAL `src/options/options.ts` (and `src/shared/crypto.ts`) source
 * text from disk and asserts — via specific credential-literal regexes — that
 * NO literal passphrase / password / api-token / fixed key is assigned anywhere.
 * The reference extension hard-coded the passphrase `"bobalink-extension"`
 * (reference options.ts:327); that defect must never reappear.
 *
 * Anti-bluff (§11.4): the assertions are SPECIFIC regexes for an *assigned*
 * credential literal — not "the file exists". If someone re-introduced
 * `const passphrase = "bobalink-extension"` or called `encrypt(token, "...")`
 * with a string literal, the matching test FAILs.
 *
 * @module tests/security/no-hardcoded-secret.test
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it, expect } from "vitest";

// Vitest runs with cwd = the extension/ project root.
const OPTIONS_TS = resolve(process.cwd(), "src/options/options.ts");
const CRYPTO_TS = resolve(process.cwd(), "src/shared/crypto.ts");

const optionsSource = readFileSync(OPTIONS_TS, "utf8");
const cryptoSource = readFileSync(CRYPTO_TS, "utf8");

/**
 * Strip line + block comments and JSDoc so we only assert against EXECUTABLE
 * source. The §11.4.10 prose in the file header legitimately *mentions* the
 * forbidden pattern by name; asserting on comments would be a false positive.
 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "") // block + JSDoc comments
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1"); // line comments (not URLs like http://)
}

const optionsCode = stripComments(optionsSource);
const cryptoCode = stripComments(cryptoSource);

describe("§11.4.10 — options.ts contains no hard-coded passphrase", () => {
  it("does NOT contain the reference's fixed passphrase literal 'bobalink-extension' in code", () => {
    // The exact reference defect. FAILs if the fixed key is reintroduced.
    expect(optionsCode).not.toContain("bobalink-extension");
  });

  it("never assigns a credential-named variable to a string literal", () => {
    // Catches: const/let passphrase|password|secret|apiKey|apiToken|key = "literal"
    // (any non-empty quoted literal). A user-entered value reads from the DOM
    // (readValue / .value), never a literal — so a literal assignment FAILs.
    const credentialLiteralAssign =
      /\b(?:const|let|var)\s+\w*(?:passphrase|password|secret|api[_-]?token|api[_-]?key|encryption[_-]?key)\w*\s*(?::[^=]+)?=\s*(['"`])(?!\1)[^'"`]+\1/i;
    expect(credentialLiteralAssign.test(optionsCode)).toBe(false);
  });

  it("never passes a string LITERAL as the passphrase (2nd arg) to encrypt()", () => {
    // encrypt(<plaintext>, <passphrase>): the 2nd argument must be a variable
    // (tokenPassphrase), never a quoted literal or an empty string.
    const encryptWithLiteralPass =
      /encrypt\s*\([^,)]+,\s*(['"`])[^'"`]*\1\s*\)/;
    expect(encryptWithLiteralPass.test(optionsCode)).toBe(false);
  });

  it("the passphrase it encrypts under is read from the DOM, not a constant", () => {
    // Positive evidence the guard is real: the passphrase variable comes from a
    // form field. If this disappears, the encryption is no longer user-keyed.
    expect(optionsCode).toMatch(/readValue\(\s*doc\s*,\s*["']opt-token-passphrase["']/);
    expect(optionsCode).toMatch(/encrypt\(\s*tokenPlain\s*,\s*tokenPassphrase\s*\)/);
  });

  it("guards: a token entered with an EMPTY passphrase is refused, not auto-keyed", () => {
    // The anti-fixed-key branch: tokenPassphrase.length > 0 must gate the encrypt.
    expect(optionsCode).toMatch(/tokenPassphrase\.length\s*>\s*0/);
  });
});

describe("§11.4.10 — crypto.ts derives keys from a passphrase, with no embedded key", () => {
  it("rejects an empty passphrase in encrypt() (no silent fixed-key fallback)", () => {
    // The crypto layer must throw when passphrase is falsy — never substitute a
    // default/embedded key. FAILs if this guard is removed.
    expect(cryptoCode).toMatch(/if\s*\(\s*!passphrase\s*\)/);
    expect(cryptoCode).toMatch(/Passphrase is required for encryption/);
  });

  it("does NOT embed a raw key / passphrase / salt literal", () => {
    // Salts/IVs are generated at runtime (crypto.getRandomValues); no literal
    // base64 key material may be checked in. A long quoted base64-ish constant
    // assigned to a key/salt/passphrase-named symbol is the violation.
    const embeddedKeyLiteral =
      /\b(?:key|salt|passphrase|secret)\w*\s*(?::[^=]+)?=\s*(['"`])[A-Za-z0-9+/]{16,}={0,2}\1/i;
    expect(embeddedKeyLiteral.test(cryptoCode)).toBe(false);
  });

  it("uses crypto.getRandomValues for salt/IV (runtime randomness, not a constant)", () => {
    expect(cryptoCode).toMatch(/crypto\.getRandomValues/);
  });
});
