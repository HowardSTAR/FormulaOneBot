#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${1:-$SCRIPT_DIR/backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$BACKUP_DIR/jenkins-home-$timestamp.tar.gz"

mkdir -p "$BACKUP_DIR"

docker run --rm \
    --volume f1hub_jenkins_home:/source:ro \
    --volume "$BACKUP_DIR:/backup" \
    alpine:3.22 \
    tar -czf "/backup/$(basename "$archive")" -C /source .

sha256sum "$archive" > "$archive.sha256"
echo "Создано: $archive"
echo "Контрольная сумма: $archive.sha256"
