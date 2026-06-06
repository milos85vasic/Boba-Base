#!/usr/bin/env python3
"""Extract the Jackett API key from its ServerConfig.json.

Polls the config file until Jackett has generated a key (first-start
scenario) or returns immediately if one already exists.  Exits with the
key on stdout, or an empty string if the file/key is missing.

Usage:
    export JACKETT_API_KEY=$(python3 scripts/extract-jackett-key.py)
"""

import json
import os
import sys
import time

DEFAULT_CONFIG_PATH = "/config/jackett/Jackett/ServerConfig.json"
FALLBACK_PATH = "./config/jackett/Jackett/ServerConfig.json"
POLL_INTERVAL = float(os.environ.get("JACKETT_POLL_INTERVAL", "2.0"))
POLL_MAX_SECONDS = float(os.environ.get("JACKETT_POLL_MAX_SECONDS", "120.0"))


def find_config_file() -> str | None:
    for path in (DEFAULT_CONFIG_PATH, FALLBACK_PATH):
        if os.path.isfile(path):
            return path
    return None


def extract_key(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    key = data.get("APIKey") if isinstance(data, dict) else None
    if key and isinstance(key, str) and key.strip() and key.strip().lower() != "your_api_key_here":
        return key.strip()
    return None


def main() -> int:
    path = find_config_file()
    elapsed = 0.0

    while True:
        if path is not None:
            key = extract_key(path)
            if key is not None:
                print(key)
                return 0

        if elapsed >= POLL_MAX_SECONDS:
            break

        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        path = find_config_file()

    return 0


if __name__ == "__main__":
    sys.exit(main())
