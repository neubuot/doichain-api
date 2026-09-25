#!/bin/bash
# Kopiert das Arbeitsverzeichnis (ohne .git und Caches) nach /root/doichain-api-src auf dem Server
# und fuehrt dort deploy/install.sh aus. Aufruf: bash deploy/push-to-server.sh [benutzer@host]
set -euo pipefail
HOST=${1:-root@136.243.155.62}
cd "$(dirname "$0")/.."
tar --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' -cf - . \
  | ssh "$HOST" 'rm -rf /root/doichain-api-src && mkdir -p /root/doichain-api-src && tar -xf - -C /root/doichain-api-src && bash /root/doichain-api-src/deploy/install.sh'
