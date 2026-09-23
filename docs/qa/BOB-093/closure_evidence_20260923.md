# BOB-093 closure evidence 2026-09-23 (read-only live verification)

Container: qbittorrent-proxy (healthy). Nothing restarted/modified. Reads via podman exec cat only.

## 1. Deployed == repo (sha256)
```
container /config/qBittorrent/nova3/engines/rutracker.py : 98e3cb71f3bc06633c9defba8f2be881eda3444f17306d3644de684164e6f858
repo plugins/rutracker.py                                : 98e3cb71f3bc06633c9defba8f2be881eda3444f17306d3644de684164e6f858
copy of container file (podman exec cat > scratch)       : 98e3cb71f3bc06633c9defba8f2be881eda3444f17306d3644de684164e6f858
```
Bounded quantifiers grep'd inside the container:
```
140:    re_search_queries = re.compile(r'<a[^>]{0,512}?href="tracker\.php\?([^"]{0,256}?start=\d+)"')
151:    re_threads = re.compile(r'<tr id="trs-tr-\d{1,12}.{0,4096}?</tr>', re.S)
```

## 2. Existing regression tests (tests/stress/test_rutracker_redos_bounds.py + tests/unit/test_plugin_rutracker.py), nice -n 19, timeout 300
Repo copy is byte-identical to deployed (section 1), so this exercises the deployed bytes.
```
........................................................................ [ 72%]
...........................                                              [100%]
99 passed in 12.32s

real	0m14.138s
user	0m13.209s
sys	0m0.794s
```

## 3. Deployed-copy probe with control needle (same interpreter/path/inputs)
Probe loads the container-extracted file; CONTROL uses the historical unbounded patterns.
```
DEPLOYED re_threads tr_storm 64KB : 0.1995s
DEPLOYED re_torrent_data gtlt 2KB : 0.000012s
DEPLOYED re_torrent_data ts 4KB   : 0.0049s
CONTROL unbounded tr_storm 64KB   : 1.4025s
CONTROL unbounded gtlt 2KB        : 3.2513s

real	0m5.022s
user	0m4.925s
sys	0m0.037s
```

Reading: bounded deployed regexes finish in <=0.2s where the unbounded control takes 1.4s (tr storm) and 3.25s (gtlt) on the same inputs, so the instrument sees the blow-up and the deployed code does not exhibit it.

## Honest gaps
- Tests import the repo path, not the container path; equivalence rests on the identical sha256, not on executing inside the container (no exec of python in container performed).
- Sub-step 4 (time a LARGE REAL rutracker result page <2s) NOT met: needs live rutracker access; previously blocked by 403 (see Issues.md). Synthetic adversarial inputs only.
- Tracker item BOB-093 NOT closed.
