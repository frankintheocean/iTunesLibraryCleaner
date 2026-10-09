#!/usr/bin/env bash
set -euo pipefail
cd /workspace/iTunesLibraryCleaner
python3 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r requirements-lock-linux.txt
export npm_config_cache=/tmp/library-manager-npm-cache
export XDG_CACHE_HOME=/tmp/library-manager-cache
if [[ -n "${HTTPS_PROXY:-}" ]]; then
  export ELECTRON_GET_USE_PROXY=1
  export GLOBAL_AGENT_HTTP_PROXY="$HTTPS_PROXY"
fi
npm ci
node node_modules/electron/install.js
npm run build
