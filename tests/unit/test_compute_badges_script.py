"""Tests for scripts/compute-badges.sh (BOB-118, §11.4.259, §11.4.115 polarity).

The paired golden-good/golden-bad pair required by §1.1: the "--check"
mode must PASS (exit 0) against a freshly-regenerated README, and it must
FAIL (exit non-zero) against a README a real count has drifted away from
— proving the guard genuinely detects the class of bug BOB-118 reports,
not merely that the script runs without crashing.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "compute-badges.sh"


@pytest.fixture
def script_content():
    return SCRIPT.read_text()


class TestComputeBadgesScriptExists:
    def test_script_file_exists(self):
        assert SCRIPT.is_file(), f"{SCRIPT} does not exist"

    def test_script_is_executable(self):
        assert os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable"

    def test_script_syntax_valid(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_has_strict_mode(self, script_content):
        assert "set -euo pipefail" in script_content


class TestComputeBadgesNoFabrication:
    """§11.4.6 — an unmeasurable count must degrade to an honest N/A,
    never a fabricated or carried-forward number."""

    def test_never_hardcodes_the_stale_bob118_numbers(self, script_content):
        # The exact stale badge-URL fragments BOB-118 reported must never
        # be emitted as a literal fallback/default anywhere in the
        # generator's OUTPUT-producing code. (The provenance note text the
        # script writes into docs/TESTING.md is allowed to CITE "585" as
        # history — that is a documentation string, not a computed value,
        # so this checks the shields.io URL fragment specifically.)
        assert "python%20tests-585" not in script_content
        assert "frontend%20tests-182" not in script_content

    def test_has_na_fallback_path(self, script_content):
        assert "NA|" in script_content, (
            "compute-badges.sh must emit an honest NA sentinel when a "
            "count genuinely cannot be computed (§11.4.6)"
        )


@pytest.mark.timeout(240)
class TestComputeBadgesCheckModePolarity:
    """The §1.1 paired mutation: golden-good (in-sync fixture) passes,
    golden-bad (a real BOB-118-shaped drift) fails.

    Task #110 (BOB-130) verified: the function-scoped ``synced_fixtures``
    fixture shells out ``scripts/compute-badges.sh`` full-regeneration
    (~93s CPU-bound) once per test method in this class (3 methods), which
    exceeds the project's ``--timeout=60`` default (pyproject.toml) even
    though each individual invocation stays under its own 180s subprocess
    timeout. 240s covers the 3x93s=~279s worst case with margin while
    preserving the 60s default for every other test in the suite. See
    .superpowers/sdd/task7-badge-timeout-verification.md.
    """

    @pytest.fixture
    def synced_fixtures(self):
        """Golden-good: regenerate real README/TESTING.md copies into a
        scratch dir, so --check compares against genuinely fresh counts.
        Function-scoped deliberately (a class-scoped generator fixture
        here trips a pytest fixture-finalizer-ordering assertion on this
        project's pinned pytest version — `assert not self._finalizers` in
        `_pytest/fixtures.py` — so each test pays its own ~10-20s
        regeneration cost rather than fighting that scope interaction).
        Uses a plain `tempfile` directory, not the built-in `tmp_path`
        fixture, to keep the fixture self-contained."""
        with tempfile.TemporaryDirectory(prefix="compute_badges_fixture_") as d:
            tmp_dir = Path(d)
            readme_src = ROOT / "README.md"
            testing_src = ROOT / "docs" / "TESTING.md"
            readme = tmp_dir / "README.md"
            testing = tmp_dir / "TESTING.md"
            readme.write_text(readme_src.read_text())
            testing.write_text(testing_src.read_text())

            subprocess.run(
                [str(SCRIPT), "--readme", str(readme), "--testing-md", str(testing)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
            yield readme, testing

    def test_golden_good_freshly_regenerated_readme_is_in_sync(self, synced_fixtures):
        readme, testing = synced_fixtures
        result = subprocess.run(
            [str(SCRIPT), "--check", "--readme", str(readme), "--testing-md", str(testing)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, (
            f"a freshly-regenerated README must report in-sync, got exit "
            f"{result.returncode}: {result.stdout}\n{result.stderr}"
        )
        assert "in sync" in result.stdout

    def test_golden_bad_stale_python_count_is_detected(self, synced_fixtures):
        readme, testing = synced_fixtures
        content = readme.read_text()
        # Reproduce the exact BOB-118 shape: mutate the live-computed
        # python-tests badge number down to a stale, unrelated value —
        # the class of drift the whole mechanism exists to catch.
        mutated = content.replace(
            "python%20tests-", "python%20tests-999999%20mutated-"
        )
        assert mutated != content, "fixture mutation did not change anything — test is broken"

        # Mutate a PRIVATE copy — the class-scoped fixture is shared with
        # the other polarity assertions and must stay in its golden-good
        # state for them.
        with tempfile.TemporaryDirectory(prefix="compute_badges_mutant_") as d:
            mutated_readme = Path(d) / "README-mutated.md"
            mutated_readme.write_text(mutated)

            result = subprocess.run(
                [str(SCRIPT), "--check", "--readme", str(mutated_readme), "--testing-md", str(testing)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=180,
            )
        assert result.returncode == 2, (
            f"a mutated/stale badge must be detected as STALE (exit 2), got "
            f"exit {result.returncode}: {result.stdout}\n{result.stderr}"
        )
        assert "STALE" in result.stdout

    def test_check_mode_never_writes_to_disk(self, synced_fixtures):
        readme, testing = synced_fixtures
        before_readme = readme.read_text()
        before_testing = testing.read_text()
        subprocess.run(
            [str(SCRIPT), "--check", "--readme", str(readme), "--testing-md", str(testing)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert readme.read_text() == before_readme, "--check must not modify the README"
        assert testing.read_text() == before_testing, "--check must not modify TESTING.md"
