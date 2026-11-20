import json
import logging
import os
import sys
import threading

_src = os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from api.routes import _save_qbit_credentials
from config.log_filter import CredentialScrubber


class TestCredentialFileSafety:
    def test_file_mode_is_restrictive(self, tmp_path):
        creds_file = str(tmp_path / "qbittorrent_creds.json")
        _save_qbit_credentials(
            creds_file,
            {"username": "admin", "password": "admin"},
        )
        mode = os.stat(creds_file).st_mode & 0o777
        assert mode == 0o600, f"credential file mode must be 0o600, got 0o{mode:o}"

    def test_concurrent_writes_no_corruption(self, tmp_path):
        creds_file = str(tmp_path / "qbittorrent_creds.json")
        errors: list[str] = []
        num_writers = 50

        def writer(idx: int):
            try:
                _save_qbit_credentials(
                    creds_file,
                    {"username": f"user_{idx}", "password": f"pass_{idx}"},
                )
            except Exception as e:
                errors.append(f"writer {idx}: {e}")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(num_writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Errors during concurrent writes: {errors}"

        with open(creds_file) as f:
            data = json.load(f)

        assert "username" in data
        assert "password" in data
        assert data["username"].startswith("user_")
        assert data["password"].startswith("pass_")

    def test_saved_password_not_logged_plaintext(self, tmp_path, caplog):
        """_save_qbit_credentials may log errors, but the password must not
        appear in any log record in plaintext."""
        creds_file = str(tmp_path / "qbittorrent_creds.json")
        secret = "super-secret-qbit-pass-123"
        _save_qbit_credentials(
            creds_file,
            {"username": "admin", "password": secret},
        )

        for record in caplog.records:
            assert secret not in record.getMessage(), "password leaked into logs"

    def test_credential_scrubber_redacts_qbittorrent_password(self):
        scrubber = CredentialScrubber()
        secret = "qbittorrent-password-xyz"
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=f"Saved qBittorrent credentials: password={secret}",
            args=None,
            exc_info=None,
        )
        scrubber.filter(record)
        assert secret not in record.getMessage()
        assert "password=***" in record.getMessage()
