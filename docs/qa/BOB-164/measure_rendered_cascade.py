#!/usr/bin/env python3
"""BOB-164 round 2 — measure the REAL rendered cascade for the badge and
status nodes the contrast scan never sees.

WHY THIS EXISTS.  `axe_contrast_scan.py` scans a static dist with no
backend, so the results table and the hooks list render EMPTY and their
`.type-badge` / `.quality-badge` / `.status` nodes are absent from the
page being measured (tracked as BOB-185).  The round-1 review reasoned
about those nodes from the stylesheet alone and concluded they rendered
WHITE text.  This script settles it by MEASUREMENT instead: it loads a
real bundle in a real headless Chromium, finds the component's Angular
style-scoping attribute, injects the exact markup
`dashboard.component.html` emits, and reads `getComputedStyle`.

USAGE
    .venv/bin/python docs/qa/BOB-164/measure_rendered_cascade.py \
        --dist download-proxy/src/ui/dist/frontend/browser      # pre-fix
    .venv/bin/python docs/qa/BOB-164/measure_rendered_cascade.py \
        --dist /tmp/dist_r2/browser                             # post-fix

Exit status is informational: this is a MEASUREMENT, not a gate.  The
gates are `axe_contrast_scan.py` and
`frontend/src/app/models/style-contrast.spec.ts`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("axescan", Path(__file__).with_name("axe_contrast_scan.py"))
axescan = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(axescan)

# Exactly the class combinations dashboard.component.html emits.
NODES = [
    "status unknown", "status active", "status running", "status failed",
    "type-badge unknown", "type-badge ebook", "type-badge movie",
    "quality-badge unknown", "quality-badge full_hd", "quality-badge hd", "quality-badge uhd_4k",
]

JS = """
(classes) => {
  const probe = document.querySelector('.results-table') || document.querySelector('[class*="stat-"]')
             || document.querySelector('app-dashboard *') || document.querySelector('app-root *');
  let scope = null;
  if (probe) for (const a of probe.attributes) if (a.name.startsWith('_ngcontent')) { scope = a.name; break; }
  const host = document.querySelector('app-dashboard') || document.querySelector('app-root') || document.body;
  const out = { scope, bodyColor: getComputedStyle(document.body).color, nodes: {} };
  for (const cls of classes) {
    const s = document.createElement('span');
    s.className = cls;
    if (scope) s.setAttribute(scope, '');
    s.textContent = 'No';
    host.appendChild(s);
    const cs = getComputedStyle(s);
    out.nodes[cls] = { color: cs.color, background: cs.backgroundColor,
                       fontSize: cs.fontSize, fontWeight: cs.fontWeight };
    s.remove();
  }
  return out;
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", type=Path, required=True)
    ap.add_argument("--palette", default="darcula")
    ap.add_argument("--mode", default="dark")
    args = ap.parse_args()

    url, httpd, _ = axescan._serve(args.dist.resolve())
    try:
        from playwright.sync_api import sync_playwright

        exe = axescan._chromium_executable()
        launch = {"headless": True}
        if exe:
            launch["executable_path"] = exe
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            page.goto(url, timeout=30_000)
            page.evaluate(
                "([k, v]) => localStorage.setItem(k, v)",
                [axescan.THEME_STORAGE_KEY,
                 json.dumps({"paletteId": args.palette, "mode": args.mode, "explicitMode": True})],
            )
            page.reload(timeout=30_000)
            page.wait_for_selector("app-root *", timeout=20_000)
            page.wait_for_timeout(600)
            res = page.evaluate(JS, NODES)
            browser.close()
    finally:
        httpd.shutdown()

    print(f"dist={args.dist}  theme={args.palette}/{args.mode}  "
          f"scope={res['scope']}  body color={res['bodyColor']}")
    worst = 0
    for name, n in res["nodes"].items():
        ratio = axescan.contrast_ratio(n["color"], n["background"])
        pt = float(n["fontSize"].rstrip("px")) * 0.75
        floor = axescan.required_floor(pt, float(n["fontWeight"]))
        verdict = "FAIL" if ratio < floor else "ok"
        worst += 1 if verdict == "FAIL" else 0
        print(f"  {name:<22} fg={n['color']:<22} bg={n['background']:<22} "
              f"{pt:.2f}pt/{n['fontWeight']}  ratio={ratio:.2f}  floor={floor}  {verdict}")
    print(f"\n{worst} of {len(res['nodes'])} measured nodes below their floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
