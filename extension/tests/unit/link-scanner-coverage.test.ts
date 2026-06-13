/**
 * @fileoverview Additional anti-bluff coverage for the REAL LinkScanner.
 *
 * Companion to `tests/unit/link-scanner.test.ts` (which proves the happy path:
 * magnet detected with correct infohash/dn, absolute `.torrent` detected,
 * mailto/`#fragment`/`.html` ignored, identical-magnet dedup, stable ids). This
 * file targets the genuine LinkScanner-SPECIFIC gaps those leave open — the
 * anchor-SELECTION and FILTERING logic itself — driving the production
 * `src/scanner/link-scanner.ts` over a real jsdom DOM (`document.body.innerHTML`
 * + Vitest `environment: "jsdom"`). No scanner stub, no parser stub: every
 * assertion inspects the user-observable `DetectedTorrent[]` the scanner returns.
 *
 * The behaviours asserted here are READ FROM THE PRODUCTION CODE, not invented:
 *  - Scheme gate (link-scanner.ts:79/83): a normalized href is detected ONLY when
 *    it `startsWith("magnet:")` OR matches `isTorrentFileUrl` →
 *    `TORRENT_FILE_VALIDATION_REGEX = /^https?:\/\/.+\.torrent(\?.*)?$/i`
 *    (constants.ts:56). Therefore `javascript:`/`data:`/`vbscript:`/`ftp:`/
 *    `file:`/`mailto:`/`#frag` and a NON-http `.torrent` are all ignored.
 *  - Visibility gate (base.ts:150-165 `shouldIncludeElement`): with the default
 *    `includeHidden:false`, an anchor whose computed `display==="none"` OR
 *    `visibility==="hidden"` is SKIPPED via `window.getComputedStyle`. Zero-size
 *    is NOT in that check, so a 0x0 (but displayed/visible) anchor IS detected.
 *  - excludeSelector (base.ts:50): an anchor matching
 *    `script,style,noscript,template,textarea` is skipped — an `<a>` never
 *    matches it, so this does not affect anchors (asserted indirectly: a normal
 *    `<a>` is always considered).
 *  - href resolution (link-scanner.ts:196 `resolveUrl` via `new URL(href, base)`):
 *    an ABSOLUTE `.torrent` is kept verbatim; a RELATIVE `.torrent` href never
 *    reaches resolveUrl because the regex requires `^https?://` — so relative
 *    `.torrent` is NOT detected (asserted as the real, documented behaviour).
 *  - displayName derivation (link-scanner.ts:142/179): magnet `dn` > anchor text
 *    > `Magnet <12hex>...` fallback; torrent-file anchor text > filename >
 *    `"Unknown torrent file"`. A missing/empty name yields a sane string fallback,
 *    NEVER undefined / a crash.
 *
 * Each test fails against a no-op stub returning [] OR a regressed scanner that
 * mis-handles the property under test (the §11.4 anti-bluff RED proof). Real
 * defects (a forbidden scheme detected, a visible magnet missed, a crash on a
 * missing name) are kept RED — production is NOT edited to make them pass.
 *
 * @module tests/unit/link-scanner-coverage.test
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { LinkScanner } from "../../src/scanner/link-scanner";
import { TypedEventEmitter } from "../../src/shared/events";
import type { DetectedTorrent } from "../../src/types/torrent";

/** Real, valid 40-char hex infohashes (lowercase canonical form). */
const HASH_A = "abcdef0123456789abcdef0123456789abcdef01";
const HASH_B = "0123456789abcdef0123456789abcdef01234567";

/** Build a magnet URI; `dn` is %-encoded (parser decodes via decodeURIComponent). */
function magnet(hash: string, name?: string): string {
  const dn = name ? `&dn=${encodeURIComponent(name)}` : "";
  return `magnet:?xt=urn:btih:${hash}${dn}`;
}

/** Build a fresh LinkScanner bound to a real event emitter. */
function makeScanner(): LinkScanner {
  return new LinkScanner(new TypedEventEmitter());
}

/** Install body HTML and scan with a fresh LinkScanner. */
async function scanBody(html: string): Promise<readonly DetectedTorrent[]> {
  document.body.innerHTML = html;
  return makeScanner().scan();
}

describe("LinkScanner — additional coverage (anchor selection + filtering, real jsdom)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });
  afterEach(() => {
    document.body.innerHTML = "";
  });

  // --------------------------------------------------------------------------
  // 1. Scheme allowlist on real anchors.
  // --------------------------------------------------------------------------
  it("detects only magnet: and absolute http(s) .torrent anchors; rejects every dangerous/other scheme", async () => {
    // Regression guard: the scheme gate (startsWith("magnet:") || isTorrentFileUrl)
    // must let exactly the two safe schemes through. If a regression detected ANY
    // forbidden-scheme anchor as clickable (e.g. matched a substring instead of a
    // prefix, or accepted a non-http `.torrent`), the count/ids below go RED. This
    // is a SECURITY property: a `javascript:`/`data:`/`vbscript:` href surfaced as
    // a "download" is a clickable-payload defect — KEEP RED if it fires, do not weaken.
    const items = await scanBody(`
      <a href="${magnet(HASH_A)}">good magnet</a>
      <a href="https://example.org/files/good.torrent">good torrent file</a>
      <a href="javascript:alert(1)//x.torrent">js payload</a>
      <a href="data:application/x-bittorrent;base64,AAAA">data uri</a>
      <a href="vbscript:Msgbox(1)">vbscript</a>
      <a href="ftp://mirror.example.org/file.torrent">ftp torrent</a>
      <a href="file:///etc/passwd.torrent">file torrent</a>
      <a href="mailto:abuse@example.org">mail</a>
      <a href="#section-2">fragment only</a>
      <a href="https://example.org/page.html">normal page</a>
    `);

    // Exactly the two safe anchors are detected.
    expect(items.length).toBe(2);

    const magnetItem = items.find((it) => it.type === "magnet");
    const fileItem = items.find((it) => it.type === "torrent-file");
    expect(magnetItem?.magnet?.infohash).toBe(HASH_A);
    expect(fileItem?.torrentFile?.url).toBe(
      "https://example.org/files/good.torrent",
    );

    // No detection's url/uri carries any forbidden scheme — proves none slipped through.
    const surfaces = items.map(
      (it) => it.magnet?.uri ?? it.torrentFile?.url ?? "",
    );
    for (const s of surfaces) {
      expect(s.startsWith("javascript:")).toBe(false);
      expect(s.startsWith("data:")).toBe(false);
      expect(s.startsWith("vbscript:")).toBe(false);
      expect(s.startsWith("ftp:")).toBe(false);
      expect(s.startsWith("file:")).toBe(false);
    }
  });

  // --------------------------------------------------------------------------
  // 2. Visibility / hidden filtering — assert REAL code behaviour.
  //    base.ts:157-162 — includeHidden:false (default), so display:none /
  //    visibility:hidden anchors are skipped via getComputedStyle. There is NO
  //    zero-size check, so a 0x0 anchor that is still "displayed" IS detected.
  // --------------------------------------------------------------------------
  it("skips a display:none magnet anchor but detects a visible one on the same page", async () => {
    // Regression guard: if the getComputedStyle display:none filter were dropped,
    // the hidden HASH_B magnet would leak into results → RED. If the filter were
    // too aggressive and dropped the visible one, the visible HASH_A would be
    // missing → RED. Asserts the skip is SELECTIVE, not a blanket pass/fail.
    const items = await scanBody(`
      <a href="${magnet(HASH_A)}">visible magnet</a>
      <a href="${magnet(HASH_B)}" style="display:none">hidden magnet</a>
    `);

    expect(items.length).toBe(1);
    expect(items[0]?.magnet?.infohash).toBe(HASH_A);
    const hashes = items.map((it) => it.magnet?.infohash);
    expect(hashes).not.toContain(HASH_B);
  });

  it("skips a visibility:hidden .torrent anchor (the second branch of the visibility gate)", async () => {
    // Regression guard: covers the `style.visibility === "hidden"` arm distinctly
    // from display:none. A visible torrent-file anchor on the same page must still
    // be detected, proving the filter targets only the hidden one.
    const items = await scanBody(`
      <a href="https://example.org/a/visible.torrent">visible file</a>
      <a href="https://example.org/b/secret.torrent" style="visibility:hidden">hidden file</a>
    `);

    expect(items.length).toBe(1);
    expect(items[0]?.torrentFile?.url).toBe(
      "https://example.org/a/visible.torrent",
    );
    expect(items.map((it) => it.torrentFile?.url)).not.toContain(
      "https://example.org/b/secret.torrent",
    );
  });

  it("DETECTS a zero-size magnet anchor (the visibility gate has no zero-area check)", async () => {
    // Asserts what the code ACTUALLY does (no invention): shouldIncludeElement
    // only checks computed display/visibility, NOT bounding-box area. jsdom reports
    // an explicit width:0;height:0 anchor as display:inline / visibility:visible,
    // so it passes the gate and IS detected. If a regression ADDED a zero-size
    // filter, this magnet would vanish → RED, flagging a behaviour change.
    const items = await scanBody(
      `<a href="${magnet(HASH_A)}" style="width:0;height:0;display:inline">zero size</a>`,
    );

    expect(items.length).toBe(1);
    expect(items[0]?.magnet?.infohash).toBe(HASH_A);
  });

  // --------------------------------------------------------------------------
  // 3. href normalization / relative vs absolute .torrent.
  // --------------------------------------------------------------------------
  it("does NOT detect a relative .torrent href (regex requires absolute http(s)); absolute IS resolved", async () => {
    // Read from the code: isTorrentFileUrl → /^https?:\/\/.+\.torrent(\?.*)?$/i.
    // A relative href ("/dl/x.torrent", "files/y.torrent") has no scheme, so it
    // FAILS the regex and is never considered a torrent-file → not detected. The
    // absolute one IS detected and resolveUrl keeps it verbatim. This pins the
    // real, documented limitation; a regression that started matching relative
    // hrefs (or stopped resolving absolute) would flip the counts → RED.
    const items = await scanBody(`
      <a href="/downloads/relative-one.torrent">relative absolute-path</a>
      <a href="files/relative-two.torrent">relative same-dir</a>
      <a href="https://example.org/downloads/absolute.torrent">absolute</a>
    `);

    expect(items.length).toBe(1);
    const file = items[0];
    expect(file?.type).toBe("torrent-file");
    // Absolute URL is preserved exactly by resolveUrl (new URL(href, base)).
    expect(file?.torrentFile?.url).toBe(
      "https://example.org/downloads/absolute.torrent",
    );
    expect(file?.torrentFile?.filename).toBe("absolute.torrent");
    // No relative URL leaked in as a detection.
    const urls = items.map((it) => it.torrentFile?.url ?? "");
    expect(urls.some((u) => u.includes("relative-one"))).toBe(false);
    expect(urls.some((u) => u.includes("relative-two"))).toBe(false);
  });

  it("detects an absolute .torrent with a query string and percent-encoded filename", async () => {
    // Regex allows a trailing `(\?.*)?`, and extractFilename decodeURIComponent's
    // the last path segment. Proves query-bearing URLs are accepted (not rejected
    // by an over-strict `$`-anchored check) and the filename is decoded for the UI.
    const url =
      "https://example.org/get/My%20Cool%20Release.torrent?token=abc123&x=1";
    const items = await scanBody(`<a href="${url}">dl</a>`);

    expect(items.length).toBe(1);
    expect(items[0]?.torrentFile?.url).toBe(url);
    // Last path segment, percent-decoded.
    expect(items[0]?.torrentFile?.filename).toBe("My Cool Release.torrent");
  });

  // --------------------------------------------------------------------------
  // 4. displayName derivation + sane fallback (never undefined / crash).
  // --------------------------------------------------------------------------
  it("magnet displayName: dn wins; else anchor text; else a non-empty `Magnet <hex>...` fallback (no crash)", async () => {
    // Three magnets share NO dn / different name sources, exercising the full
    // fallback chain in processMagnetLink (dn ?? anchorText ?? `Magnet …`).
    // A regression that returned undefined for the empty-name case (a crash/blank
    // label for the user) makes the final assertion RED.
    const items = await scanBody(`
      <a href="${magnet(HASH_A, "DN Wins Name")}">anchor text ignored</a>
      <a href="${magnet(HASH_B)}">Anchor Text Used</a>
      <a href="${magnet("11111111111111111111111111111111111111aa")}"></a>
    `);

    expect(items.length).toBe(3);

    const dnItem = items.find((it) => it.magnet?.infohash === HASH_A);
    expect(dnItem?.displayName).toBe("DN Wins Name");

    const anchorItem = items.find((it) => it.magnet?.infohash === HASH_B);
    expect(anchorItem?.displayName).toBe("Anchor Text Used");

    const fallbackItem = items.find(
      (it) => it.magnet?.infohash === "11111111111111111111111111111111111111aa",
    );
    // No dn, empty anchor text → `Magnet <first 12 hex>...`. Must be a real,
    // non-empty string, never undefined.
    expect(typeof fallbackItem?.displayName).toBe("string");
    expect(fallbackItem?.displayName).toBe("Magnet 111111111111...");
    expect(fallbackItem?.displayName?.length ?? 0).toBeGreaterThan(0);
  });

  it("torrent-file displayName: anchor text wins; else the filename fallback (no crash on empty anchor)", async () => {
    // processTorrentLink: element.textContent.trim() || filename || "Unknown
    // torrent file". The empty-anchor case must fall back to the filename — a
    // user-visible label, never undefined. A regression yielding undefined → RED.
    const items = await scanBody(`
      <a href="https://example.org/x/named.torrent">Human Label</a>
      <a href="https://example.org/y/fallback-name.torrent"></a>
    `);

    expect(items.length).toBe(2);

    const labelled = items.find(
      (it) => it.torrentFile?.url === "https://example.org/x/named.torrent",
    );
    expect(labelled?.displayName).toBe("Human Label");

    const empty = items.find(
      (it) =>
        it.torrentFile?.url === "https://example.org/y/fallback-name.torrent",
    );
    // Empty anchor → filename used as the label.
    expect(typeof empty?.displayName).toBe("string");
    expect(empty?.displayName).toBe("fallback-name.torrent");
  });

  // --------------------------------------------------------------------------
  // 5. Dedup within one scan via the stable id (same magnet, two anchors).
  //    (link-scanner.test.ts already covers identical-href dedup via the per-pass
  //    `seen` set; THIS asserts the deeper property — two DIFFERENT hrefs that
  //    resolve to the SAME infohash collapse by STABLE id, the orchestrator's key.)
  // --------------------------------------------------------------------------
  it("the same infohash via two DIFFERENT magnet hrefs (different dn) yields one stable id", async () => {
    // Same torrent identity (HASH_A), two textually-distinct magnet URIs (differing
    // dn) so the per-pass `seen` (keyed on the normalized href) does NOT collapse
    // them — both reach createDetectedTorrent. They must share ONE stable id
    // (computeStableId is infohash-first), which is exactly what lets the
    // orchestrator dedup them to a single item. A regression folding dn into the
    // id (or salting it) makes the ids differ → RED.
    const items = await scanBody(`
      <a href="${magnet(HASH_A, "Mirror One")}">m1</a>
      <a href="${magnet(HASH_A, "Mirror Two")}">m2</a>
    `);

    // Both anchors are detected (distinct hrefs), but they share the same id.
    expect(items.length).toBe(2);
    expect(items[0]?.magnet?.infohash).toBe(HASH_A);
    expect(items[1]?.magnet?.infohash).toBe(HASH_A);
    expect(items[0]?.id).toBe(items[1]?.id);
    // The display names genuinely differ (proving the two anchors are distinct).
    expect(items[0]?.displayName).not.toBe(items[1]?.displayName);
    // One unique identity → the orchestrator's id-keyed Map collapses to one.
    expect(new Set(items.map((it) => it.id)).size).toBe(1);
  });

  // --------------------------------------------------------------------------
  // 6. Large-page bound — relative scaling ratio only, NO absolute ms threshold.
  // --------------------------------------------------------------------------
  it("detects every magnet on a large page and scales no worse than ~linearly (relative ratio, no absolute clock)", async () => {
    // Anti-bluff under volume: build N unique magnet anchors, assert ALL are
    // detected (no silent drop) and the time scales at most ~linearly vs a small
    // baseline. RELATIVE ratio ONLY — absolute wall-clock is environment-dependent
    // and flaky (§11.4.50). A super-linear (O(n^2)) selection/dedup regression
    // makes the ratio blow past the generous bound → RED.
    const makeAnchors = (count: number): string => {
      const parts: string[] = [];
      for (let i = 0; i < count; i++) {
        const hash = (
          i.toString(16).padStart(8, "0") + "abcdef0123456789abcdef0123456789"
        ).slice(0, 40);
        parts.push(`<a href="magnet:?xt=urn:btih:${hash}">rel ${i}</a>`);
      }
      return parts.join("\n");
    };

    const SMALL = 20;
    const LARGE = 400; // 20x the work.

    document.body.innerHTML = makeAnchors(SMALL);
    const t0 = performance.now();
    const smallResults = await makeScanner().scan();
    const smallMs = performance.now() - t0;

    document.body.innerHTML = makeAnchors(LARGE);
    const t1 = performance.now();
    const largeResults = await makeScanner().scan();
    const largeMs = performance.now() - t1;

    // Correctness: every unique magnet detected under volume.
    expect(smallResults.length).toBe(SMALL);
    expect(largeResults.length).toBe(LARGE);

    // Scaling: 20x the input must not cost dramatically worse than 20x the time.
    const workRatio = LARGE / SMALL; // 20
    const timeRatio = (largeMs + 1) / (smallMs + 1);
    expect(timeRatio).toBeLessThan(workRatio * 6);
  });
});
