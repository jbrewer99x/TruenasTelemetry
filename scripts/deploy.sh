#!/usr/bin/env bash
# Deploy to the TrueNAS "telemetry" SMB share from macOS.
# Usage: scripts/deploy.sh [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TRUENAS_HOST="${TRUENAS_HOST:-10.0.0.10}"
SHARE="${SHARE:-telemetry}"
TARGET="${TARGET:-/Volumes/$SHARE}"

RSYNC_FLAGS=(-av)
if [[ "${1:-}" == "--dry-run" || "${1:-}" == "-n" ]]; then
    RSYNC_FLAGS+=(--dry-run)
    echo "Dry run: nothing will be copied."
fi

is_mounted() {
    # e.g. "//user@10.0.0.10/telemetry on /Volumes/telemetry (smbfs, ...)"
    mount | grep -Eq "@?${TRUENAS_HOST}/${SHARE} on ${TARGET} \(smbfs"
}

if ! is_mounted; then
    echo "Mounting smb://${TRUENAS_HOST}/${SHARE} (credentials from Keychain)..."
    osascript -e "mount volume \"smb://${TRUENAS_HOST}/${SHARE}\"" >/dev/null
fi

if ! is_mounted; then
    echo "ERROR: $TARGET is not mounted from //${TRUENAS_HOST}/${SHARE}"
    exit 1
fi

echo "Deploying Telemetry to $TARGET"

rsync "${RSYNC_FLAGS[@]}" \
    --exclude 'ssh/' \
    --exclude '.env' \
    --exclude '.git/' \
    --exclude '.vscode/' \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude '.DS_Store' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "$PROJECT_ROOT/" "$TARGET/"

echo "Telemetry deployment complete."
