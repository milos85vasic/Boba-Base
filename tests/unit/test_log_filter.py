"""
Unit tests for config/log_filter.py — no mocks, real data only.
"""

import importlib.util
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")

# Load the module
_log_filter_spec = importlib.util.spec_from_file_location(
    "config.log_filter", os.path.join(_SRC_PATH, "config", "log_filter.py"),
)
_log_filter_mod = importlib.util.module_from_spec(_log_filter_spec)
sys.modules["config.log_filter"] = _log_filter_mod
_log_filter_spec.loader.exec_module(_log_filter_mod)

CredentialScrubber = _log_filter_mod.CredentialScrubber


class TestCredentialScrubber:
    def test_scrubs_password(self):
        import logging

        f = CredentialScrubber()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="PASSWORD=supersecret", args=None, exc_info=None,
        )
        assert f.filter(record)
        assert "supersecret" not in record.msg
        assert "***" in record.msg
        assert record.msg.startswith("PASSWORD")

    def test_scrubs_api_key(self):
        import logging

        f = CredentialScrubber()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="API_KEY=abc123", args=None, exc_info=None,
        )
        assert f.filter(record)
        assert "abc123" not in record.msg
        assert "***" in record.msg

    def test_scrubs_token_colon(self):
        import logging

        f = CredentialScrubber()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="TOKEN: my-secret-token", args=None, exc_info=None,
        )
        assert f.filter(record)
        assert "my-secret-token" not in record.msg
        assert "***" in record.msg

    def test_scrubs_cookie(self):
        import logging

        f = CredentialScrubber()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="COOKIE=abc123; path=/", args=None, exc_info=None,
        )
        assert f.filter(record)
        assert "abc123" not in record.msg
        assert "***" in record.msg

    def test_passes_through_safe_message(self):
        import logging

        f = CredentialScrubber()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="Downloaded 5 torrents", args=None, exc_info=None,
        )
        assert f.filter(record)
        assert record.msg == "Downloaded 5 torrents"

    def test_scrubs_multiple_sensitive_values(self):
        import logging

        f = CredentialScrubber()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="USERNAME=admin PASSWORD=secret API_KEY=xyz",
            args=None, exc_info=None,
        )
        assert f.filter(record)
        assert "secret" not in record.msg
        assert "admin" in record.msg
        assert "xyz" not in record.msg
        assert record.msg.count("***") == 2

    def test_handles_non_string_msg(self):
        import logging

        f = CredentialScrubber()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg=12345, args=None, exc_info=None,
        )
        assert f.filter(record)
        assert str(record.msg) == "12345"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
