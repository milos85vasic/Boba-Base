#!/usr/bin/env python3
"""failopen_lang_analyzer.py — fail-open idiom detector for Rust, Ruby and C
(BOB-191), used by scripts/pre_build/check_fail_open_unanalysed_langs.sh.

The constitution's CM-DANGEROUS-COMBINATION-FAIL-CLOSED scanner enumerates
.rs/.rb/.c files but has no analyser for them (they are reported UNANALYSED).
This analyser covers ONLY shapes that are fail-open by construction, so it does
not manufacture BOB-189-class false positives (a guard that returns false on an
error is fail-CLOSED and is never reported):

  RS-EMPTY-ERR-ARM     `Err(..) => {}` / `Err(..) => ()` — the error arm does nothing
  RS-EMPTY-IF-LET-ERR  `if let Err(..) = expr {}` — error matched, then dropped
  RB-EMPTY-RESCUE      `rescue [Class] [=> e]` immediately followed by `end`
  RB-RESCUE-NIL        `expr rescue nil` / `rescue nil` — every error becomes nil
  C-EMPTY-ERR-BRANCH   `if (rc != 0) {}` / `if (ret < 0);` on an error-named
                       status variable — the failure branch is empty

Comments and string literals are blanked (newlines kept) before matching, so a
pattern quoted in a comment or a string is never a hit.

Usage:
  failopen_lang_analyzer.py <file>...     scan; one line per hit
  failopen_lang_analyzer.py --selfcheck   run every rule on its built-in golden-bad
                                          needle (must be SEEN) and golden-good
                                          snippet (must NOT be seen)
Output:  <path>:<line>: <RULE> <detail>
Exit:    0 no hits / selfcheck passed, 1 hits, 2 unreadable file / selfcheck failed
"""
import re
import sys

EXT_LANG = {".rs": "rust", ".rb": "ruby", ".c": "c", ".h": "c"}


def _blank(match):
    return re.sub(r"[^\n]", " ", match.group(0))


def strip_c_like(text):
    # block comments, line comments, double-quoted strings, char literals
    pat = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])\'', re.S)
    return pat.sub(_blank, text)


def strip_ruby(text):
    pat = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|#[^\n]*', re.S)
    return pat.sub(_blank, text)


RULES = {
    "rust": [
        ("RS-EMPTY-ERR-ARM", re.compile(r"\bErr\s*\([^()]*\)\s*=>\s*(?:\{\s*\}|\(\s*\))"),
         "error match arm does nothing"),
        ("RS-EMPTY-IF-LET-ERR", re.compile(r"\bif\s+let\s+Err\s*\([^()]*\)\s*=[^{;]*\{\s*\}"),
         "error matched then dropped (empty body)"),
    ],
    "ruby": [
        ("RB-EMPTY-RESCUE", re.compile(r"\brescue\b[ \t]*(?:[A-Z][\w:]*)?[ \t]*(?:=>[ \t]*\w+)?[ \t]*(?:\n|;)\s*end\b"),
         "rescue clause with an empty body"),
        ("RB-RESCUE-NIL", re.compile(r"\brescue[ \t]+nil\b"),
         "every error is converted to nil"),
    ],
    "c": [
        ("C-EMPTY-ERR-BRANCH",
         re.compile(r"\bif\s*\(\s*(?:\w*(?:err|ret|rc|status|res)\w*)\s*(?:!=\s*0|<\s*0|==\s*-1)\s*\)\s*(?:\{\s*\}|;)", re.I),
         "failure branch on an error status is empty"),
    ],
}

STRIP = {"rust": strip_c_like, "c": strip_c_like, "ruby": strip_ruby}


def scan_text(lang, text):
    body = STRIP[lang](text)
    hits = []
    for rule, rx, detail in RULES[lang]:
        for m in rx.finditer(body):
            hits.append((body.count("\n", 0, m.start()) + 1, rule, detail))
    return sorted(hits)


SELFCHECK = {
    "rust": (
        'fn f() { match g() { Ok(v) => use_it(v), Err(_) => {} }\n if let Err(e) = h() {} }\n',
        'fn f() -> bool { match g() { Ok(_) => true, Err(_) => false } }\n// Err(_) => {}\nlet s = "Err(x) => {}";\n',
        {"RS-EMPTY-ERR-ARM", "RS-EMPTY-IF-LET-ERR"},
    ),
    "ruby": (
        "begin\n  risky\nrescue => e\nend\nx = parse(s) rescue nil\n",
        "begin\n  risky\nrescue => e\n  raise AuthError\nend\n# rescue nil\ny = 'rescue nil'\n",
        {"RB-EMPTY-RESCUE", "RB-RESCUE-NIL"},
    ),
    "c": (
        "int f(void) { int rc = g(); if (rc != 0) {} return 0; }\n",
        "int f(void) { int rc = g(); if (rc != 0) { return -1; } /* if (rc != 0) {} */ return 0; }\n",
        {"C-EMPTY-ERR-BRANCH"},
    ),
}


def selfcheck():
    ok = True
    for lang, (bad, good, want) in SELFCHECK.items():
        seen = {r for _, r, _ in scan_text(lang, bad)}
        missing = want - seen
        if missing:
            print(f"SELFCHECK FAIL {lang}: golden-bad needle NOT seen for {sorted(missing)} — analyser blind")
            ok = False
        else:
            print(f"SELFCHECK ok {lang}: needle seen for {sorted(want)}")
        false_pos = scan_text(lang, good)
        if false_pos:
            print(f"SELFCHECK FAIL {lang}: golden-good snippet flagged {false_pos} — false positive")
            ok = False
        else:
            print(f"SELFCHECK ok {lang}: golden-good snippet stays silent")
    return 0 if ok else 2


def main(argv):
    if argv == ["--selfcheck"]:
        return selfcheck()
    if not argv:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    total, bad = 0, 0
    for path in argv:
        lang = next((l for e, l in EXT_LANG.items() if path.endswith(e)), None)
        if lang is None:
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print(f"UNREADABLE {path}: {exc}", file=sys.stderr)
            bad += 1
            continue
        for line, rule, detail in scan_text(lang, text):
            print(f"{path}:{line}: {rule} {detail}")
            total += 1
    if bad:
        return 2
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
