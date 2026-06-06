"""Tests for plugins/novaprinter.py — pure parsing functions, no I/O."""

import os
import sys

_PLUGINS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "plugins"))
if _PLUGINS not in sys.path:
    sys.path.insert(0, _PLUGINS)

from novaprinter import anySizeToBytes


class TestAnySizeToBytes:
    def test_int_passthrough(self):
        assert anySizeToBytes(1024) == 1024

    def test_float_rounds(self):
        assert anySizeToBytes(1024.7) == 1025
        assert anySizeToBytes(1024.2) == 1024

    def test_unmatched_string_returns_minus_one(self):
        assert anySizeToBytes("not a size") == -1
        assert anySizeToBytes("") == -1
        assert anySizeToBytes("abc123") == -1

    def test_bytes_no_unit(self):
        assert anySizeToBytes("1024") == 1024
        assert anySizeToBytes("0") == 0

    def test_kilobytes(self):
        assert anySizeToBytes("1 KB") == 1024
        assert anySizeToBytes("2 KB") == 2048
        assert anySizeToBytes("1.5 KB") == 1536

    def test_megabytes(self):
        assert anySizeToBytes("1 MB") == 1048576
        assert anySizeToBytes("10 MB") == 10485760

    def test_gigabytes(self):
        assert anySizeToBytes("1 GB") == 1073741824
        assert anySizeToBytes("2.5 GB") == 2684354560

    def test_terabytes(self):
        assert anySizeToBytes("1 TB") == 1099511627776

    def test_case_insensitive_unit(self):
        assert anySizeToBytes("1 kb") == 1024
        assert anySizeToBytes("1 mb") == 1048576

    def test_size_with_spaces(self):
        assert anySizeToBytes("  1024  ") == 1024
        assert anySizeToBytes("  1  GB  ") == 1073741824

    def test_zero_size(self):
        assert anySizeToBytes("0 KB") == 0
        assert anySizeToBytes("0") == 0
