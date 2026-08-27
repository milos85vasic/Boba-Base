#!/usr/bin/env python3
"""THE ORACLE for CM-EXPORT-CHARSET-VALID (§11.4.245, §11.4.249).

Decides, per generated export, compliant vs non-compliant. It knows NOTHING
about thresholds, baselines, ratchets, or exit-code policy — that knowledge
lives in its two consumers (the gate and the tightener), which is what keeps
those two from ever disagreeing about the count they act on.

ORACLE STRATEGY (§11.4.245): INVARIANT. A generated HTML export must declare its
own encoding. The expected value comes from the HTML spec, not from the code
that produced the file, so the oracle is structurally independent of the
producer it judges.

WHAT COUNTS AS A GENERATED EXPORT: an .html with a sibling .md. Hand-authored
page furniture has no .md twin and is out of scope.

WHAT COUNTS AS COMPLIANT: a <meta ... charset...> ELEMENT. Structure, never the
bare substring — a document is not self-describing because its prose contains
the word "charset" (§11.4.201(7)(a); measured during BOB-169: a naive
`grep -qi charset` PASSED against the broken generator by matching a heading slug).

Usage:  cm_export_charset_scan.py <scan_root>
Output: one line — "<total> <bad> <compliant> <sample_basename>"
Exit:   0 always on a completed scan. Deciding what the numbers MEAN is the
        caller's job; an oracle that also refuses is an oracle=gate collapse.
"""
import io
import os
import re
import sys

META_CHARSET = re.compile(r'<meta[^>]+charset', re.I)
HEAD_BYTES = 4096


def scan(root):
    """Return (pairs, bad) — every generated export, and those lacking a charset."""
    pairs = []
    for base in ('docs', 'scripts'):
        for dirpath, _dirnames, filenames in os.walk(os.path.join(root, base)):
            for name in filenames:
                if not name.endswith('.html'):
                    continue
                html = os.path.join(dirpath, name)
                if os.path.exists(html[:-5] + '.md'):
                    pairs.append(html)
    try:
        for name in os.listdir(root):
            if name.endswith('.html') and os.path.exists(os.path.join(root, name[:-5] + '.md')):
                pairs.append(os.path.join(root, name))
    except OSError:
        pass

    bad = []
    for html in pairs:
        try:
            head = io.open(html, encoding='utf-8', errors='replace').read(HEAD_BYTES)
        except OSError:
            continue
        if not META_CHARSET.search(head):
            bad.append(html)
    return pairs, bad


def main():
    if len(sys.argv) != 2:
        sys.stderr.write('usage: cm_export_charset_scan.py <scan_root>\n')
        return 2
    pairs, bad = scan(sys.argv[1])
    sample = os.path.basename(bad[0]) if bad else '-'
    print(len(pairs), len(bad), len(pairs) - len(bad), sample)
    return 0


if __name__ == '__main__':
    sys.exit(main())
