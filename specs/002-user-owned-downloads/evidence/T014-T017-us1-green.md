# US1 GREEN — the fix, and what measurement changed about the plan

**Date**: 2026-08-21 · rootless podman · operator uid 1000

## The plan was wrong about three of the five services, and measurement caught it

The plan called for a MIXED ROUTE: `PUID=0` for the two linuxserver services, and
`userns_mode: keep-id` for `download-proxy`, `qbittorrent-proxy-go`, `boba-jackett`.

Before editing anything, each service was probed:

```
podman exec <svc> id -u        ->  qbittorrent 0 · jackett 0 · qbittorrent-proxy 0 · boba-jackett 0

write probe (write a real file into a host-mounted path, read the owner back FROM THE HOST):
  download-proxy                       -> uid 1000 (milosvasic)     already correct
  boba-jackett                         -> uid 1000 (milosvasic)     already correct
  qbittorrent via `s6-setuidgid abc`   -> uid 100999 (UNKNOWN)      the defect
```

The third line is the **control**: it proves the probe can SEE the defect, so the two
`1000` readings are a real result rather than a blind instrument (§11.4.201(7) — a null is
not evidence until a control needle shows the instrument can see through the same path).
`qBitTorrent-go/Dockerfile` has no `USER` directive, so that service runs as root too.

Under rootless podman container uid 0 **is** the host operator, so a container already
running as root already writes operator-owned files. Applying `keep-id` to those three
would have changed nothing useful AND left them with no usable root — the same failure the
research phase had already measured on the linuxserver images, where `--userns=keep-id`
made the container hang with no output, twice.

**T010/T011/T012 are therefore closed as "no change required — measured", not "done".**
Only `qbittorrent` and `jackett` were changed.

Root cause of the planning error: research measured `keep-id` against a bare `alpine` —
which runs as root and has no init — and generalised to three services it had not probed
individually. A measurement taken through a different path than the one you intend to gate
is not evidence about that path.

## T015 — the RED went GREEN, and the guard has teeth

The RED test originally hardcoded `PUID=1000`. That asserts a permanent property of the
*image* ("told to run its app as uid 1000, it produces host uid 100999"), which is true and
unfixable — no change to this project can make it false. A test that can never go green is
not a RED; it would have kept failing after the defect was fixed, which is the
§11.4.201(1) false-positive refusal. Reconciled per §11.4.120 to read PUID/PGID **from
docker-compose.yml** — the configuration this feature actually changes.

```
2 passed in 19.58s
```

§1.1 mutation — revert the fix in compose, re-run:

```
AssertionError: file written by the containerised application is owned by uid 100999,
                but the operator is uid 1000.
AssertionError: directories created by the containerised application are not owned by
                the operator (uid 1000): [('outer', 100999), ('outer/inner', 100999)]
FAILED test_container_written_directory_is_owned_by_the_operator
FAILED test_container_written_file_is_owned_by_the_operator
```

Restored; `sha256 ef8e810af47125b5` before and after — byte-identical; 2 passed again.

## T016 — the LIVE stack, not an ad-hoc container run

```
qbittorrent  s6-setuidgid abc touch /downloads/... -> host sees 1000 (milosvasic)
operator can delete it without elevation?             YES
```

## T017 — a real download through the real service

A public-domain Debian netinst torrent (public tracker: no private-tracker ratio spent,
which is why it was chosen over the freeleech path). qBittorrent downloaded the **whole
791 MB ISO** through its own I/O path — preallocation, `Incomplete/` temp dir,
move-on-complete — not a `touch`:

```
1000  drwxrwxrwx        202  .../Downloads
1000  drwxrwxrwx          0  .../Downloads/Incomplete          <- created by qBittorrent
1000  -rw-r--r--  791674880  .../Downloads/debian-13.6.0-amd64-netinst.iso

distinct owners of freshly-downloaded content: uid 1000

RENAME OK
write into the dir qBittorrent created: OK
```

Torrent and data removed afterwards; 0 torrents remain, ISO gone, empty `Incomplete/`
removed, 2.2 T free.

## A false null hit for real during this validation

`find "$DD" -newermt '-6 minutes'` reported **0 items** while a 791 MB file 79 seconds old
sat in that directory. `find` on this host is **bfs 4.1.1**, which *rejects* every relative
`-newermt` form: it writes an error to stderr and prints nothing to stdout, so reading only
stdout turns a hard failure into a clean empty result.

This was caught only because a file of known age was on disk to act as a control. Without
it the conclusion would have been "the download created no files" about a system that had
just written 791 MB — a §11.4.201(6) false null, and one that `quickstart.md` shipped: its
Scenario 1 contained that exact command and would have misled every operator on this host.
Fixed to `-mmin -10`, with the reason recorded inline so it is not "simplified" back.
