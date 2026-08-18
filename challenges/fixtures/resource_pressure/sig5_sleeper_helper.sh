#!/bin/bash
# sig5_sleeper_helper.sh — inert helper for sig5_real_pathological_regex_fixture.sh.
#
# Ignores ALL positional arguments (they exist purely so /proc/<pid>/cmdline
# records whatever pathological-looking argv the driver disguises this
# process with, via `exec -a ugrep`). The actual sleep duration is read
# from the SIG5_SLEEP_SECONDS environment variable (defaulting to 20 if
# absent or non-numeric) — a plain env var, never positional-parameter
# indirection, so this script's own behaviour cannot be confused with the
# disguise arguments it is deliberately fed. This process does nothing
# resource-intensive: no real grep, no real memory pressure, just a
# bounded sleep.
set -u
duration="${SIG5_SLEEP_SECONDS:-20}"
case "$duration" in
  '' | *[!0-9.]*) duration=20 ;;
esac
sleep "$duration"
