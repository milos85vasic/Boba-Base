# BOB-089 — QA evidence

RED-first regression suite for `start.sh --reload-python | --reload-plugins | --recreate`.

- Suite: `tests/integration/test_start_sh_reload_paths.py`
- Contract per subcommand: see file docstring (mirrors CLAUDE.md "Pick the right restart level").
- §11.4.115(F) — verdicts read from the target at run time (podman inspect + container marker files).
- §11.4.161 — rootless podman auto-detected same way `start.sh` does.

## RED — `RED_reload_python_stub.log`

`reload_python()`'s `find … -exec rm -rf` line replaced with `echo "MUTATION-BOB089: cache clear skipped"`. The test FAILs with:

    AssertionError: __pycache__ still exists after --reload-python — cache-clear step did not run

That is the exact contract-violation the mutation induces — the guard is not a tautology.

## GREEN — `GREEN_all_three.log`

Mutation reverted. All three tests PASS on the real running fleet (podman, qbittorrent-proxy healthy):

    test_reload_plugins_restarts_without_copying_files PASSED
    test_recreate_stack_destroys_and_recreates_container PASSED
    test_reload_python_clears_pycache_and_restarts PASSED
    3 passed in 105.00s

Discriminators the tests observe:

* `--reload-python` → marker `__pycache__` removed AND `StartedAt` bumped AND container id UNCHANGED (restart, not recreate).
* `--reload-plugins` → `StartedAt` bumped AND id UNCHANGED AND `plugins/bob089_reload_plugins_marker.py` NOT auto-copied into `config/qBittorrent/nova3/engines/` (that's `./install-plugin.sh`'s job).
* `--recreate` → container id CHANGES (destroy + recreate, not a plain restart).
