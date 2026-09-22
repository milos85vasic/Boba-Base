# BOB-198 closure evidence — 2026-09-22

## Fix (implements the recorded operator decision exactly — no auth middleware added)

**Operator decision (2026-08-26, §11.4.66): "REFUSE TO START LAN-BOUND"** — a
boot-time guard, not auth middleware.

`qBitTorrent-go/cmd/qbittorrent-proxy/main.go`:
- New `checkLoopbackBind(bindHost string) error` (line ~163) — refuses
  anything that is not a loopback address (`127.0.0.0/8` literal, `::1`, or
  `localhost` case-insensitive); syntax-only, no DNS resolution (an
  unresolvable hostname fails closed rather than being trusted).
- Called immediately after log setup in `main()` (line ~36), before the
  qBittorrent connection attempt, proxy config, or any store opens.
  `log.Fatal()` on refusal — logs the actual configured address and exits
  non-zero; the code never reaches `r.Run(addr)`.
- The listener bind itself changed from the prior bare `":%d"`
  (all-interfaces) form to `"%s:%d"` using the new `ServerBindHost` (line
  ~140) — the real fix, with the boot-time check as defense-in-depth against
  a future regression.

`qBitTorrent-go/internal/config/config.go`: new `Config.ServerBindHost`
field, env `SERVER_BIND_HOST`, defaulting to `"127.0.0.1"`.

No auth middleware was added anywhere — confirmed by inspection, middleware
registration (CORS/Logger/GinRateLimit) is unchanged.

## RED evidence

The test file was written first, referencing `checkLoopbackBind` before it
existed — build failure (`undefined: checkLoopbackBind`) proved the pre-fix
code had no boot-time guard of any kind.

## GREEN + golden-FALSE evidence (independently re-verified this session)

```
$ cd qBitTorrent-go && go build ./cmd/qbittorrent-proxy/... ./internal/config/...
$ go vet ./cmd/qbittorrent-proxy/... ./internal/config/...
$ go test ./cmd/qbittorrent-proxy/... ./internal/config/... -v
--- PASS: TestGuard_RefusesNonLoopbackBind (0.00s)
    --- PASS: .../explicit_all-interfaces_literal (0.00s)
    --- PASS: .../empty_host_(Go's_:port_all-interfaces_shorthand) (0.00s)
    --- PASS: .../specific_LAN_IP (0.00s)
    --- PASS: .../another_specific_non-loopback_IP (0.00s)
    --- PASS: .../unresolvable_/_arbitrary_hostname_(fail-closed,_no_DNS_trust) (0.00s)
    --- PASS: .../IPv6_non-loopback_literal (0.00s)
--- PASS: TestGuard_AllowsGenuineLoopbackBind (0.00s)
    --- PASS: .../IPv4_loopback_literal (0.00s)
    --- PASS: .../localhost,_lowercase (0.00s)
    --- PASS: .../localhost,_mixed_case_(case-insensitive) (0.00s)
    --- PASS: .../IPv6_loopback_literal (0.00s)
    --- PASS: .../any_127.0.0.0/8_literal,_not_just_.1 (0.00s)
PASS
ok  	github.com/milos85vasic/qBitTorrent-go/cmd/qbittorrent-proxy	(cached)
--- PASS: TestLoad_Defaults, TestLoad_EnvOverride, TestLoad_TrackerAuth,
          TestLoad_TrackerCookies, TestLoad_KinozalFallback,
          TestLoad_MetadataAPIKeys, TestQBittorrentURL (all pre-existing,
          all still pass — no regression from the new ServerBindHost field)
PASS
ok  	github.com/milos85vasic/qBitTorrent-go/internal/config	(cached)
```

6/6 refusal subtests (0.0.0.0, empty-string all-interfaces shorthand, two
specific non-loopback IPs, an arbitrary hostname proving no-DNS-trust, a
non-loopback IPv6 literal) and 5/5 golden-FALSE subtests (127.0.0.1,
localhost, LocalHost case-insensitivity, ::1, and 127.0.0.53 proving the
whole 127.0.0.0/8 block is accepted not just .1) all PASS.

## Additional real-process runtime evidence (captured by the implementing agent, beyond what was required)

Built the actual binary and ran it twice on scratch ports:
- `SERVER_BIND_HOST=0.0.0.0` → logged the fatal refusal and exited 1; server
  never started.
- Default (unset) → `ss -tlnp` confirmed `LISTEN 127.0.0.1:<port>` (not
  `0.0.0.0`).

## git diff --stat

```
qBitTorrent-go/cmd/qbittorrent-proxy/main.go | 92 +++++++++++++++++++++++++++-
qBitTorrent-go/internal/config/config.go     | 20 ++++--
2 files changed, 106 insertions(+), 6 deletions(-)
```
Plus new untracked `qBitTorrent-go/cmd/qbittorrent-proxy/main_test.go` (117 lines).

## Residual note (informational, not acted on — out of this item's scope)

`config/lan_route_auth_policy.yaml` carries a comment citing this file's OLD
bind behavior — now stale, but it documents a *different* gate
(`scripts/pre_build/check_cm_lan_routes_authenticated.sh`, route-level
auth-marker wiring for the Python service) unrelated to this fix; not
touched. `docker-compose.yml`'s `MERGE_SERVICE_HOST=0.0.0.0` for the
`qbittorrent-proxy-go` service is a distinct env var from the new
`SERVER_BIND_HOST` this fix introduces and has no effect on this guard.
