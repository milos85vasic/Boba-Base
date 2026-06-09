# Coverage Baseline

**Revision:** 3
**Last modified:** 2026-06-09T12:00:00Z

Last updated at commit `HEAD` on 2026-06-09 (search.py 84%, plugin coverage push, BOB-015 fixes).

## Summary

| Metric | Value |
|--------|-------|
| **Total coverage** | **65%** |
| **Total statements** | 6,821 |
| **Missing lines** | 2,264 |
| **Branches (partial)** | 122 |
| **Unit tests passing** | 1,802+ |
| **Coverage gate (`fail_under`)** | 49 |

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
| `merge_service/search.py` | 965 | 143 | 294 | 23 | 84% |
| `merge_service/validator.py` | 205 | 13 | 60 | 1 | 92% |

## Coverage Gate History

| Phase | `fail_under` | Notes |
|-------|-------------|-------|
| Phase 0 | 1% | Baseline |
| Phase 10 | 49% | Raised to actual measured coverage |
| Phase 11 | 49% | routes.py 95%, search.py 80%, validator 92%, jackett_autoconfig 99% |
| Phase 12 | 49% | search.py 84%, theme_injector 99%, env_loader 100%, yts/piratebay JSON guards |

## Measurement Method

```bash
python3 -m pytest tests/unit/ --import-mode=importlib \
  --cov=download-proxy/src --cov=plugins \
  --cov-report=term-missing --cov-report=xml
```

Unit tests only (integration/e2e tests require running containers and are not included in baseline).
