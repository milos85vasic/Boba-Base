# Coverage Baseline

**Revision:** 1
**Last modified:** 2026-06-06T00:00:00Z

Last updated at commit `da7da4a` on 2026-04-22 (Phase 10 verification).

## Summary

| Metric | Value |
|--------|-------|
| **Total coverage** | **49%** |
| **Total statements** | 5,683 |
| **Missing lines** | 2,708 |
| **Branches (partial)** | 102 |
| **Unit tests passing** | 1,118 |
| **Coverage gate (`fail_under`)** | 49 |

## By Module — Core (download-proxy/src)

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|-------|------|--------|--------|-------|
| `api/__init__.py` | 118 | 26 | 22 | 2 | 76% |
| `api/auth.py` | 203 | 85 | 50 | 2 | 57% |
| `api/hooks.py` | 107 | 59 | 14 | 0 | 40% |
| `api/routes.py` | 450 | 174 | 126 | 13 | 57% |
| `api/scheduler.py` | 59 | 2 | 14 | 4 | 92% |
| `api/streaming.py` | 115 | 9 | 40 | 2 | 93% |
| `api/theme_state.py` | 100 | 19 | 12 | 0 | 81% |
| `config/__init__.py` | 49 | 1 | 2 | 1 | 96% |
| `config/log_filter.py` | 7 | 2 | 0 | 0 | 71% |
| `main.py` | 56 | 26 | 6 | 1 | 50% |
| `merge_service/deduplicator.py` | 240 | 23 | 118 | 16 | 89% |
| `merge_service/enricher.py` | 166 | 10 | 62 | 10 | 91% |
| `merge_service/hooks.py` | 106 | 5 | 26 | 1 | 95% |
| `merge_service/retry.py` | 3 | 0 | 0 | 0 | 100% |
| `merge_service/scheduler.py` | 125 | 27 | 20 | 4 | 74% |
| `merge_service/search.py` | 784 | 162 | 230 | 28 | 77% |
| `merge_service/validator.py` | 202 | 61 | 58 | 3 | 68% |

## By Module — Plugins (plugins/)

| Plugin | Stmts | Miss | BrPart | Cover |
|--------|-------|------|--------|-------|
| `community/anilibra.py` | 56 | 32 | 0 | 35% |
| `community/yourbittorrent.py` | 47 | 15 | 2 | 58% |
| `download_proxy.py` | 278 | 163 | 1 | 40% |
| `env_loader.py` | 22 | 7 | 0 | 74% |
| `eztv.py` | 37 | 18 | 0 | 46% |
| `helpers.py` | 89 | 59 | 0 | 27% |
| `iptorrents.py` | 133 | 107 | 0 | 15% |
| `kinozal.py` | 209 | 125 | 3 | 35% |
| `limetorrents.py` | 154 | 127 | 0 | 13% |
| `nnmclub.py` | 209 | 129 | 3 | 34% |
| `nova2.py` | 79 | 79 | 0 | 0% |
| `novaprinter.py` | 24 | 17 | 0 | 22% |
| `nyaa.py` | 103 | 84 | 0 | 13% |
| `piratebay.py` | 83 | 60 | 0 | 24% |
| `rutor.py` | 192 | 131 | 1 | 27% |
| `rutracker.py` | 219 | 157 | 2 | 25% |
| `socks.py` | 444 | 354 | 2 | 16% |
| `solidtorrents.py` | 124 | 105 | 0 | 12% |
| `theme_injector.py` | 98 | 98 | 0 | 0% |
| `torrentgalaxy.py` | 94 | 71 | 0 | 17% |
| `yts.py` | 99 | 79 | 1 | 16% |

## Coverage Gate History

| Phase | `fail_under` | Notes |
|-------|-------------|-------|
| Phase 0 | 1% | Baseline |
| Phase 10 | 49% | Raised to actual measured coverage |

## Measurement Method

```bash
python3 -m pytest tests/unit/ --import-mode=importlib \
  --cov=download-proxy/src --cov=plugins \
  --cov-report=term-missing --cov-report=xml
```

Unit tests only (integration/e2e tests require running containers and are not included in baseline).
