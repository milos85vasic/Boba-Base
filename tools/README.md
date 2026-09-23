# tools/ — Developer Tooling

Standalone developer scripts that do **not** run inside a container
and are not invoked by the normal start/stop flow. Each script here
is independently runnable from a host Python 3.12.

## Scripts

| Script | What it does |
|---|---|
| `plugin_update_automation.py` | Checks upstream repositories for newer versions of each plugin in `plugins/`, optionally downloads + validates + backs up + installs them, and produces an update report. Supports `--check`, `--update`, and `--dry-run`. |

### `plugin_update_automation.py`

Usage:

```bash
# Check without mutating anything
python3 tools/plugin_update_automation.py --check

# Update plugins in place (creates backups under plugins/.backups/)
python3 tools/plugin_update_automation.py --update

# Preview updates without writing anything
python3 tools/plugin_update_automation.py --update --dry-run
```

The script validates each downloaded plugin with `python3 -m py_compile`
before installing it (constitution Principle II). If validation fails,
nothing is written -- the update is refused before any file is touched.
Once validation and the pinned-hash check both pass, the new content is
written to a private temp file and renamed onto the target atomically,
so the existing plugin is never truncated in place; a write failure
after that point leaves the previous plugin file completely untouched
(no separate restore step is needed). A timestamped `.bak` copy of the
previous file is still created under `plugins/.backups/` before every
update, purely for manual recovery/diffing. Reports are written as JSON
to the `--output` file (`plugin_update_report.json` by default), not to
stdout; stdout only gets a short human-readable summary and a
confirmation line naming where the report was saved.

## Adding a new tool

1. Drop a standalone Python 3.12 script in this directory.
2. Shebang (`#!/usr/bin/env python3`) and a docstring describing the
   intended invocation at the top.
3. No external dependencies beyond `requirements.txt` — any extra
   library must be added to `download-proxy/requirements.txt` so the
   container can share it.
4. Add a row to the table above.
5. If the tool is worth running in CI, wire it into the appropriate
   workflow under `.github/workflows/`.

## Conventions

- Pure Python 3.12 — no shell wrappers in this directory (those live
  at the repo root: `start.sh`, `stop.sh`, `setup.sh`, `ci.sh`).
- No network calls during import; network only happens inside `main()`
  so the script is safe to import for unit testing.
- Console progress/status messages go to stdout; structured JSON
  reports are written to a file (see each tool's own usage section
  for the exact flag/default path), not printed to stdout.

## Tests

- `tools/` has no dedicated test suite. If a tool becomes load-bearing,
  add tests under `tests/unit/` that import it directly.

## Gotchas

- Scripts here run on the **host**, so they see the host's Python,
  not the container's. Beware version drift.
- `plugin_update_automation.py` hits upstream URLs; run with care on
  metered connections and respect the retry budget inside the script.
- `__pycache__` in this directory is gitignored but will be recreated
  on every run — delete it manually if a stale import surfaces.
