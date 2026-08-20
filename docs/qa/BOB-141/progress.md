# BOB-141 — CLAUDE.md vs the Go Dockerfile: doc corrected, provisioning question OPEN

**Revision:** 1
**Last modified:** 2026-08-20T17:05:00Z

## What was wrong

CLAUDE.md stated the Go profile "replaces the Python proxy on **7186**, **7187**,
**7188**". The container cannot deliver that. Read from source, not prose:

```
qBitTorrent-go/Dockerfile:16    CMD ["/app/qbittorrent-proxy"]        (ONE binary)
qBitTorrent-go/Dockerfile:15    EXPOSE 7187 7188                      (declares 2)
cmd/qbittorrent-proxy/main.go   r.Run(fmt.Sprintf(":%d", cfg.ServerPort))  (binds 1)
internal/config/config.go:58    ServerPort = MERGE_SERVICE_PORT (default 7187)
```

`webui-bridge` is a separate binary (`cmd/webui-bridge`, `/bridge/health`,
`cfg.BridgePort`) that this container never starts. Nothing in it binds 7186
either, though the compose service sets `PROXY_PORT=7186` and `BRIDGE_PORT=7188`
in its environment, which reinforces the wrong impression.

## Why it mattered

This prose was used as the source of truth when authoring
`config/served_ports.yaml`, producing `serves: [7186, 7187, 7188]` for that
service. The healthcheck gate built on it then FAILED a service whose healthcheck
was already correct — a §11.4.201(1) false-positive refusal caused directly by
trusting the doc over the Dockerfile. The manifest was corrected against source at
the time; the doc was not, and would have misled the next reader identically.

## Done in this pass

- CLAUDE.md line 110 now states the container serves **7187 only**, with the
  source citations inline so the next reader can re-derive it rather than trust
  another sentence.
- The Port Map row for 7188 now says explicitly that the `qbittorrent-proxy-go`
  container does NOT start webui-bridge.

Verified by re-deriving from source after the edit (Dockerfile CMD, `r.Run(addr)`,
`ServerPort` resolution all re-read and quoted above).

## STILL OPEN — an operator decision, deliberately not made here

Whether the doc was wrong, or the CONTAINER is under-provisioned relative to the
original intent (it should also run webui-bridge and a 7186 listener), is not
determinable from the code — both readings are consistent with what exists. The
doc now describes REALITY, which is the safe reversible state (§11.4.101); if the
intent was a three-port container, the fix is to provision it and re-widen the
doc, not to leave a doc describing something that does not run.

Whichever way it resolves, these should agree with reality afterwards:
- the compose service's `PROXY_PORT` / `BRIDGE_PORT` env vars, which no process
  in that container consumes;
- the Dockerfile's `EXPOSE 7187 7188`, which declares a port nothing binds;
- `config/served_ports.yaml`, which currently declares `serves: [7187]`.

BOB-141 therefore stays OPEN.
