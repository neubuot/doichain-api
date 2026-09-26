#!/bin/bash
# Gleicht den MCP-Server mit dem oeffentlichen Repo neubuot/doichain-mcp ab (lokaler Klon daneben).
# Quelle der Wahrheit fuer server.py, Landingpage und systemd-Unit ist dieses Repo, server.json, README,
# Tests und Workflows pflegt das oeffentliche Repo. Aufruf: bash deploy/sync-public-mcp.sh [pfad-zum-klon]
set -euo pipefail
cd "$(dirname "$0")/.."
PUB=${1:-../doichain-mcp}
[ -d "$PUB/.git" ] || { echo "Kein Git-Klon unter $PUB"; exit 1; }
cp doichain_mcp/server.py "$PUB/doichain_mcp/server.py"
rsync -a --delete web/mcp-site/ "$PUB/web/mcp-site/"
cp deploy/doichain-mcp.service "$PUB/deploy/doichain-mcp.service"
echo "Abgeglichen. Versionen: $(grep -m1 '^VERSION' doichain_mcp/server.py) / $(grep -m1 '"version"' "$PUB/server.json")"
git -C "$PUB" status --short
