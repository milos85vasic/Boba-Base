# BOB-141 closure evidence — 2026-09-23 (staleness-corrected closure)

## Finding
Already fixed in a prior session — CLAUDE.md's Architecture section
already contains a full, explicitly-cited BOB-141 correction (lines
140-164) accurately stating the Go profile's single binary binds only
7187, cross-referenced against `qBitTorrent-go/Dockerfile:16` and
`internal/config/config.go:58`. The Port Map table entry for 7188 also
already carries the accurate BOB-141 annotation. No edit was needed or
made — the tracker status was never advanced to reflect the prior fix.

## Independent verification (coordinator, from clean shell)
```
$ git status --short CLAUDE.md
(empty)
$ grep -n "BOB-141" CLAUDE.md
142:  service on **7187** only. *(Corrected 2026-08-20, BOB-141. ...
152:  intent) is an open question tracked as BOB-141; ...
173:| 7188 | webui-bridge (... NOT started by the `qbittorrent-proxy-go`
     container, see BOB-141) | manual start |
```
Cross-checked against actual source:
```
$ grep -n "CMD\|EXPOSE" qBitTorrent-go/Dockerfile
28:EXPOSE 7187 7188
29:CMD ["/app/qbittorrent-proxy"]
$ grep -n "ServerPort" qBitTorrent-go/internal/config/config.go
67:  ServerPort: getEnvAsInt("MERGE_SERVICE_PORT", ... 7187),
```
Confirms the documented claim matches reality exactly: one binary, one
bound port (7187), 7188 declared-but-unbound.

## Honest, genuinely new finding surfaced during this investigation (NOT
   part of this item's scope — filed as its own follow-up per §11.4.238)
`AGENTS.md:55` still carries the SAME stale false claim CLAUDE.md already
corrected: `| Go backend | qbittorrent-proxy-go | ... | 7186, 7187, 7188 |
Opt-in via --profile go; replaces Python proxy |`. Independently confirmed
present. See BOB-232 (new item filed for this).

## Status
Fixed (already landed, tracker sync only). Closed by coordinator.
