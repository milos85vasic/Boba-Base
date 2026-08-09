import os
import subprocess

import pytest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SITE_DIR = os.path.join(REPO_ROOT, "website", "site")


def _mkdocs_available() -> bool:
    try:
        subprocess.run(
            ["mkdocs", "--version"],
            capture_output=True,
            timeout=10,
        )
        return True
    except FileNotFoundError:
        return False


@pytest.mark.skipif(  # SKIP-OK: intentional — real `mkdocs --version` invocation, not presence-only
    not _mkdocs_available(), reason="mkdocs not installed"
)
def test_mkdocs_build_succeeds():
    result = subprocess.run(
        ["mkdocs", "build"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"mkdocs build failed (exit {result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


@pytest.mark.skipif(  # SKIP-OK: intentional — real `mkdocs --version` invocation, not presence-only
    not _mkdocs_available(), reason="mkdocs not installed"
)
def test_mkdocs_build_produces_site():
    subprocess.run(
        ["mkdocs", "build"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    assert os.path.isdir(SITE_DIR), f"site directory not found at {SITE_DIR}"
    index_html = os.path.join(SITE_DIR, "index.html")
    assert os.path.isfile(index_html), f"index.html not found at {index_html}"
