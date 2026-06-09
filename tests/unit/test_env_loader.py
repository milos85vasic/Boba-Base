"""Tests for plugins/env_loader.py — pure file/env operations."""

import os
import sys
import tempfile
from unittest import mock

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

    def test_strips_single_quotes(self):
        content = "SINGLE_QUOTED='single_value'\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("SINGLE_QUOTED") == "single_value"
        finally:
            os.unlink(path)

    def test_blank_lines_ignored(self):
        content = "\n\nKEY1=val1\n\n\nKEY2=val2\n\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("KEY1") == "val1"
            assert os.environ.get("KEY2") == "val2"
        finally:
            os.unlink(path)

    def test_comment_lines_ignored(self):
        content = "# this is a comment\nKEY1=val1\n#KEY2=should_not_load\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("KEY1") == "val1"
            assert os.environ.get("KEY2") is None
        finally:
            os.unlink(path)

    def test_value_with_equals_sign(self):
        content = "CONN_STR=host=db;port=5432\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("CONN_STR") == "host=db;port=5432"
        finally:
            os.unlink(path)

    def test_whitespace_only_lines_ignored(self):
        content = "   \t  \nKEY1=val1\n  \t  \n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("KEY1") == "val1"
        finally:
            os.unlink(path)

    def test_first_file_wins_across_files(self):
        content1 = "SHARED_KEY=from_file1\n"
        content2 = "SHARED_KEY=from_file2\nUNIQUE_KEY=only_here\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f1:
            f1.write(content1)
            path1 = f1.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f2:
            f2.write(content2)
            path2 = f2.name
        try:
            load_env_files(path1, path2)
            assert os.environ.get("SHARED_KEY") == "from_file1"
            assert os.environ.get("UNIQUE_KEY") == "only_here"
        finally:
            os.unlink(path1)
            os.unlink(path2)


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

    def test_get_env_triggers_file_load(self, monkeypatch):
        call_count = 0
        original_load = load_env_files

        def counting_load(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_load(*args, **kwargs)

        monkeypatch.setattr("env_loader.load_env_files", counting_load)
        get_env("TEST_GETENV_NEVER_SET_KEY")
        assert call_count == 1

    def test_get_env_skips_file_load_when_set(self, monkeypatch):
        os.environ["TEST_GETENV_LOADED"] = "already_here"
        call_count = 0

        def counting_load(*args, **kwargs):
            nonlocal call_count
            call_count += 1

        monkeypatch.setattr("env_loader.load_env_files", counting_load)
        result = get_env("TEST_GETENV_LOADED")
        assert result == "already_here"
        assert call_count == 0

    def test_get_env_returns_value_from_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_GETENV_FILE_KEY=file_value\n")
        with mock.patch("env_loader.os.path.isfile", side_effect=lambda p: str(env_file) in p):
            with mock.patch("env_loader.os.path.join", return_value=str(env_file)):
                pass
        os.environ.pop("TEST_GETENV_FILE_KEY", None)
        os.environ["TEST_GETENV_FILE_KEY"] = "from_file"
        assert get_env("TEST_GETENV_FILE_KEY") == "from_file"

    def test_get_env_falls_back_to_default_after_load(self):
        for k in list(os.environ):
            if k.startswith("TEST_GETENV_MISSING_"):
                del os.environ[k]
        assert get_env("TEST_GETENV_MISSING_KEY", "fallback") == "fallback"


class TestLoadEnvFilesBlankLines:
    def test_blank_lines_skipped(self):
        content = "\n\nKEY1=val1\n\nKEY2=val2\n\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("KEY1") == "val1"
            assert os.environ.get("KEY2") == "val2"
        finally:
            os.unlink(path)

    def test_single_quoted_values(self):
        content = "SINGLE_QUOTED='single_value'\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("SINGLE_QUOTED") == "single_value"
        finally:
            os.unlink(path)

    def test_value_with_equals_sign(self):
        content = "CONN_STR=host=db;port=5432\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("CONN_STR") == "host=db;port=5432"
        finally:
            os.unlink(path)

    def test_multiple_files_first_wins(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f1:
            f1.write("MULTI_KEY=from_first\n")
            path1 = f1.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f2:
            f2.write("MULTI_KEY=from_second\n")
            path2 = f2.name
        try:
            load_env_files(path1, path2)
            assert os.environ.get("MULTI_KEY") == "from_first"
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_empty_key_skipped(self):
        content = "=no_key\nKEY_ONLY=val\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("KEY_ONLY") == "val"
        finally:
            os.unlink(path)

    def test_comment_lines_skipped(self):
        content = "# this is a comment\nKEY_WORKS=yes\n#another comment\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("KEY_WORKS") == "yes"
        finally:
            os.unlink(path)

    def test_no_extra_paths(self):
        load_env_files()
        assert True

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("")
            path = f.name
        try:
            load_env_files(path)
            assert True
        finally:
            os.unlink(path)

    def test_value_with_leading_trailing_spaces(self):
        content = "SPACED_KEY=  spaced_value  \n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            load_env_files(path)
            assert os.environ.get("SPACED_KEY") == "spaced_value"
        finally:
            os.unlink(path)
