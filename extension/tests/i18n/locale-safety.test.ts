/**
 * i18n locale SAFETY + INTEGRITY guard (8 locales: en, de, es, fr, it, ja, pt,
 * ru).
 *
 * SCOPE — complements, does NOT duplicate, `tests/unit/locale-parity.test.ts`.
 * The parity test already proves KEY parity (every non-en catalog has exactly
 * en's key set) + non-empty messages + that an en placeholder token is not
 * DROPPED by a translation. This file covers the SAFETY / integrity gaps the
 * parity test leaves open, all asserted against the REAL shipped catalogs read
 * off disk with fs:
 *
 *   1. PLACEHOLDER SET EQUALITY (bi-directional). Parity only checks "en token
 *      not dropped"; it does NOT catch a locale that ADDS a stray `$...$` token
 *      en lacks, nor does it cross-check the Chrome `placeholders` object. A
 *      localized `popupStatus` that renders `$1` where en renders `$url$`, or
 *      that introduces an extra `$count$`, produces a broken interpolated
 *      string for that locale's user. We assert, per key, that the FULL set of
 *      `$...$` / positional tokens (and the declared `placeholders` keys) in
 *      each locale message EQUALS en's set — no missing AND no extra.
 *
 *   2. XSS-INERT VALUES. Extension i18n messages are rendered into popup /
 *      options UI. A translation carrying raw `<script`, `<img ... onerror=>`,
 *      `javascript:`, or any raw `<tag>` is a stored-XSS injection vector the
 *      moment a message is set via innerHTML. We assert every `message` value
 *      across all 8 locales is free of HTML tags / event-handler / `javascript:`
 *      payloads. (`description` fields are dev-only metadata, never rendered,
 *      so they are out of scope.)
 *
 *   3. STRUCTURAL INTEGRITY. Every catalog parses as JSON (a malformed catalog
 *      breaks the WHOLE locale at Chrome load time); every entry is an object
 *      with a string `message`; no message is empty / whitespace-only; no
 *      message contains a leftover `__MSG_*__` reference (an un-substituted
 *      i18n token rendered literally to the user).
 *
 *   4. CATALOG PRESENCE. All 8 declared locale catalogs exist and each parses —
 *      a missing catalog for a declared locale is a hard load failure for that
 *      locale's users.
 *
 * Catalogs are loaded from the REAL `src/public/_locales/<locale>/messages.json`
 * shipped files — not a copy — so a real defect introduced into any catalog
 * turns the relevant test RED with the exact locale + key + offending value.
 *
 * Anti-bluff: each property is written so it would FAIL against a no-op (e.g.
 * the placeholder extractor is self-validated against a synthetic message in
 * an explicit `it`, so a regex that silently matches nothing cannot make the
 * placeholder checks vacuously green; the XSS regex is likewise validated
 * against a synthetic hostile string). NO wall-clock thresholds. Production
 * catalogs are NOT mutated — defects are reported, not patched.
 */
import { readFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const EXT_ROOT = resolve(__dirname, "..", "..");
const LOCALES_DIR = join(EXT_ROOT, "src", "public", "_locales");

/** Default locale (Chrome `default_locale`) — the placeholder source-of-truth. */
const DEFAULT_LOCALE = "en";
/** Every locale catalog the extension ships (manifest `default_locale` + 7). */
const ALL_LOCALES = ["en", "de", "es", "fr", "it", "ja", "pt", "ru"] as const;
/** Non-default locales compared against en for placeholder-set equality. */
const TRANSLATION_LOCALES = ALL_LOCALES.filter((l) => l !== DEFAULT_LOCALE);

const catalogPath = (locale: string): string =>
  join(LOCALES_DIR, locale, "messages.json");

interface CatalogEntry {
  message?: unknown;
  description?: unknown;
  placeholders?: Record<string, unknown>;
}

/** Read the REAL catalog file as raw text (so JSON.parse failures surface). */
function readRaw(locale: string): string {
  return readFileSync(catalogPath(locale), "utf8");
}

function loadCatalog(locale: string): Record<string, CatalogEntry> {
  return JSON.parse(readRaw(locale)) as Record<string, CatalogEntry>;
}

/**
 * The full placeholder fingerprint of a single catalog entry:
 *   - every Chrome named token `$NAME$` (case-insensitive name) in the message
 *   - every positional token `$1` .. `$9` in the message
 *   - every key declared in the entry's `placeholders` object, normalized to
 *     `$KEY$` form so it is comparable with inline `$NAME$` tokens
 * Returned as a sorted, de-duplicated, UPPER-cased set (Chrome placeholder
 * names are case-insensitive), so two entries are token-comparable.
 */
function placeholderFingerprint(entry: CatalogEntry): string[] {
  const tokens = new Set<string>();
  const message = typeof entry.message === "string" ? entry.message : "";
  for (const m of message.matchAll(/\$[A-Za-z0-9_@]+\$/g)) {
    tokens.add(m[0].toUpperCase());
  }
  for (const m of message.matchAll(/\$[1-9]/g)) tokens.add(m[0]);
  if (entry.placeholders && typeof entry.placeholders === "object") {
    for (const key of Object.keys(entry.placeholders)) {
      tokens.add(`$${key.toUpperCase()}$`);
    }
  }
  return [...tokens].sort();
}

/**
 * Detect HTML-tag / script-injection / event-handler / javascript:-URI payload
 * in a rendered string. Conservative — intentionally flags ANY raw angle-tag,
 * since i18n messages are plain UI labels and should never contain markup.
 */
const HTML_TAG = /<\s*\/?\s*[a-zA-Z][^>]*>/; // any raw <tag> / </tag>
const SCRIPT_OPEN = /<\s*script\b/i;
const IMG_TAG = /<\s*img\b/i;
const EVENT_HANDLER = /\bon[a-z]+\s*=/i; // onerror=, onload=, onclick=, ...
const JS_URI = /javascript:/i;

function htmlViolation(value: string): string | null {
  if (SCRIPT_OPEN.test(value)) return "<script";
  if (IMG_TAG.test(value)) return "<img";
  if (EVENT_HANDLER.test(value)) return "on*= event handler";
  if (JS_URI.test(value)) return "javascript: URI";
  if (HTML_TAG.test(value)) return "raw <…> HTML tag";
  return null;
}

const LEFTOVER_MSG = /__MSG_[A-Za-z0-9_@]+__/;

describe("i18n locale safety + integrity (8 locales)", () => {
  // --- 0. Self-validation of the oracles (anti-bluff: prove the detectors
  // ---    actually fire, so the catalog checks below cannot be vacuous). ---
  it("placeholder extractor captures named + positional + placeholders-object tokens (self-test)", () => {
    const synthetic: CatalogEntry = {
      message: "Sent $count$ to $URL$ via $1",
      placeholders: { extra: { content: "$2" } },
    };
    expect(placeholderFingerprint(synthetic)).toEqual([
      "$1",
      "$COUNT$",
      "$EXTRA$",
      "$URL$",
    ]);
    // and a placeholder-free message yields the empty set (not a false token).
    expect(placeholderFingerprint({ message: "Plain label" })).toEqual([]);
  });

  it("HTML/XSS detector fires on hostile payloads and passes inert text (self-test)", () => {
    expect(htmlViolation("<script>alert(1)</script>")).not.toBeNull();
    expect(htmlViolation('<img src=x onerror="alert(1)">')).not.toBeNull();
    expect(htmlViolation('<a href="javascript:alert(1)">x</a>')).not.toBeNull();
    expect(htmlViolation("<b>bold</b>")).not.toBeNull();
    // real shipped values look like these — must be inert:
    expect(htmlViolation("Send to Boba")).toBeNull();
    expect(htmlViolation("Отправить в Boba")).toBeNull();
    expect(htmlViolation("Boba に送信")).toBeNull();
    expect(htmlViolation("Torrents sent successfully!")).toBeNull();
  });

  // --- 4. Catalog presence (a missing declared-locale catalog = load failure). ---
  it.each(ALL_LOCALES)("the %s catalog file exists on disk", (locale) => {
    expect(
      existsSync(catalogPath(locale)),
      `declared locale "${locale}" has no messages.json at ${catalogPath(locale)}`,
    ).toBe(true);
  });

  // --- 3a. Structural integrity: valid JSON for every catalog. ---
  it.each(ALL_LOCALES)("the %s catalog is valid JSON", (locale) => {
    expect(
      () => loadCatalog(locale),
      `${locale}/messages.json is not parseable JSON — this breaks the entire locale at load`,
    ).not.toThrow();
  });

  // --- 3b. Structural integrity: every entry is an object with a string,
  // ---     non-empty, non-leftover-token message. ---
  it.each(ALL_LOCALES)(
    "every %s entry has a non-empty, non-whitespace, token-free string message",
    (locale) => {
      const cat = loadCatalog(locale);
      const empty: string[] = [];
      const nonString: string[] = [];
      const leftover: string[] = [];
      for (const [key, entry] of Object.entries(cat)) {
        if (entry === null || typeof entry !== "object") {
          nonString.push(`${key} (entry not an object)`);
          continue;
        }
        if (typeof entry.message !== "string") {
          nonString.push(`${key} (message is ${typeof entry.message})`);
          continue;
        }
        if (entry.message.trim().length === 0) empty.push(key);
        if (LEFTOVER_MSG.test(entry.message)) {
          leftover.push(`${key}="${entry.message}"`);
        }
      }
      expect(
        nonString,
        `${locale} entries with a non-string message: ${nonString.join("; ")}`,
      ).toEqual([]);
      expect(
        empty,
        `${locale} entries with an empty / whitespace-only message: ${empty.join(", ")}`,
      ).toEqual([]);
      expect(
        leftover,
        `${locale} messages contain a leftover __MSG_*__ token rendered to the user: ${leftover.join("; ")}`,
      ).toEqual([]);
    },
  );

  // --- 2. XSS-inert message VALUES across all 8 locales. ---
  it.each(ALL_LOCALES)(
    "no %s message value contains HTML / script / event-handler / javascript: payload",
    (locale) => {
      const cat = loadCatalog(locale);
      const violations: string[] = [];
      for (const [key, entry] of Object.entries(cat)) {
        if (typeof entry.message !== "string") continue; // covered by integrity test
        const why = htmlViolation(entry.message);
        if (why !== null) {
          violations.push(`${key}: ${why} → "${entry.message}"`);
        }
      }
      expect(
        violations,
        `${locale} message values carry an HTML/XSS payload (injection vector when rendered): ${violations.join(" | ")}`,
      ).toEqual([]);
    },
  );

  // --- 1. Placeholder SET EQUALITY (bi-directional) per key, locale ⇄ en. ---
  it.each(TRANSLATION_LOCALES)(
    "%s placeholder set EQUALS en per key (no missing, no extra, $-token + placeholders-object)",
    (locale) => {
      const en = loadCatalog(DEFAULT_LOCALE);
      const cat = loadCatalog(locale);

      const mismatches: string[] = [];
      for (const [key, enEntry] of Object.entries(en)) {
        const localeEntry = cat[key];
        // Missing/extra KEYS are the parity test's job; only compare keys that
        // exist in BOTH so this test isolates the placeholder-integrity gap.
        if (!localeEntry || typeof localeEntry.message !== "string") continue;
        const enSet = placeholderFingerprint(enEntry);
        const locSet = placeholderFingerprint(localeEntry);
        const missing = enSet.filter((t) => !locSet.includes(t));
        const extra = locSet.filter((t) => !enSet.includes(t));
        if (missing.length > 0 || extra.length > 0) {
          mismatches.push(
            `${key}: en=[${enSet.join(",")}] ${locale}=[${locSet.join(",")}]` +
              (missing.length ? ` missing=[${missing.join(",")}]` : "") +
              (extra.length ? ` extra=[${extra.join(",")}]` : ""),
          );
        }
      }
      expect(
        mismatches,
        `${locale} placeholder sets diverge from en (broken interpolation for this locale's users): ${mismatches.join(" | ")}`,
      ).toEqual([]);
    },
  );
});
