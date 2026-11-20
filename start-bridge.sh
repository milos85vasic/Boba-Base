#!/bin/sh
set -eu

# Install Python dependencies once. The download-proxy requirements are the
# source of truth for the merge-service/bridge dependency set.
pip install --no-cache-dir -q -r /config/download-proxy/requirements.txt || true

# Run the WebUI bridge host process inside the container.
exec python3 /app/webui-bridge.py
