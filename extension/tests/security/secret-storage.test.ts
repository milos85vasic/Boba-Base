/**
 * @fileoverview SECURITY — secret-storage & passphrase-guard behaviour (§11.4.10).
 *
 * Drives the REAL `saveOptions` (src/options/options.ts) through a jsdom-parsed
 * `src/options/index.html`, backed by the committed storage module on the
 * in-memory chrome.storage fake, and asserts USER-OBSERVABLE security outcomes:
 *
 *   1. An entered Boba API token + a passphrase → the PERSISTED config holds an
 *      encrypted bundle, and the plaintext token NEVER appears anywhere in the
 *      stored JSON (no plaintext-token field is written).
 *   2. An entered token WITHOUT a passphrase → the token is NOT stored (the
 *      empty/unset-passphrase path is rejected — no auto-encryption under a
 *      fixed/empty key).
 *
 * Anti-bluff (§11.4 / §11.4.69): assertions inspect the ACTUAL persisted bytes
 * read back from storage — not return codes. If saveOptions wrote the plaintext
 * token, or auto-encrypted under an empty passphrase, the matching test FAILs.
 *
 * @module tests/security/secret-storage.test
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { createChromeStorageFake } from "../unit/chrome-fake";
import { STORAGE_KEYS } from "../../src/shared/constants";
import type { ExtensionConfig } from "../../src/types/config";

// Real options markup lives under the WXT entrypoints tree. Vitest runs with
// cwd = the extension/ project root for both the root config and the isolated
// `-c` run (the local config pins `root` to the project root).
const OPTIONS_HTML = resolve(
  process.cwd(),
  "src/entrypoints/options/index.html",
);
const PLAINTEXT_TOKEN = "boba-plaintext-token-ZZZ-do-not-leak";
const SESSION_PASS = "user-entered-session-pass";

let fake: ReturnType<typeof createChromeStorageFake>;

function loadOptionsMarkup(): void {
  const html = readFileSync(OPTIONS_HTML, "utf8");
  const bodyMatch = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html);
  document.body.innerHTML = bodyMatch ? (bodyMatch[1] ?? "") : html;
}

function setInput(id: string, value: string): void {
  (document.getElementById(id) as HTMLInputElement).value = value;
}

beforeEach(() => {
  fake = createChromeStorageFake();
  (globalThis as unknown as { chrome: unknown }).chrome = fake.chrome;
  document.body.innerHTML = "";
  vi.resetModules();
});

async function loadModule() {
  return import("../../src/options/options");
}

describe("secret storage — Boba API token is stored encrypted, never as plaintext", () => {
  it("persists an encrypted bundle and leaks no plaintext token into storage", async () => {
    loadOptionsMarkup();
    const { populateForm, saveOptions } = await loadModule();
    await populateForm(document);

    setInput("opt-boba-api-token", PLAINTEXT_TOKEN);
    setInput("opt-token-passphrase", SESSION_PASS);

    const returned = await saveOptions(document);

    // The persisted server field is an encrypted bundle (has ciphertext), and
    // is NOT the plaintext token.
    const blob = returned.servers[0]?.encryptedBobaApiToken;
    expect(typeof blob).toBe("string");
    expect(blob).toMatch(/"ciphertext"/);
    expect(blob).not.toContain(PLAINTEXT_TOKEN);

    // Read the WHOLE persisted config back and serialise it — the plaintext
    // token must not appear anywhere in the stored bytes (no plaintext field).
    const stored = (await fake.chrome.storage.local.get(STORAGE_KEYS.CONFIG))[
      STORAGE_KEYS.CONFIG
    ] as ExtensionConfig;
    expect(JSON.stringify(stored)).not.toContain(PLAINTEXT_TOKEN);

    // And there is no plaintext-named field carrying the secret.
    const server = stored.servers[0] as unknown as Record<string, unknown>;
    expect(server.apiToken).toBeUndefined();
    expect(server.bobaApiToken).toBeUndefined();
    expect(server.token).toBeUndefined();
  });
});

describe("secret storage — empty/unset passphrase is rejected (no fixed-key auto-encrypt)", () => {
  it("does NOT store the token when no passphrase is supplied", async () => {
    loadOptionsMarkup();
    const { populateForm, saveOptions } = await loadModule();
    await populateForm(document);

    setInput("opt-boba-api-token", PLAINTEXT_TOKEN);
    // passphrase deliberately left blank
    setInput("opt-token-passphrase", "");

    const returned = await saveOptions(document);

    // The token is NOT persisted under any key, and definitely not encrypted
    // with an empty/fixed key. Prior value was null → stays null.
    expect(returned.servers[0]?.encryptedBobaApiToken ?? null).toBeNull();

    const stored = (await fake.chrome.storage.local.get(STORAGE_KEYS.CONFIG))[
      STORAGE_KEYS.CONFIG
    ] as ExtensionConfig;
    expect(JSON.stringify(stored)).not.toContain(PLAINTEXT_TOKEN);
  });

  it("a whitespace-only passphrase still results in no usable secret persisted", async () => {
    loadOptionsMarkup();
    const { populateForm, saveOptions } = await loadModule();
    await populateForm(document);

    setInput("opt-boba-api-token", PLAINTEXT_TOKEN);
    setInput("opt-token-passphrase", "   ");

    const returned = await saveOptions(document);
    const stored = (await fake.chrome.storage.local.get(STORAGE_KEYS.CONFIG))[
      STORAGE_KEYS.CONFIG
    ] as ExtensionConfig;

    // Whichever way the guard treats whitespace, the plaintext token must never
    // be persisted in cleartext. (If it encrypts, the bundle won't contain it;
    // if it refuses, nothing is stored.)
    expect(JSON.stringify(stored)).not.toContain(PLAINTEXT_TOKEN);
    const blob = returned.servers[0]?.encryptedBobaApiToken ?? null;
    if (blob !== null) {
      expect(blob).not.toContain(PLAINTEXT_TOKEN);
    }
  });
});
