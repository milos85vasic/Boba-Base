#!/usr/bin/env python3
"""BOB-164 — rendered-DOM WCAG colour-contrast measurement for the shipped dashboard.

WHY THIS SHAPE (§11.4.170 / §11.4.245): contrast can only be measured on a
RENDERED document — the served root ships an empty ``<app-root></app-root>``
and every colour is a CSS custom property ``ThemeService`` writes onto
``document.documentElement`` at runtime, so a static grep of the source
audits a page nobody sees.  The oracle is therefore real axe-core
(vendored at ``frontend/node_modules/axe-core``, reused per §11.4.28 rather
than reimplemented) executing inside a real headless Chromium against the
real compiled Angular bundle.

ORACLE INDEPENDENCE — STATED HONESTLY (§11.4.245, §11.4.6).  axe-core
reports its own ``contrastRatio`` computed from the browser's resolved
styles.  This script ALSO recomputes the ratio in Python straight from the
WCAG 2.x relative-luminance formula and asserts the two agree to 2 decimal
places, so an arithmetic error on either side voids the run.

That is ARITHMETIC independence, NOT measurement independence, and round 1
overstated it as "two independent oracles".  Both numbers are derived from
the SAME measurement: ``fgColor`` / ``bgColor`` / ``shadowColor`` as read
by axe from ``getComputedStyle``.  If axe resolves the wrong backdrop —
the exact §11.4.201(9) field-identity trap documented at ``effective_bg``
below — the Python side reproduces the error faithfully and the two agree
on a wrong answer.

The genuinely independent oracle for DECLARED pairs is
``frontend/src/app/models/palette.contrast.spec.ts`` plus
``style-contrast.spec.ts``: they resolve colours from the palette source
and the stylesheets, never from a browser, so a browser-side measurement
error cannot propagate into them.  The two layers answer different
questions and neither substitutes for the other.

USAGE
    .venv/bin/python docs/qa/BOB-164/axe_contrast_scan.py \
        --dist download-proxy/src/ui/dist/frontend/browser \
        --out  docs/qa/BOB-164/scan_<label>.json

    # or against a live service instead of a static dist:
    .venv/bin/python docs/qa/BOB-164/axe_contrast_scan.py --url http://localhost:7187/

Exit status: 0 when ZERO colour-contrast violations across every scanned
theme, 1 otherwise.  That makes the script itself the RED/GREEN guard.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import socket
import socketserver
import sys
import threading
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
AXE_SOURCE = REPO_ROOT / "frontend" / "node_modules" / "axe-core" / "axe.min.js"
THEME_STORAGE_KEY = "qbit.theme"  # frontend/src/app/services/theme.service.ts:27


# ---------------------------------------------------------------- WCAG math
def _srgb_channel(c8: int) -> float:
    c = c8 / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_or_rgb: str) -> float:
    """WCAG 2.x relative luminance of an opaque sRGB colour."""
    r, g, b = parse_color(hex_or_rgb)
    return 0.2126 * _srgb_channel(r) + 0.7152 * _srgb_channel(g) + 0.0722 * _srgb_channel(b)


def parse_color(value: str) -> tuple[int, int, int]:
    v = value.strip().lower()
    if v.startswith("#"):
        v = v[1:]
        if len(v) == 3:
            v = "".join(ch * 2 for ch in v)
        if len(v) not in (6, 8):
            raise ValueError(f"unparseable hex colour: {value!r}")
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    if v.startswith("rgb"):
        inner = v[v.index("(") + 1 : v.rindex(")")]
        parts = [p.strip() for p in inner.replace("/", ",").split(",") if p.strip()]
        return int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
    raise ValueError(f"unparseable colour: {value!r}")


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.x contrast ratio (L1+0.05)/(L2+0.05), L1 the lighter."""
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def required_floor(font_size_pt: float, font_weight: float) -> float:
    """WCAG 1.4.3 floor. Large text = >=18pt, or >=14pt when bold (>=700).

    axe reports fontSize already in points.  Returns 3.0 for large text,
    4.5 otherwise.  (Non-text UI components are 1.4.11 / 3.0 but axe's
    color-contrast rule only reports TEXT nodes, so they never appear here.)
    """
    if font_size_pt >= 18.0:
        return 3.0
    if font_size_pt >= 14.0 and font_weight >= 700:
        return 3.0
    return 4.5


# ------------------------------------------------------------ static server
class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_a: Any) -> None:  # silence access log
        return


def _serve(directory: Path) -> tuple[str, socketserver.TCPServer, threading.Thread]:
    handler = functools.partial(_QuietHandler, directory=str(directory))

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}/", httpd, thread


# ------------------------------------------------------------------- browser
def _chromium_executable() -> str | None:
    """Explicit browser path when the cached revision playwright wants is absent.

    Honest §11.4.6 note: this is an ENVIRONMENT accommodation, not a
    measurement choice — contrast is computed by axe from getComputedStyle,
    which is stable across Chromium builds.
    """
    override = os.environ.get("BOB164_CHROMIUM")
    if override:
        return override
    base = Path.home() / ".cache" / "ms-playwright"
    if not base.is_dir():
        return None
    candidates = sorted(base.glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    candidates += sorted(base.glob("chromium-*/chrome-linux64/chrome"))
    return str(candidates[-1]) if candidates else None


def scan(url: str, themes: list[tuple[str, str]], wait_for_app: bool = True) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    if not AXE_SOURCE.is_file():
        raise SystemExit(
            f"axe-core runtime absent at {AXE_SOURCE} — run "
            "`cd frontend && npm install --save-dev axe-core` "
            "(§11.4.3 honest SKIP: the oracle is unavailable, the page is NOT proven clean)"
        )
    axe_src = AXE_SOURCE.read_text(encoding="utf-8")
    exe = _chromium_executable()
    results: dict[str, Any] = {"url": url, "axe_version": None, "themes": {}}

    with sync_playwright() as p:
        launch: dict[str, Any] = {"headless": True}
        if exe:
            launch["executable_path"] = exe
        browser = p.chromium.launch(**launch)
        try:
            for palette_id, mode in themes:
                label = f"{palette_id}/{mode}"
                page = browser.new_page(viewport={"width": 1440, "height": 1200})
                try:
                    page.goto(url, timeout=30_000)
                    if wait_for_app:
                        page.evaluate(
                            "([k, v]) => localStorage.setItem(k, v)",
                            [THEME_STORAGE_KEY,
                             json.dumps({"paletteId": palette_id, "mode": mode, "explicitMode": True})],
                        )
                        page.reload(timeout=30_000)
                        page.wait_for_selector("app-root *", timeout=20_000)
                        page.wait_for_function(
                            "(m) => document.documentElement.getAttribute('data-mode') === m",
                            arg=mode, timeout=10_000,
                        )
                    page.wait_for_timeout(400)
                    page.add_script_tag(content=axe_src)
                    res = page.evaluate(
                        "() => axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa']}})"
                    )
                    results["axe_version"] = res.get("testEngine", {}).get("version")
                    results["themes"][label] = _summarise(res)
                finally:
                    page.close()
        finally:
            browser.close()
    return results


def _pt(raw: Any) -> float:
    """axe reports fontSize as e.g. ``'12.0 (16px)'`` — take the pt figure."""
    if raw is None:
        return 0.0
    txt = str(raw).strip()
    num = ""
    for ch in txt:
        if ch.isdigit() or ch == ".":
            num += ch
        else:
            break
    try:
        return float(num)
    except ValueError:
        return 0.0


def _weight(raw: Any) -> float:
    """axe reports fontWeight as ``'normal'`` / ``'bold'`` / a numeric string."""
    if raw is None:
        return 400.0
    txt = str(raw).strip().lower()
    if txt == "bold":
        return 700.0
    if txt in ("normal", ""):
        return 400.0
    try:
        return float(txt)
    except ValueError:
        return 400.0


def _contrast_entry(n: dict[str, Any], bucket: str) -> dict[str, Any]:
    """Normalise one axe node (from `violations` OR `incomplete`)."""
    data: dict[str, Any] = {}
    for check in list(n.get("any", [])) + list(n.get("all", [])) + list(n.get("none", [])):
        if check.get("id") == "color-contrast":
            data = check.get("data") or {}
            break
    fg, bg = data.get("fgColor"), data.get("bgColor")
    shadow = data.get("shadowColor")
    size = _pt(data.get("fontSize"))
    weight = _weight(data.get("fontWeight"))
    effective_bg = shadow or bg
    entry: dict[str, Any] = {
        "bucket": bucket,
        "selector": " ".join(n.get("target", [])),
        "html": (n.get("html") or "")[:180],
        "fg": fg,
        "bg": bg,
        "shadow": shadow,
        "effective_bg": effective_bg,
        "font_size_pt": size,
        "font_weight": weight,
        "axe_ratio": data.get("contrastRatio"),
        "axe_expected": data.get("expectedContrastRatio"),
        "message_key": data.get("messageKey"),
    }
    if fg and effective_bg:
        mine = round(contrast_ratio(fg, effective_bg), 2)
        entry["python_ratio"] = mine
        entry["python_ratio_ignoring_shadow"] = round(contrast_ratio(fg, bg), 2) if bg else None
        entry["required_floor"] = required_floor(size, weight)
        axe_r = data.get("contrastRatio")
        entry["oracles_agree"] = axe_r is not None and abs(float(axe_r) - mine) <= 0.02
        exp = data.get("expectedContrastRatio")
        if exp:
            entry["floors_agree"] = abs(float(str(exp).split(":")[0]) - required_floor(size, weight)) < 1e-9
    return entry


# axe emits these under `incomplete` when the text is composed of non-BMP
# code points (icon glyphs, emoji).  They are NOT text under SC 1.4.3 —
# they are non-text content, whose floor is SC 1.4.11's 3:1.  Treated as a
# NAMED class rather than filtered away silently (§11.4.201(6)).
GLYPH_ONLY_KEYS = {"nonBmp"}
NON_TEXT_FLOOR = 3.0

# THE UNMEASURED-GLYPH FENCE (§11.4.3 honest SKIP + §11.4.224(E) exclusion
# list).  For these nodes axe reports messageKey `nonBmp` AND resolves
# NEITHER fgColor NOR bgColor, so no oracle here can compute a ratio.
#
# Reporting them as failures would be a §11.4.201(1) false-positive
# refusal: nothing measured says they are broken.  Silently dropping them
# would re-create the very false-null this round exists to close.  So they
# are a NAMED class: printed on every run, recorded in the JSON, excluded
# from the exit code — and fenced, so a node that is NOT one of these
# known icon controls still BLOCKS rather than joining the quiet pile.
#
# Each entry is an icon-glyph control carrying its own `aria-label`, i.e.
# decorative iconography rather than prose.  They remain unverified under
# SC 1.4.11 (3:1 for non-text UI components), which this oracle cannot
# decide — tracked as BOB-184, not claimed clean.
UNMEASURED_GLYPH_SELECTORS = {
    ".bridge-retry",   # <button aria-label="Retry WebUI Bridge probe">, icon glyph
    ".theme-toggle",   # <button aria-label="Switch to ..."> sun/moon glyph
    ".caret",          # <span class="caret">-> disclosure triangle, decorative
}


def _adjudicate_incomplete(entry: dict[str, Any]) -> str:
    """Decide what an axe `incomplete` result MEANS. Never 'absence'.

    axe reports `incomplete` when its own heuristics decline to decide.
    Round 1 read only `violations`, so this whole channel was invisible:
    a white-on-white control needle at 1.0:1 — the most flagrant failure
    possible — came back as `incomplete` (messageKey `equalRatio`) and was
    counted as a PASS by both the summary and the exit code.  That is the
    §11.4.201(6) false-null living inside the contrast oracle itself.

    axe declining to decide does not mean the page is fine; it means the
    ORACLE abstained.  Where fg and bg are known this script can still
    decide — so it does, from the same WCAG formula it already uses.
    """
    ratio = entry.get("python_ratio")
    if ratio is None:
        if entry.get("message_key") in GLYPH_ONLY_KEYS and any(
            sel in entry.get("selector", "") for sel in UNMEASURED_GLYPH_SELECTORS
        ):
            # Known icon-glyph control, no colours resolved by either
            # oracle: honestly UNMEASURED, not silently passed.
            return "GLYPH_UNMEASURED"
        # No colours resolved and not a fenced glyph: genuinely
        # undecidable, and an undecided node is NOT a passing node.
        return "UNDECIDABLE"
    if entry.get("message_key") in GLYPH_ONLY_KEYS:
        return "GLYPH_FAIL" if ratio < NON_TEXT_FLOOR else "GLYPH_OK"
    return "FAIL" if ratio < entry.get("required_floor", 4.5) else "OK"


def _summarise(res: dict[str, Any]) -> dict[str, Any]:
    contrast_nodes: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for v in res.get("violations", []):
        if v["id"] != "color-contrast":
            other.append({"id": v["id"], "impact": v.get("impact"), "nodes": len(v.get("nodes", []))})
            continue
        for n in v.get("nodes", []):
            data = {}
            for check in n.get("any", []):
                if check.get("id") == "color-contrast":
                    data = check.get("data") or {}
                    break
            fg, bg = data.get("fgColor"), data.get("bgColor")
            shadow = data.get("shadowColor")
            size = _pt(data.get("fontSize"))
            weight = _weight(data.get("fontWeight"))
            # FIELD IDENTITY (§11.4.201(9)) — axe measures the EFFECTIVE
            # background: where a `text-shadow` is present it treats the
            # shadow colour as the local backdrop behind the glyph and
            # reports `shadowColor`.  Recomputing against `bgColor` there
            # would compare two DIFFERENT quantities and manufacture a
            # false disagreement.  Proven by control experiment: the same
            # #9d001e-on-#3c3f41 pair reports 1.23 with no shadow, 1.45
            # under --shadow-text-sm and 1.62 under --shadow-text-lg.
            effective_bg = shadow or bg
            entry: dict[str, Any] = {
                "selector": " ".join(n.get("target", [])),
                "html": (n.get("html") or "")[:180],
                "fg": fg,
                "bg": bg,
                "shadow": shadow,
                "effective_bg": effective_bg,
                "font_size_pt": size,
                "font_weight": weight,
                "axe_ratio": data.get("contrastRatio"),
                "axe_expected": data.get("expectedContrastRatio"),
            }
            if fg and effective_bg:
                mine = round(contrast_ratio(fg, effective_bg), 2)
                declared = round(contrast_ratio(fg, bg), 2) if bg else None
                entry["python_ratio"] = mine
                entry["python_ratio_ignoring_shadow"] = declared
                entry["required_floor"] = required_floor(size, weight)
                axe_r = data.get("contrastRatio")
                entry["oracles_agree"] = axe_r is not None and abs(float(axe_r) - mine) <= 0.02
                exp = data.get("expectedContrastRatio")
                if exp:
                    entry["floors_agree"] = abs(float(str(exp).split(":")[0]) - required_floor(size, weight)) < 1e-9
            contrast_nodes.append(entry)
    # THE `incomplete` CHANNEL (§11.4.201(6)) — read, adjudicated, and
    # counted. Round 1 read only `violations`, so every node axe declined
    # to decide was silently scored as a pass.
    incomplete_nodes: list[dict[str, Any]] = []
    for v in res.get("incomplete", []):
        if v["id"] != "color-contrast":
            continue
        for n in v.get("nodes", []):
            entry = _contrast_entry(n, "incomplete")
            entry["verdict"] = _adjudicate_incomplete(entry)
            incomplete_nodes.append(entry)

    blocking_incomplete = [e for e in incomplete_nodes if e["verdict"] in ("FAIL", "UNDECIDABLE", "GLYPH_FAIL")]
    passes = sum(1 for p in res.get("passes", []) if p["id"] == "color-contrast")
    pass_nodes = sum(len(p.get("nodes", [])) for p in res.get("passes", []) if p["id"] == "color-contrast")
    return {
        "contrast_violation_nodes": len(contrast_nodes),
        "contrast_incomplete_nodes": len(incomplete_nodes),
        "contrast_incomplete_blocking": len(blocking_incomplete),
        "contrast_passing_nodes": pass_nodes,
        "contrast_rule_passed": bool(passes),
        "nodes": contrast_nodes,
        "incomplete": incomplete_nodes,
        "other_violations": other,
    }


DEFAULT_THEMES = [("darcula", "dark"), ("darcula", "light")]

# ------------------------------------------------------------- self-check
SELFCHECK_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>BOB-164 contrast oracle self-check</title></head><body style="background:#ffffff">
<p id="golden-bad-equal" style="color:#ffffff;background:#ffffff;font-size:16px">
  white on white, 1.0 to 1, the most flagrant failure a contrast oracle can face</p>
<p id="golden-bad-plain" style="color:#bbbbbb;background:#ffffff;font-size:16px">
  light grey on white, well under the floor</p>
<p id="negative-control" style="color:#000000;background:#ffffff;font-size:16px">
  black on white, 21 to 1, must never be reported as a failure</p>
</body></html>
"""


def selfcheck() -> int:
    """Prove the oracle can SEE a violation before any run is believed.

    §11.4.107(10) / §11.4.201(7)(b). Three fixtures through the SAME code
    path a real scan uses:

      golden-bad-equal    white on white. axe does NOT report this as a
                          violation — it lands in `incomplete` with
                          messageKey `equalRatio`. Round 1 read only
                          `violations`, so this scored as a PASS. If this
                          fixture is not caught, the oracle is blind in
                          exactly the way that hid the round-1 defect.
      golden-bad-plain    ordinary sub-floor pair, expected in `violations`.
      negative-control    black on white. Must NOT be reported — a checker
                          that flags everything is worthless (§11.4.201(1)).
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "index.html").write_text(SELFCHECK_HTML, encoding="utf-8")
        url, httpd, _ = _serve(Path(td))
        try:
            out = scan(url, [("fixture", "static")], wait_for_app=False)
        finally:
            httpd.shutdown()

    summary = next(iter(out["themes"].values()))
    flagged = {e["selector"] for e in summary["nodes"]}
    flagged |= {
        e["selector"] for e in summary["incomplete"]
        if e["verdict"] in ("FAIL", "UNDECIDABLE", "GLYPH_FAIL")
    }
    ok = True
    for needle in ("#golden-bad-equal", "#golden-bad-plain"):
        hit = any(needle in sel for sel in flagged)
        print(f"  golden-bad  {needle:<20} {'CAUGHT' if hit else 'MISSED -> ORACLE IS BLIND'}")
        ok &= hit
    ctrl = any("#negative-control" in sel for sel in flagged)
    print(f"  neg-control #negative-control  {'FALSE POSITIVE' if ctrl else 'correctly silent'}")
    ok &= not ctrl
    print(f"\nself-check: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1



def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", type=Path, help="static dist dir to serve")
    ap.add_argument("--url", help="already-running URL to scan instead of --dist")
    ap.add_argument("--out", type=Path, help="where to write the JSON report (not used by --self-check)")
    ap.add_argument("--all-palettes", action="store_true", help="scan every palette id in both modes")
    ap.add_argument("--self-check", action="store_true",
                    help="validate the oracle against golden-good/golden-bad fixtures and exit")
    args = ap.parse_args()

    if args.self_check:
        return selfcheck()

    themes = DEFAULT_THEMES
    if args.all_palettes:
        ids = ["darcula", "dracula", "solarized", "nord", "monokai", "gruvbox", "one-dark", "tokyo-night"]
        themes = [(i, m) for i in ids for m in ("dark", "light")]

    if not args.out:
        raise SystemExit("--out is required unless --self-check is given")

    httpd = None
    try:
        if args.url:
            url = args.url
        else:
            if not args.dist or not (args.dist / "index.html").is_file():
                raise SystemExit(f"--dist has no index.html: {args.dist}")
            url, httpd, _ = _serve(args.dist.resolve())
        out = scan(url, themes)
    finally:
        if httpd:
            httpd.shutdown()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")

    total = 0
    total_blocking_incomplete = 0
    print(f"axe-core {out['axe_version']}  target={out['url']}")
    for label, summary in out["themes"].items():
        n = summary["contrast_violation_nodes"]
        total += n
        total_blocking_incomplete += summary["contrast_incomplete_blocking"]
        print(f"\n=== theme {label}: {n} colour-contrast violation node(s), "
              f"{summary['contrast_passing_nodes']} passing node(s) ===")
        for e in summary["nodes"]:
            agree = "ratio+floor agree" if (e.get("oracles_agree") and e.get("floors_agree")) else "ORACLE MISMATCH"
            shadow = f" shadow={e['shadow']}" if e.get("shadow") else ""
            print(
                f"  {e['selector'][:44]:<46} fg={e['fg']} bg={e['bg']}{shadow} "
                f"{e['font_size_pt']}pt/{int(e['font_weight'])} "
                f"axe={e['axe_ratio']} py={e.get('python_ratio')} "
                f"floor={e.get('required_floor')} ({agree})"
            )
        for e in summary["incomplete"]:
            print(
                f"  [incomplete/{e['verdict']:<11}] {e['selector'][:40]:<42} "
                f"fg={e['fg']} bg={e['bg']} key={e['message_key']} "
                f"py={e.get('python_ratio')} floor={e.get('required_floor')}"
            )
        if summary["other_violations"]:
            print(f"  [non-contrast violations present: {summary['other_violations']}]")
    print(f"\nTOTAL colour-contrast violation nodes across {len(out['themes'])} theme(s): {total}")
    unmeasured = sum(
        1 for sm in out["themes"].values() for e in sm["incomplete"] if e["verdict"] == "GLYPH_UNMEASURED"
    )
    print(f"TOTAL blocking `incomplete` nodes (FAIL / UNDECIDABLE / GLYPH_FAIL): {total_blocking_incomplete}")
    print(f"TOTAL fenced GLYPH_UNMEASURED nodes (reported, not blocking; SC 1.4.11 unverified): {unmeasured}")
    print(f"written: {args.out}")
    return 0 if (total == 0 and total_blocking_incomplete == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
