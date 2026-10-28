#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="/mnt/telemetry"

ls "$TARGET" >/dev/null

if ! findmnt -rn -T "$TARGET" -t cifs >/dev/null; then
    echo "ERROR: $TARGET is not mounted from TrueNAS"
    exit 1
fi

echo "Deploying Telemetry"

rsync -av \
    --exclude 'ssh/' \
    --exclude '.env' \
    --exclude '.git/' \
    --exclude '.vscode/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "$PROJECT_ROOT/" "$TARGET/"

echo "Telemetry deployment complete."