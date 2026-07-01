# Porting Lava autonomous-QA solutions → Boba-Base (submodules-driven)

Maps the Lava deep-research playbook (`Lava:docs/autonomous-qa/PORTING-PLAYBOOK.md`) onto **Boba-Base's actual stack** (Go `qBitTorrent-go` + Python `download-proxy`/`merge_service` + `plugins` + `frontend`/`extension` + Jackett), respecting Boba-Base's **TDD + anti-bluff (CONST-XII)** mandate. Both repos already share `submodules/{containers, jackett, challenges, helixqa}` + `constitution`, so the reusable pieces land **in the shared submodule** (consumed by both), and only thin glue stays per-repo.

## Applicability triage (honest — not a blind copy)

| Lava §  | Solution | Applies to Boba-Base? | Why |
|---|---|---|---|
| §1 | Containerized **Android** emulator | ❌ no | Boba-Base has no Android; UI is web (`frontend`/`extension`) → browser E2E (Playwright-in-container) is the analog, separate work |
| §2 | Android guest-net `ndc` fix | ❌ no | Android-only |
| §7 | Compose UI Challenge + off-main nav | ❌ no | Android-only |
| **§0/§4** | **Egress-path insight + VPN-host egress** | ✅ **YES — primary** | Same datacenter-IP tracker block; affects Jackett + `merge_service` + `download-proxy` + plugin engines |
| **§3** | **Configurable outbound proxy** | ✅ **YES** | `download-proxy`/`qBitTorrent-go`/Jackett tracker calls need a configurable egress |
| **§5** | **Durable remote execution (systemd-linger)** | ✅ **YES** | `run_all_challenges.sh`/`ci.sh`/`helixqa` long runs on remote hosts get reaped by logind |
| **§8** | **Jackett cookie-login + cookie-harvest** | ⚠️ partial — already present | Boba-Base has `nnmclub-cookie-*`, `extract-tracker-cookies.sh`, `extract-jackett-key.py`; ADD the apikey-vs-cookie management distinction + test fake-equivalence |
| **§6/§9** | **Anti-bluff QA verdict + diagnostics** | ✅ YES | strengthen `run_all_challenges.sh` verdicts + the diagnostic gotchas |

## The four high-value ports (in order)

### P1 — Durable remote execution (§5)  [submodule: containers; glue: scripts/]
**Problem Boba-Base shares:** long QA/deploy runs on a remote host die when the SSH session ends.
**Root cause:** remote `systemd-logind KillUserProcesses` reaps detached user processes (tmux/nohup/setsid all die).
**Fix:** `loginctl enable-linger` + `systemd-run --user --unit=<n> --collect bash runner.sh`; poll `systemctl --user is-active`; sentinel file for completion. Avoid piping the long command through `tail -N` (buffers until exit) — log per-step artifacts.
**Port:** add `containers` submodule helper `pkg/remoteexec` (or `scripts/lib/durable-run.sh`) shared by both repos; wire `scripts/deploy-remote.sh` + `run_all_challenges.sh` to use it. **TDD:** a test that launches a 60s sleeper via the helper, drops the SSH session, and asserts it's STILL running after (fails against the old nohup approach).

### P2 — Egress decision + VPN-host routing (§0/§4)  [submodule: containers; glue: scripts/ + Jackett/proxy env]
**Problem Boba-Base shares:** on a datacenter host, trackers are network-blocked (DNS-fail/TLS-MITM, **not** Cloudflare → FlareSolverr can't fix). Affects Jackett indexer fetches + `merge_service`/`download-proxy` + plugin engines.
**Diagnosis (port the script):** `curl https://api.ipify.org` (host IP) + `curl -o /dev/null -w %{http_code} https://<tracker>/` direct vs via a VPN-host SOCKS proxy. Different egress IP + 200 via proxy ⇒ confirmed.
**Fix:** route outbound through a VPN-connected host (the nezha pattern). SOCKS tunnel `ssh -D 127.0.0.1:1080 -N <vpnhost>` (use `--socks5-hostname` for remote DNS); point Jackett + `download-proxy` + `qBitTorrent-go` at it (P3). For browser-cookie harvest, run the harvester ON the VPN host.
**Port:** `containers` submodule `pkg/egress` (tunnel up/verify) + `scripts/egress-via-vpn.sh` glue; reuse Boba-Base's existing `ensure-macos-tunnel.sh` style. **TDD:** assert the via-proxy egress IP ≠ direct host IP AND a known-blocked tracker returns 200 via proxy.

### P3 — Configurable outbound proxy in the services (§3)
**download-proxy (Python):** `httpx`/`requests` honor `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`/`NO_PROXY` env natively — add an explicit `BOBA_UPSTREAM_PROXY` config that sets these for tracker-bound clients, with loopback bypass (`NO_PROXY=127.0.0.1,localhost,jackett`). **qBitTorrent-go:** set `http.Transport.Proxy` (socks5 native, remote DNS) from a `BOBA_UPSTREAM_PROXY` env — mirror Lava `internal/httpx/proxy.go`. **Jackett:** has a built-in proxy setting (configure via its API/ServerConfig).
**Deploy gotcha (port):** the env must be FORWARDED into the containers (`docker-compose.yml` env / the boba-ctl deploy) — Lava's bug was a missing allow-list entry. **Verify on distroless via `podman inspect`, not `exec printenv`.** **TDD:** a test with a local proxy asserts the service's tracker request traverses it; falsifiability: disable the wiring → test fails.

### P4 — Jackett cookie-login hardening (§8)  [submodule: jackett integration + helixqa fakes]
**Add to Boba-Base's existing cookie infra:** Jackett's **management API** (`/api/v2.0/indexers`, indexer `/config`) needs a **dashboard session cookie** (empty-password `POST /UI/Dashboard`) — the apikey only authorizes Torznab `/results`+`/caps`. If `boba-jackett`/`extract-jackett-key.py` only uses the apikey, `ListIndexers`/config silently 302→`/UI/Login`. **Critical for anti-bluff:** the test fake MUST 302-without-cookie like real Jackett (behavioral equivalence) or the gap stays hidden. **TDD:** fake 302s management without the cookie; assert discovery succeeds via the cookie path; falsifiability: remove cookie login → 302 failure.

## Submodules-driven principle (per Decoupled Reusable Architecture)
- **`containers` submodule** is the home for P1 (durable-exec) + P2 (egress/tunnel) — generic, both repos + future projects consume. Contribute upstream first, then bump the pin in Lava AND Boba-Base.
- **`jackett` integration + `helixqa`** is the home for P4's cookie-login + the behaviorally-equivalent fake.
- **Per-repo glue only:** P3's env wiring (each service's HTTP client + each repo's compose/deploy).

## Execution order (TDD per CONST-XII — each step RED→GREEN with pasted evidence)
1. P1 durable-exec helper in `containers` + wire `run_all_challenges.sh`/`deploy-remote.sh`.
2. P2 egress diagnosis + VPN-host tunnel helper in `containers` + `scripts/egress-via-vpn.sh`.
3. P3 `BOBA_UPSTREAM_PROXY` in `download-proxy` + `qBitTorrent-go` + Jackett + compose env-forward.
4. P4 Jackett cookie-login + fake-equivalence test.
5. Re-run `run_all_challenges.sh` from the VPN-routed host → real tracker search→download evidence.

> Source playbook (full root-cause detail + Lava code refs): `Lava:docs/autonomous-qa/PORTING-PLAYBOOK.md`. Each P-item there has the exact mechanism + the falsifiability rehearsal to replicate under Boba-Base's CONST-XII.
