"""
Shared environment variable loader.

Single implementation used by plugins and the merge service.
Search order: os.environ → ./env file paths
"""

import os
import sys


def load_env_files(*extra_paths: str):
    """Load .env-style files into os.environ (first wins, no overrides)."""
    default_paths = [
        "/config/.env",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"),
        os.path.expanduser("~/.qbit.env"),
        "/root/.qbit.env",
    ]
    for path in list(extra_paths) + default_paths:
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip('"').strip("'")
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception as exc:
                # §11.4.252(3): a partially-read .env leaves earlier keys applied
                # and silently drops the rest. Never swallow the reason -- a
                # downstream "credentials not configured" warning would otherwise
                # misname a corrupt/unreadable file as an absent one.
                # Non-fatal by design: this loader runs at nova3 plugin-import
                # time, so raising here would break plugin loading entirely. The
                # credential precondition itself still fails closed downstream
                # (rutracker sentinel check, iptorrents._login guard).
                print(
                    f"env_loader: failed to read {path}: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )


def get_env(key: str, default: str = "") -> str:
    """Get env var, loading from .env files if not already set."""
    val = os.environ.get(key)
    if val is None:
        load_env_files()
        val = os.environ.get(key, default)
    return val
