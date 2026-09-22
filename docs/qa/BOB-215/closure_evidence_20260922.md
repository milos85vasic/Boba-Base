# BOB-215 closure evidence — 2026-09-22

## Fix

`cmd/boba-ctl/main.go`:
- `authMethod()` (line ~498) default branch now returns `("", error)` naming
  both the config key (`"auth"`) and the declared bad value, instead of
  silently resolving to `remote.AuthSSHKey`.
- `toRemoteHost()` (line ~523) propagates the error, wrapped with the host
  name.
- `cmdDeploy()` (line ~573) handles the new error return, prints it, and
  exits non-zero rather than proceeding with a credential mechanism the
  operator never actually declared.

## RED evidence (pre-fix)

A temporary test asserted the defect against unfixed code:
```
=== RUN   TestAuthMethod_BOB215_PreFixRedEvidence
    deploy_test.go:114: BOB-215 CONFIRMED: unrecognised/empty auth value silently resolves to "ssh_key"
--- PASS: TestAuthMethod_BOB215_PreFixRedEvidence (0.00s)
```
(the PASS proves the bug: `authMethod("totally-not-a-real-auth-method")` and
`authMethod("")` both silently returned `AuthSSHKey`).

## GREEN + golden-FALSE evidence (independently re-verified this session)

```
$ cd cmd/boba-ctl && go build ./... && go test ./... -v
=== RUN   TestFindDeployHost_NotFound
--- PASS: TestFindDeployHost_NotFound (0.00s)
=== RUN   TestDeployHost_ToRemoteHost
--- PASS: TestDeployHost_ToRemoteHost (0.00s)
=== RUN   TestDeployHost_ToRemoteHost_InvalidAuthRefuses
--- PASS: TestDeployHost_ToRemoteHost_InvalidAuthRefuses (0.00s)
=== RUN   TestAuthMethod_LegitimateValuesResolve
--- PASS: TestAuthMethod_LegitimateValuesResolve (0.00s)
=== RUN   TestAuthMethod_UnrecognisedValueRefuses
--- PASS: TestAuthMethod_UnrecognisedValueRefuses (0.00s)
[... 10 more pre-existing tests, all PASS ...]
PASS
ok  	github.com/milos85vasic/qbittorrent/cmd/boba-ctl	0.007s
```
15/15 PASS, `go build ./...` and `go vet ./...` both clean.

`TestAuthMethod_LegitimateValuesResolve` covers every recognised value
(`key`/`ssh_key`/`ssh-key` → AuthSSHKey; `agent`/`ssh_agent`/`ssh-agent` →
AuthSSHAgent; `password` → AuthPassword) plus case/whitespace variants — all
resolve with no error, proving the fix introduces no false refusal.
`TestAuthMethod_UnrecognisedValueRefuses` drives 5 bad values and asserts
each refuses with an error naming both the config key and the bad value.

## git diff --stat

```
cmd/boba-ctl/deploy_test.go | 87 ++++++++++++++++++++++++++++++++++++++++-----
cmd/boba-ctl/main.go        | 38 ++++++++++++++------
2 files changed, 107 insertions(+), 18 deletions(-)
```
