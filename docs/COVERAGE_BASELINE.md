# Coverage Baseline

**Revision:** 5
**Last modified:** 2026-06-09T14:00:00Z

Last updated at commit `HEAD` on 2026-06-09 (search.py 95%, community plugin coverage push, 88% total).

## Summary

| Metric | Value |
|--------|-------|
| **Total coverage** | **88%** |
| **Total statements** | 8,392 |
| **Missing lines** | 946 |
| **Branches (partial)** | 102 |
| **Unit tests passing** | 4,053 (of 4,074 collected) |
| **Unit tests failing** | 21 |
| **Coverage gate (`fail_under`)** | 88 |

## By Module — Core (download-proxy/src)

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|-------|------|--------|--------|-------|
| `api/__init__.py` | 135 | 1 | 26 | 3 | 98% |
| `api/auth.py` | 242 | 19 | 60 | 6 | 91% |
| `api/hooks.py` | 112 | 0 | 16 | 0 | 100% |
| `api/routes.py` | 472 | 18 | 134 | 8 | 95% |
| `api/scheduler.py` | 59 | 0 | 14 | 0 | 100% |
| `api/streaming.py` | 115 | 0 | 40 | 1 | 99% |
| `api/theme_state.py` | 100 | 0 | 12 | 0 | 100% |
| `config/__init__.py` | 49 | 0 | 2 | 0 | 100% |
| `config/log_filter.py` | 7 | 0 | 0 | 0 | 100% |
| `main.py` | 56 | 2 | 6 | 2 | 94% |
| `merge_service/deduplicator.py` | 242 | 14 | 120 | 7 | 94% |
| `merge_service/enricher.py` | 166 | 0 | 62 | 0 | 100% |
| `merge_service/hooks.py` | 106 | 6 | 26 | 0 | 95% |
| `merge_service/jackett_autoconfig.py` | 205 | 1 | 76 | 2 | 99% |
| `merge_service/retry.py` | 3 | 0 | 0 | 0 | 100% |
| `merge_service/scheduler.py` | 126 | 6 | 20 | 2 | 93% |
| `merge_service/search.py` | 965 | 39 | 294 | 15 | 95% |
| `merge_service/validator.py` | 205 | 13 | 60 | 1 | 92% |

## By Module — Plugins (selected)

| Plugin | Stmts | Miss | Branch | BrPart | Cover |
|--------|-------|------|--------|--------|-------|
| `anilibra.py` | 53 | 0 | 12 | 0 | 100% |
| `download_proxy.py` | 328 | 18 | 102 | 5 | 95% |
| `env_loader.py` | 22 | 0 | 12 | 0 | 100% |
| `eztv.py` | 77 | 0 | 18 | 0 | 100% |
| `helpers.py` | 89 | 2 | 22 | 2 | 96% |
| `iptorrents.py` | 133 | 14 | 40 | 2 | 87% |
| `kickass.py` | 74 | 0 | 20 | 0 | 100% |
| `kinozal.py` | 209 | 12 | 60 | 2 | 95% |
| `limetorrents.py` | 154 | 4 | 56 | 3 | 97% |
| `nnmclub.py` | 226 | 15 | 64 | 1 | 94% |
| `nova2.py` | 79 | 79 | 18 | 0 | 0% |
| `nyaa.py` | 104 | 8 | 40 | 1 | 94% |
| `piratebay.py` | 86 | 5 | 12 | 0 | 95% |
| `rutor.py` | 192 | 22 | 38 | 1 | 90% |
| `rutracker.py` | 219 | 31 | 34 | 1 | 87% |
| `socks.py` | 444 | 444 | 142 | 0 | 0% |
| `theme_injector.py` | 129 | 1 | 42 | 1 | 99% |
| `torlock.py` | 80 | 0 | 34 | 2 | 98% |
| `yts.py` | 105 | 31 | 34 | 3 | 70% |
| `community/jackett.py` | 182 | 0 | 54 | 0 | 100% |

## Coverage Gate History

| Phase | `fail_under` | Notes |
|-------|-------------|-------|
| Phase 0 | 1% | Baseline |
| Phase 10 | 49% | Raised to actual measured coverage |
| Phase 11 | 49% | routes.py 95%, search.py 80%, validator 92%, jackett_autoconfig 99% |
| Phase 12 | 49% | search.py 84%, theme_injector 99%, env_loader 100%, yts/piratebay JSON guards |
| Phase 13 | 49% | search.py 95%, total 88%, community plugin coverage sweep |
| Phase 14 | 88% | Gate raised to match actual measured coverage (88.14%) |

## Measurement Method

```bash
python3 -m pytest tests/unit/ --import-mode=importlib \
  --cov=download-proxy/src --cov=plugins \
  --cov-report=term-missing --cov-report=xml
```

Unit tests only (integration/e2e tests require running containers and are not included in baseline).
