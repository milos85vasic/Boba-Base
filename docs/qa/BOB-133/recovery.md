# BOB-133 fleet recovery evidence

## Recovery command
```
bash ./start.sh --recreate
```

## Post-recovery port check
```
0.0.0.0:7186
0.0.0.0:7187
*:7185
*:7189
*:9117
```

## Live probe evidence
```
HTTP 200 /api/v1/stats
HTTP 200 POST /api/v1/search
response body:
{"search_id":"d78e9692-4134-42a6-9b90-2edc5bb219be","query":"bob133_recovery","status":"running","results":[],"total_results":0,"merged_results":0,"trackers_searched":["rutracker","kinozal","nnmclub","iptorrents","jackett","academictorrents","ali213","anilibra","audiobookbay","bitru","bitsearch","bt```
