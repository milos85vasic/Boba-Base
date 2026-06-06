"""Tests for plugins/env_loader.py — pure file/env operations."""

import os
import sys
import tempfile

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PLUGINS_PATH = os.path.join(_REPO_ROOT, "plugins")
if _PLUGINS_PATH not in sys.path:
    sys.path.insert(0, _PLUGINS_PATH)

from env_loader import load_env_files, get_env


class TestLoadEnvFiles:
    def setup_method(self):
        self._saved = os.environ.copy()

    def teardown_method(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def test_load_from_file(self):
        content = "TEST_KEY=test_value\nANOTHER=hello\n# comment\nINVALID_LINE_NO_EQUAL\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("TEST_KEY") == "test_value"
            assert os.environ.get("ANOTHER") == "hello"
        finally:
            os.unlink(path)

    def test_first_wins(self):
        os.environ["EXISTING_KEY"] = "original"
        content = "EXISTING_KEY=overwritten\nNEW_KEY=new_value\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ["EXISTING_KEY"] == "original"
            assert os.environ.get("NEW_KEY") == "new_value"
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        load_env_files("/tmp/nonexistent_file_for_testing_12345.env")
        assert True

    def test_read_error(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("KEY=val\n")
            path = f.name
        os.chmod(path, 0o000)
        try:
            load_env_files(path)
        finally:
            os.chmod(path, 0o644)
            os.unlink(path)

    def test_strips_quotes(self):
        content = 'QUOTED_KEY="quoted_value"\n'
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("QUOTED_KEY") == "quoted_value"
        finally:
            os.unlink(path)


class TestGetEnv:
    def setup_method(self):
        self._saved = os.environ.copy()
        for k in list(os.environ):
            if k.startswith("TEST_GETENV_"):
                del os.environ[k]

    def teardown_method(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def test_get_env_from_env(self):
        os.environ["TEST_GETENV_FOO"] = "from_env"
        assert get_env("TEST_GETENV_FOO") == "from_env"

    def test_get_env_default(self):
        assert get_env("TEST_GETENV_NONEXISTENT", "default_val") == "default_val"

    def test_get_env_empty_default(self):
        result = get_env("TEST_GETENV_NONEXISTENT_EMPTY")
        assert result == ""
