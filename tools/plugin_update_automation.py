#!/usr/bin/env python3
"""
Plugin Update Automation Tool

This tool:
1. Checks for updates to plugins from upstream sources
2. Downloads updated plugin files
3. Validates new plugins before installation
4. Creates backups of existing plugins
5. Generates update reports

Usage:
    python3 tools/plugin_update_automation.py --check
    python3 tools/plugin_update_automation.py --update
    python3 tools/plugin_update_automation.py --update --dry-run
"""

import os
import sys
import json
import argparse
import shutil
import hashlib
from datetime import datetime
from typing import Dict, List
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
PLUGINS_DIR = os.path.join(PROJECT_DIR, "plugins")
sys.path.insert(0, PLUGINS_DIR)


class Colors:
    GREEN = "\033[92m"
    FAIL = "\033[91m"
    WARNING = "\033[93m"
    CYAN = "\033[96m"
    BLUE = "\033[94m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text):
    print(f"{Colors.WARNING}! {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.CYAN}ℹ {text}{Colors.ENDC}")


def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{text}{Colors.ENDC}")


# Known upstream sources for plugins
UPSTREAM_SOURCES = {
    "eztv": "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/eztv.py",
    "jackett": "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/jackett.py",
    "limetorrents": "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/limetorrents.py",
    "piratebay": "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/piratebay.py",
    "solidtorrents": "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/solidtorrents.py",
    "torlock": "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/torlock.py",
    "torrentproject": "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/torrentproject.py",
    "torrentscsv": "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/torrentscsv.py",
    "academictorrents": "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/academictorrents.py",
    "bt4g": "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/bt4g.py",
    "glotorrents": "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/glotorrents.py",
    "kickass": "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/kickasstorrents.py",
    "linuxtracker": "https://raw.githubusercontent.com/MadeOfMagicAndWires/qBit-plugins/master/engines/linuxtracker.py",
    "nyaa": "https://raw.githubusercontent.com/MadeOfMagicAndWires/qBit-plugins/master/engines/nyaasi.py",
}

# BOB-217 -- SECURITY (supply-chain): pinned SHA-256 content hashes.
#
# THREE of the four repositories in UPSTREAM_SOURCES above are third-party
# PERSONAL GitHub accounts, not the official qbittorrent organisation:
# LightDestory/qBittorrent-Search-Plugins and MadeOfMagicAndWires/qBit-plugins.
# `update_plugin()` combines UNTRUSTED INPUT (these URLs) + MUTATION (writes
# plugins/<name>.py) + DEFERRED CODE EXECUTION (qBittorrent imports and runs
# that file as a search engine). Until this fix, the ONLY gate was
# `compile()` in `_validate_plugin()` -- a SYNTAX check. A syntactically
# valid file is exactly what a hostile payload is.
#
# This registry is the actual safety gate: fetched content is written to
# disk ONLY when its SHA-256 hash matches the pin recorded here. This is a
# "trust on first use" baseline -- every hash below was computed from each
# URL's content as fetched on 2026-09-23. A legitimate upstream change
# (a real bugfix, a tracker moving domains, etc.) will therefore fail this
# check too, by design: an operator must explicitly review the diff and
# re-pin the new hash before `--update` will install it. A plugin with no
# entry here is refused with "no pin configured", never silently accepted.
#
# `python3 tools/plugin_update_automation.py --check` still works without
# consulting this registry (it only diffs against the locally-installed
# copy, never writes); this registry is consulted by `--update` only, at
# `PluginUpdateManager._verify_pinned_hash()`.
PLUGIN_PINNED_HASHES: Dict[str, str] = {
    "eztv": "22a051ae9de6403a5735540c074b78d4eb247de9d6366ef896dc750b8c51c4bb",
    "jackett": "d035fca325dce689d87bd900fa1951ff5bca535aedfa71f6e040b7ca954537bf",
    "limetorrents": "aca3fbc4956970474a66295f5e61f02532bcdf5399ae97c144bf826a7c8fddce",
    "piratebay": "b37f13d21ff5f22ff2154a497cd3ed2d727784024d09d393c1bead88e438dab5",
    "solidtorrents": "e10e039b02c675fbeae6503482f1fb12683bba1c39f5424e7c2729dc44d12a71",
    "torlock": "8571dfd3db7d9ea9f31df245e0ba1c04b5e9373824a3332a0db98f2240dca632",
    "torrentproject": "64960bb8d7ebde829b55fdb5a669f96cb0694d8d49cc87aaf960f1f1dae793f0",
    "torrentscsv": "7c7c8a54249e5f2ce237df6421a735a5c1bd7acefd1304d736ee8f925fd6031b",
    "academictorrents": "5a4e025814e1fc8ae97a6c267fb706e03976fef1b629cb63eeb9944ebd9b49d3",
    "bt4g": "401100cd935591cb91c4720061f13b02dad8f0ee0a276c19e8757937a66a8cfe",
    "glotorrents": "66f7ac3ec14f7739451d4614823f82acda619430dda59bb521c51f507b5966ca",
    "kickass": "b3e9f714f06936a9185b3a54bd58a6f4230d13d1378d87012284f2955bf68d69",
    "linuxtracker": "7c24908e39935c5c13046afc0969c952aec587f6fd4c16cdf86cf89b5da9a411",
    "nyaa": "8b38deb7d22d86c3d64300cd58d55810260ea61b96b0fd552c3748201de44e46",
}


class PluginUpdateManager:
    """Manages plugin updates from upstream sources."""

    def __init__(self, plugins_dir: str, backup_dir: str = None, pinned_hashes: Dict[str, str] | None = None):
        self.plugins_dir = plugins_dir
        self.backup_dir = backup_dir or os.path.join(plugins_dir, ".backups")
        # BOB-217: defaults to the module-level registry, but is
        # overridable (e.g. by tests) without touching the real registry.
        self.pinned_hashes = PLUGIN_PINNED_HASHES if pinned_hashes is None else pinned_hashes

    def check_for_updates(self) -> List[Dict]:
        """Check all plugins for available updates."""
        print_header("CHECKING FOR PLUGIN UPDATES")

        updates_available = []

        for plugin_name, url in UPSTREAM_SOURCES.items():
            try:
                local_path = os.path.join(self.plugins_dir, f"{plugin_name}.py")

                if not os.path.exists(local_path):
                    print_info(f"{plugin_name}: Not installed locally")
                    updates_available.append({"plugin": plugin_name, "status": "not_installed", "upstream_url": url})
                    continue

                local_hash = self._get_file_hash(local_path)
                upstream_content = self._download_url(url)

                if upstream_content is None:
                    print_warning(f"{plugin_name}: Could not fetch upstream")
                    continue

                upstream_hash = hashlib.md5(upstream_content.encode()).hexdigest()

                if local_hash != upstream_hash:
                    local_version = self._extract_version(local_path)
                    upstream_version = self._extract_version_from_content(upstream_content)

                    print_info(f"{plugin_name}: Update available ({local_version} -> {upstream_version})")
                    updates_available.append(
                        {
                            "plugin": plugin_name,
                            "status": "update_available",
                            "local_version": local_version,
                            "upstream_version": upstream_version,
                            "upstream_url": url,
                            "upstream_content": upstream_content,
                        }
                    )
                else:
                    print_success(f"{plugin_name}: Up to date")

            except Exception as e:
                print_error(f"{plugin_name}: Error checking - {e}")

        return updates_available

    def update_plugin(self, plugin_name: str, upstream_content: str, dry_run: bool = False) -> Dict:
        """Update a single plugin."""
        result = {
            "plugin": plugin_name,
            "timestamp": datetime.now().isoformat(),
            "dry_run": dry_run,
            "status": "pending",
        }

        local_path = os.path.join(self.plugins_dir, f"{plugin_name}.py")

        try:
            if not self._validate_plugin(upstream_content):
                result["status"] = "failed"
                result["error"] = "Validation failed (syntax check)"
                print_error(f"{plugin_name}: Validation failed (syntax check)")
                return result

            # BOB-217: the syntax check above is NOT a safety gate (see its
            # docstring). This IS the safety gate -- content that has not
            # been explicitly reviewed and pinned is refused before it is
            # ever written to disk, dry-run or not (checked before the
            # dry-run early-return, so a preview reflects what --update
            # would actually do).
            pin_ok, pin_reason = self._verify_pinned_hash(plugin_name, upstream_content)
            if not pin_ok:
                result["status"] = "failed"
                result["error"] = f"Pinned-hash verification failed: {pin_reason}"
                print_error(f"{plugin_name}: Pinned-hash verification failed - {pin_reason}")
                return result

            if dry_run:
                result["status"] = "dry_run_success"
                print_info(f"{plugin_name}: Would update (dry run)")
                return result

            if os.path.exists(local_path):
                backup_path = self._create_backup(local_path)
                result["backup"] = backup_path

            with open(local_path, "w", encoding="utf-8") as f:
                f.write(upstream_content)

            result["status"] = "success"
            print_success(f"{plugin_name}: Updated successfully")

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            print_error(f"{plugin_name}: Update failed - {e}")

        return result

    def _get_file_hash(self, filepath: str) -> str:
        """Calculate MD5 hash of a file."""
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _download_url(self, url: str, timeout: int = 30) -> str | None:
        """Download content from URL."""
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except (URLError, HTTPError):
            return None

    def _extract_version(self, filepath: str) -> str:
        """Extract version from plugin file."""
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
            return self._extract_version_from_content(content)
        except:
            return "unknown"

    def _extract_version_from_content(self, content: str) -> str:
        """Extract version from plugin content."""
        import re

        version_match = re.search(r"# VERSION:\s*([\d.]+)", content)
        if version_match:
            return version_match.group(1)
        return "unknown"

    def _validate_plugin(self, content: str) -> bool:
        """Compile-check plugin syntax.

        BOB-217 SECURITY NOTE: this is a SYNTAX check ONLY -- it proves
        `content` is parseable Python, NOT that it is safe. A hostile
        payload (credential exfiltration, a backdoor dropped on import,
        arbitrary code that runs the moment qBittorrent loads this file
        as a search engine) is syntactically valid Python and WILL pass
        this check. This method is NOT, and must NOT be treated as, a
        safety/security gate. The actual safety gate for untrusted
        fetched content is `_verify_pinned_hash()`, called separately
        (and required to pass) in `update_plugin()` before anything is
        written to disk.
        """
        try:
            compile(content, "<string>", "exec")
            return True
        except SyntaxError:
            return False

    def _verify_pinned_hash(self, plugin_name: str, content: str) -> tuple[bool, str]:
        """BOB-217 safety gate: verify fetched content against its pinned
        SHA-256 content hash BEFORE it is ever written to disk.

        Returns (ok, reason). `reason` always names the specific check
        that passed or failed -- "no pin configured for this URL" vs.
        "hash mismatch" are deliberately distinct, observable facts
        (constitution SS11.4.6 no-guessing) so an operator (or an
        automated caller) never has to infer why an update was refused.
        """
        expected = self.pinned_hashes.get(plugin_name)
        if expected is None:
            return False, f"no pin configured for this URL (plugin '{plugin_name}')"

        actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if actual != expected:
            return (
                False,
                f"hash mismatch for plugin '{plugin_name}': "
                f"fetched content does not match the declared pinned hash "
                f"(expected {expected}, got {actual})",
            )

        return True, "pinned hash verified"

    def _create_backup(self, filepath: str) -> str:
        """Create backup of existing plugin."""
        os.makedirs(self.backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.basename(filepath)
        backup_name = f"{filename}.{timestamp}.bak"
        backup_path = os.path.join(self.backup_dir, backup_name)

        shutil.copy2(filepath, backup_path)
        return backup_path


def main():
    parser = argparse.ArgumentParser(description="Plugin Update Automation Tool")
    parser.add_argument("--check", action="store_true", help="Check for updates only")
    parser.add_argument("--update", action="store_true", help="Apply available updates")
    parser.add_argument("--plugin", type=str, help="Update specific plugin")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated")
    parser.add_argument("--output", type=str, default="plugin_update_report.json", help="Output file")
    args = parser.parse_args()

    manager = PluginUpdateManager(PLUGINS_DIR)

    if args.check or args.update:
        updates = manager.check_for_updates()

        if args.update:
            print_header("APPLYING UPDATES")
            results = []

            for update in updates:
                if update["status"] in ["update_available", "not_installed"]:
                    if args.plugin and update["plugin"] != args.plugin:
                        continue

                    if "upstream_content" in update:
                        result = manager.update_plugin(
                            update["plugin"], update["upstream_content"], dry_run=args.dry_run
                        )
                        results.append(result)

            report = {
                "timestamp": datetime.now().isoformat(),
                "total_checked": len(UPSTREAM_SOURCES),
                "updates_found": len([r for r in results if r.get("status") == "success"]),
                "results": results,
            }
        else:
            report = {
                "timestamp": datetime.now().isoformat(),
                "total_checked": len(UPSTREAM_SOURCES),
                "updates_found": len([u for u in updates if u.get("status") == "update_available"]),
                "results": updates,
            }

        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n{Colors.CYAN}Report saved to: {args.output}{Colors.ENDC}")

        return 0 if report["updates_found"] == 0 else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
