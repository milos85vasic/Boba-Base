# Deselected from the live run: `tests/integration/test_start_sh_reload_paths.py`

Excluded via `--ignore=tests/integration/test_start_sh_reload_paths.py` because it
DRIVES THE OPERATOR'S RUNNING STACK, which this session is forbidden from disturbing.

Evidence (read from the file, not inferred):

- `test_recreate_stack_destroys_and_recreates_container` (line 239) runs
  `./start.sh --recreate`, which per `CLAUDE.md` is `<compose> down && <compose> up -d`
  — a full TEARDOWN of the stack. Its own assertion is that the container **id changes**,
  i.e. it requires the destroy to happen.
- `test_reload_python_clears_pycache_and_restarts` (line 139) and
  `test_reload_plugins_restarts_without_copying_files` (line 191) run
  `./start.sh --reload-python` / `--reload-plugins`, each of which restarts the
  `qbittorrent-proxy` container (their assertions require `StartedAt` to move forward).

All three are legitimate tests of a real contract; they are simply UNSAFE to run while
the operator and other work streams are using the live stack. They were NOT run and are
therefore NOT counted as passing in the live results.

Everything else in `tests/integration` and `tests/e2e` was run. `tests/conftest.py`
`docker_cleanup()` returns `[]` (verified) and `tests/fixtures/compose.py::compose_up`
only issues `compose up -d` when ports are NOT already listening (they were), so no other
collected test tears the stack down.
