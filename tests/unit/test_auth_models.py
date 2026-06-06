"""Tests for download-proxy/src/api/auth.py — Pydantic models only."""

import sys
import os

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SRC = os.path.join(_REPO, "download-proxy", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from pydantic import ValidationError
import pytest

from api.auth import CaptchaLoginRequest, CookieLoginRequest


class TestCaptchaLoginRequest:
    def test_valid(self):
        r = CaptchaLoginRequest(cap_sid="sid123", cap_code_field="cap_code_abc", captcha_text="ABC123", captcha_token="tok_xyz")
        assert r.cap_sid == "sid123"
        assert r.cap_code_field == "cap_code_abc"
        assert r.captcha_text == "ABC123"
        assert r.captcha_token == "tok_xyz"

    def test_missing_field(self):
        with pytest.raises(ValidationError):
            CaptchaLoginRequest(cap_sid="sid123")


class TestCookieLoginRequest:
    def test_valid(self):
        r = CookieLoginRequest(cookie_string="bb_session=abc123; t=xyz")
        assert r.cookie_string == "bb_session=abc123; t=xyz"

    def test_missing_field(self):
        with pytest.raises(ValidationError):
            CookieLoginRequest()
