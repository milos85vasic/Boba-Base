"""Verify that CI/CD workflow files have been permanently removed from the
repository per the Hard Stop rule (no CI/CD pipelines).

All GitHub Actions workflows were removed from .github/workflows/ as
mandated by the Hard Stop rule. These tests ensure the absence is
maintained and no workflow files are reintroduced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
DOTGITHUB_DIR = REPO_ROOT / ".github"


def test_no_workflows_directory() -> None:
    assert not WORKFLOW_DIR.exists(), (
        f".github/workflows/ still exists at {WORKFLOW_DIR} — "
        "all CI/CD workflow files must be removed per Hard Stop rule"
    )


def test_no_workflow_files_in_dotgithub() -> None:
    if not DOTGITHUB_DIR.exists():
        return
    workflow_files = [p for p in DOTGITHUB_DIR.rglob("*") if p.suffix in {".yml", ".yaml"}]
    assert not workflow_files, (
        f"Found unexpected CI/CD workflow file(s) in .github/: "
        f"{[str(p.relative_to(REPO_ROOT)) for p in workflow_files]}"
    )


def test_hard_stop_compliance() -> None:
    no_pipelines_patterns = [
        ".github/workflows/",
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
    ]
    for pattern in no_pipelines_patterns:
        matches = list(REPO_ROOT.glob(pattern))
        assert not matches, (
            f"Hard Stop violation: found {matches} matching {pattern!r}"
        )
