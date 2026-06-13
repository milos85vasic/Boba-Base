/**
 * @fileoverview Additional anti-bluff coverage for the REAL TextScanner.
 *
 * Companion to `tests/unit/text-scanner.test.ts`. That file proves the happy
 * path (bare magnet detected, two distinct magnets, anchor-not-detected, stable
 * id across two scans, prose-with-no-magnet). This file targets the genuine
 * TextScanner-specific GAPS it leaves open, driving the production
 * `src/scanner/text-scanner.ts` over a real jsdom DOM (Vitest `environment:
 * "jsdom"` → live `document` + `TreeWalker`). No scanner stub, no parser stub —
 * every assertion inspects the user-observable detection records the scanner
 * returns.
 *
 * What each test PROVES (each fails against a no-op stub returning [], or a
 * regressed scanner that mis-handles the property under test):
 *  1. WITHIN-BLOB DEDUP — the same infohash repeated inside ONE text node
 *     collapses to a single detection (the per-pass `seen` set + the parser's
 *     own dedup). A regression that emitted one item per textual occurrence
 *     would make this RED.
 *  2. WITHIN-BLOB MULTI — distinct infohashes inside ONE text node are ALL
 *     detected (not just the first match).
 *  3. CROSS-SCANNER ID EQUALITY — the SAME infohash detected by the TextScanner
 *     (bare text) and by the REAL LinkScanner (`<a href>`), even with DIFFERENT
 *     display names, yields the SAME stable id. This is the exact property the
 *     orchestrator's id-keyed dedup depends on; a regression in the infohash-
 *     first id derivation would make this RED.
 *  4. FALSE-POSITIVE BOUNDARY — prose containing the word "magnet", a bare
 *     `magnet:?...` whose hash is too short / non-hex / truncated-39-char, are
 *     NOT detected. Proves the scheme+40-hex validity gate (not just a substring
 *     search).
 *  5. NON-CONTENT NODES — magnets inside `<script>`, `<style>` and `<code>` are
 *     SKIPPED (the production `acceptNode` filter excludes
 *     `script, style, noscript, template, textarea, code`), while an adjacent
 *     visible `<p>` magnet on the SAME page IS detected — proving the skip is
 *     selective, not a blanket failure.
 *  6. BOUNDED LARGE BLOB — a blob with many bare magnets detects all of them and
 *     scales no worse than ~linearly relative to a small baseline (RELATIVE
 *     ratio only — NO absolute wall-clock threshold, per §11.4.50).
 *
 * @module tests/unit/text-scanner-coverage.test
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { TextScanner } from "../../src/scanner/text-scanner";
import { LinkScanner } from "../../src/scanner/link-scanner";
import { TypedEventEmitter } from "../../src/shared/events";
import type { DetectedTorrent } from "../../src/types/torrent";

/** Real, valid 40-char hex infohashes (lowercase canonical form). */
const HASH_A = "abcdef0123456789abcdef0123456789abcdef01";
const HASH_B = "0123456789abcdef0123456789abcdef01234567";
const HASH_C = "fedcba9876543210fedcba9876543210fedcba98";

/** Build a bare magnet URI string (the kind pasted into forum text). */
function magnet(hash: string, name?: string): string {
  const dn = name ? `&dn=${encodeURIComponent(name)}` : "";
  return `magnet:?xt=urn:btih:${hash}${dn}`;
}

/**
 * Install an `innerHTML` body and return a fresh TextScanner bound to a real
 * event emitter. Text nodes must be ≥ 20 chars to pass the scanner's
 * min-length filter, so every fixture wraps magnets in real sentence text.
 */
function textScannerFor(bodyHtml: string): TextScanner {
  document.body.innerHTML = bodyHtml;
  return new TextScanner(new TypedEventEmitter());
}

describe("TextScanner — additional coverage (real DOM, jsdom)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("dedupes the SAME infohash repeated inside one text blob to a single detection", async () => {
    // Regression guard: the per-pass `seen` set + findMagnetUris' own dedup must
    // collapse the duplicate. If a regression emitted one item per textual
    // occurrence, results.length would be 3 (or 2) instead of 1 → RED.
    const m = magnet(HASH_A);
    const scanner = textScannerFor(
      `<p>Mirror one is here ${m} and another mirror copy ${m} and a third paste ${m} — all the same release.</p>`,
    );

    const results = await scanner.scan();

    expect(results.length).toBe(1);
    expect((results[0] as DetectedTorrent).magnet?.infohash).toBe(HASH_A);
  });

  it("detects MULTIPLE distinct infohashes that share one text node", async () => {
    // Regression guard: the scanner iterates ALL magnetUris in a node, not just
    // the first match. A break-after-first regression would drop HASH_B → RED.
    const scanner = textScannerFor(
      `<p>Season pack split into two: part one ${magnet(HASH_A)} and part two ${magnet(HASH_B)} grab both now please.</p>`,
    );

    const results = await scanner.scan();

    const hashes = results.map((r) => r.magnet?.infohash).sort();
    expect(hashes).toEqual([HASH_A, HASH_B].sort());
    expect(results.length).toBe(2);
  });

  it("derives the SAME stable id as the LinkScanner for the same infohash (different display names)", async () => {
    // The orchestrator dedups detections by `id`. The same torrent pasted as
    // bare text AND linked via <a href> MUST collapse to one. Both scanners
    // derive the id infohash-first (BaseScanner.computeStableId), so even with
    // DIFFERENT display names the id must match. A regression that folded the
    // display name into the id (or salted it) would break cross-scanner dedup
    // → this assertion goes RED.
    const events = new TypedEventEmitter();

    // TextScanner: bare magnet in text, display name "Text Paste Name".
    document.body.innerHTML = `<p>Forum user pasted this magnet directly: ${magnet(
      HASH_C,
      "Text Paste Name",
    )} enjoy the release everyone.</p>`;
    const textResults = await new TextScanner(events).scan();

    // LinkScanner: SAME infohash in an <a href>, DIFFERENT display name (the
    // anchor's visible text), no dn.
    document.body.innerHTML = `<p>Official link over here: <a href="${magnet(
      HASH_C,
    )}">Anchor Link Name</a> for the same content.</p>`;
    const linkResults = await new LinkScanner(events).scan();

    expect(textResults.length).toBe(1);
    expect(linkResults.length).toBe(1);
    const textItem = textResults[0] as DetectedTorrent;
    const linkItem = linkResults[0] as DetectedTorrent;

    // Same infohash …
    expect(textItem.magnet?.infohash).toBe(HASH_C);
    expect(linkItem.magnet?.infohash).toBe(HASH_C);
    // … DIFFERENT display names …
    expect(textItem.displayName).toContain("Text Paste Name");
    expect(linkItem.displayName).toContain("Anchor Link Name");
    // … yet IDENTICAL stable id, so the orchestrator dedups them to one item.
    expect(textItem.id).toBe(linkItem.id);
  });

  it("does NOT falsely detect non-magnet prose, a too-short/non-hex hash, or a truncated 39-char hash", async () => {
    // Boundary: detection requires the literal `magnet:?xt=urn:btih:` scheme
    // followed by EXACTLY 40 hex chars (MAGNET_REGEX + MAGNET_VALIDATION_REGEX).
    // None of the following satisfy that. All fixtures are ≥ 20 chars so they
    // pass the node-length filter and genuinely exercise the parser's validity
    // gate, not the length shortcut.
    const truncated39 = HASH_A.slice(0, 39); // 39 hex chars — one short of 40.
    const nonHex = "zzzz567890abcdef0123456789abcdef0123zzzz"; // 40 chars, not hex.
    const scanner = textScannerFor(
      `<p>I love downloading via a magnet link, magnets are great for sharing files quickly.</p>
       <p>Here is a broken paste magnet:?xt=urn:btih:abc123 which is far too short to be real.</p>
       <p>Another invalid one magnet:?xt=urn:btih:${nonHex} has the right length but is not hex.</p>
       <p>And a truncated magnet:?xt=urn:btih:${truncated39} missing exactly one final hex digit.</p>`,
    );

    const results = await scanner.scan();

    expect(results.length).toBe(0);
  });

  it("skips magnets inside <script>/<style>/<code> but detects an adjacent visible <p> magnet", async () => {
    // Production `acceptNode` skips text whose parent is (or is inside)
    // `script, style, noscript, template, textarea, code`. Assert the REAL
    // behaviour: the three non-content magnets are NOT detected, and a visible
    // <p> magnet on the SAME page IS — proving the skip is selective, not a
    // blanket "found nothing" pass that would mask a broken walker.
    const scanner = textScannerFor(
      `<script>var hidden = "${magnet(HASH_A)} should be ignored by the scanner";</script>
       <style>.x { content: "${magnet(HASH_B)} also ignored as non-content text"; }</style>
       <code>Example snippet showing a ${magnet(HASH_C)} pasted inside a code block.</code>
       <p>But this visible paragraph really does share ${magnet(
         "11111111111111111111111111111111111111aa",
       )} for everyone.</p>`,
    );

    const results = await scanner.scan();

    expect(results.length).toBe(1);
    const item = results[0] as DetectedTorrent;
    expect(item.magnet?.infohash).toBe("11111111111111111111111111111111111111aa");
    // The non-content infohashes must be absent.
    const detectedHashes = results.map((r) => r.magnet?.infohash);
    expect(detectedHashes).not.toContain(HASH_A);
    expect(detectedHashes).not.toContain(HASH_B);
    expect(detectedHashes).not.toContain(HASH_C);
  });

  it("detects every bare magnet in a large blob and scales no worse than ~linearly (relative ratio, no absolute threshold)", async () => {
    // Build N unique valid infohashes and paste them all as bare text. Assert
    // (a) ALL are detected (correctness under volume) and (b) the time scales
    // at most ~linearly relative to a small baseline. RELATIVE ratio ONLY — no
    // absolute ms threshold (§11.4.50: absolute wall-clock is environment-
    // dependent and flaky; a scaling ratio is deterministic in shape).
    const makeBlob = (count: number): string => {
      const parts: string[] = [];
      for (let i = 0; i < count; i++) {
        // 40-char hex hash unique per i: zero-padded index over an `a…` base.
        const hash = (i.toString(16).padStart(8, "0") + "abcdef0123456789abcdef0123456789").slice(0, 40);
        parts.push(`Release number ${i} is available right here: magnet:?xt=urn:btih:${hash} grab it now.`);
      }
      return `<p>${parts.join(" ")}</p>`;
    };

    const SMALL = 20;
    const LARGE = 400; // 20x the work.

    // Baseline (small).
    const smallScanner = textScannerFor(makeBlob(SMALL));
    const t0 = performance.now();
    const smallResults = await smallScanner.scan();
    const smallMs = performance.now() - t0;

    // Large.
    const largeScanner = textScannerFor(makeBlob(LARGE));
    const t1 = performance.now();
    const largeResults = await largeScanner.scan();
    const largeMs = performance.now() - t1;

    // Correctness: every unique magnet detected (no silent drop under volume).
    expect(smallResults.length).toBe(SMALL);
    expect(largeResults.length).toBe(LARGE);

    // Scaling: 20x the input must not cost dramatically worse than 20x the time.
    // Guard against accidental super-linear (e.g. O(n^2)) regressions WITHOUT an
    // absolute clock threshold. Allow generous slack for fixed overhead + jitter.
    const workRatio = LARGE / SMALL; // 20
    // Use a small additive floor so a tiny, noisy baseline can't inflate the ratio.
    const timeRatio = (largeMs + 1) / (smallMs + 1);
    expect(timeRatio).toBeLessThan(workRatio * 6);
  });
});
