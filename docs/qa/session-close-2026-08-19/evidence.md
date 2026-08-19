# Session-close release-readiness evidence — 2026-08-19

## Uptime + host stability
 20:24:40 up  5:17,  2 users,  load average: 1.58, 2.10, 3.13

## All 3 remotes
- origin: 184c400ec6d2a49bbd326b08d6c92eefea42a76b
- github: 184c400ec6d2a49bbd326b08d6c92eefea42a76b
- upstream: 184c400ec6d2a49bbd326b08d6c92eefea42a76b

## Container fleet
proxy-redis        Up 4 hours (healthy)
proxy-postgres     Up 4 hours (healthy)
proxy-gluetun      Up 4 hours (healthy)
proxy-healthd      Up 4 hours
proxy-squid        Up 4 hours (healthy)
qbittorrent        Up 36 minutes (healthy)
jackett            Up 36 minutes (healthy)
boba-jackett       Up 35 minutes (healthy)
qbittorrent-proxy  Up 35 minutes (healthy)

## Live service probes
- merge_service /api/v1/stats: HTTP 200
- boba-jackett /healthz: HTTP 200
- qbittorrent WebUI: HTTP 200
- jackett: HTTP 301

## BOB-129 fix live-verified (real POST /search)
```
```

## Commits landed this session (25-branch base 12b439b → HEAD)
47
commits since branch base

## Latest 10
184c400 docs(qa,db-delta): capture differential dump for HEAD d9955d6
d9955d6 docs(db): BOB-127/128/129/130/131/132/133/135 registered/closed + regen exports
091a208 fix(BOB-130): raise timeout for TestComputeBadgesCheckModePolarity (93s CPU-bound fixture)
471bd03 test(warnings): add error::ResourceWarning permanent filter (Task 7 followup)
97a4dca fix(tests): BOB-129 fallout — pass Response as 3rd arg to _search_impl
e141d5b test(BOB-129): capture before/after evidence for slowapi production fix
44f3bbe fix(BOB-129): apply slowapi Option A fix to production endpoints
101adbb docs(qa,db-delta): capture differential dump for HEAD 81c4c0a
81c4c0a docs(db): register BOB-129 CRITICAL — production slowapi/starlette defect (Task 105 escape)
b8fdc9c fix(tests): narrow 2 remaining broad except Exception in conftest.py (Task #107)

## BOB-129 fix — corrected live-verify (POST with proper headers)
```
--- HEADERS ---
HTTP/1.1 200 OK
date: Wed, 19 Aug 2026 18:25:06 GMT
server: uvicorn
content-length: 13574
content-type: application/json
x-ratelimit-limit: 10
x-ratelimit-remaining: 9
x-ratelimit-reset: 1787163968.3163579
retry-after: 60

--- BODY ---
{"search_id":"f7c86912-b236-4d1c-b3c7-2908172a02f8","query":"session_close_probe","status":"running","results":[],"total_results":0,"merged_results":0,"trackers_searched":["rutracker","kinozal","nnmcl```
