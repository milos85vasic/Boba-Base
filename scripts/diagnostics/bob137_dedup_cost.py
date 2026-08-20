"""BOB-137: count regex operations performed by merge_results as N grows.

Usage (inside the container, which has the Levenshtein dependency the host
lacks -- a host run measures a DIFFERENT code path and is not comparable):

    podman exec -i qbittorrent-proxy nice -n 19 python3 - \
        < scripts/diagnostics/bob137_dedup_cost.py

Set BOB137_DISTINCT=1 for the low-match-rate (worst-case) dataset.

Count regex operations performed by merge_results as N grows.

A COUNT is deterministic and immune to CPU contention, unlike a timing
measurement -- which matters here because the only host with the right
dependencies is currently busy running the very defect under study
(§11.4.201(8): use a metric that is valid under the available conditions).
"""
import os
import random
import re
import sys

sys.path.insert(0, "/config/download-proxy/src")

CALLS = {"sub": 0, "search": 0, "match": 0, "findall": 0}
for name in list(CALLS):
    orig = getattr(re, name)
    def make(o, n):
        def wrapper(*a, **k):
            CALLS[n] += 1
            return o(*a, **k)
        return wrapper
    setattr(re, name, make(orig, name))

# These imports MUST come AFTER the re.* wrapping above: the deduplicator
# resolves re.sub/re.search at call time via the module, so wrapping first is
# what makes the counters observe it. Hence the E402 exemptions.
from merge_service.deduplicator import Deduplicator  # noqa: E402
from merge_service.search import SearchResult  # noqa: E402

random.seed(7)
WORDS = ["Ubuntu","Debian","Matrix","Inception","Arch","Fedora","Show","Movie","Pack","Season"]
DISTINCT = os.environ.get("BOB137_DISTINCT", "").strip() not in ("", "0", "no")
def mk(i):
    if DISTINCT:
        n = f"Title{i}Unique{i*7919%100003} Release{i} {1990+i%35} 1080p x264 [GRP{i}] part{i}"
    else:
        n = f"{random.choice(WORDS)} {random.choice(WORDS)} {1990+i%35} 1080p x264 [GRP{i%50}] part{i}"  # noqa: S311 - synthetic benchmark data, never cryptographic
    return SearchResult(name=n, link=f"magnet:?xt=urn:btih:{i:040x}",
                        size=f"{1+i%20} GB", seeds=i%100, leechers=i%10,
                        engine_url=f"http://t{i%43}.example", tracker=f"t{i%43}")

print(f"{'N':>6} {'regex_ops':>12} {'ops/N^2':>10} {'growth':>22}", flush=True)
prev = None
for N in (50, 100, 200, 400):
    for k in CALLS:
        CALLS[k] = 0
    res = [mk(i) for i in range(N)]
    Deduplicator().merge_results(res)
    total = sum(CALLS.values())
    growth = ""
    if prev:
        pn, pt = prev
        growth = f"N x{N/pn:.0f} -> ops x{total/pt:.1f} (quad={((N/pn)**2):.0f})"
    print(f"{N:>6} {total:>12,} {total/(N*N):>10.1f} {growth:>22}", flush=True)
    prev = (N, total)
