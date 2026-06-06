"""Test that install-plugin.sh copies JSON config files alongside plugins."""

import os
import subprocess
import sys
import tempfile

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class TestInstallPluginJsonConfig:
    @staticmethod
    def _engines_dir(home: str) -> str:
        """Return the engines directory for the current platform,
        matching install-plugin.sh logic."""
        if sys.platform == "darwin":
            return os.path.join(home, "Library", "Application Support", "qBittorrent", "nova3", "engines")
        return os.path.join(home, ".local", "share", "qBittorrent", "nova3", "engines")

    def test_installs_jackett_json(self):
        """Installing jackett should copy both jackett.py and jackett.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engines_dir = self._engines_dir(tmpdir)
            os.makedirs(engines_dir, exist_ok=True)

            subprocess.run(
                ["bash", os.path.join(_REPO_ROOT, "install-plugin.sh"), "--local", "jackett"],
                capture_output=True,
                text=True,
                cwd=_REPO_ROOT,
                env={**os.environ, "HOME": tmpdir},
            )

            assert os.path.isfile(os.path.join(engines_dir, "jackett.py"))
            assert os.path.isfile(os.path.join(engines_dir, "jackett.json"))

    def test_installs_kinozal_json(self):
        """Installing kinozal should copy both kinozal.py and kinozal.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engines_dir = self._engines_dir(tmpdir)
            os.makedirs(engines_dir, exist_ok=True)

            subprocess.run(
                ["bash", os.path.join(_REPO_ROOT, "install-plugin.sh"), "--local", "kinozal"],
                capture_output=True,
                text=True,
                cwd=_REPO_ROOT,
                env={**os.environ, "HOME": tmpdir},
            )

            assert os.path.isfile(os.path.join(engines_dir, "kinozal.py"))
            assert os.path.isfile(os.path.join(engines_dir, "kinozal.json"))

    def test_installs_nnmclub_json(self):
        """Installing nnmclub should copy both nnmclub.py and nnmclub.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engines_dir = self._engines_dir(tmpdir)
            os.makedirs(engines_dir, exist_ok=True)

            subprocess.run(
                ["bash", os.path.join(_REPO_ROOT, "install-plugin.sh"), "--local", "nnmclub"],
                capture_output=True,
                text=True,
                cwd=_REPO_ROOT,
                env={**os.environ, "HOME": tmpdir},
            )

            assert os.path.isfile(os.path.join(engines_dir, "nnmclub.py"))
            assert os.path.isfile(os.path.join(engines_dir, "nnmclub.json"))
