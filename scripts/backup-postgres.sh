#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

ENV_FILE=${1:?Usage: scripts/backup-postgres.sh .env.odoo_co [backup-directory]}
BACKUP_DIR=${2:-./backups}
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
database_backup="$BACKUP_DIR/postgres-$timestamp.dump"
media_backup="$BACKUP_DIR/media-$timestamp.tar.gz"
trap 'rm -f "$database_backup" "$media_backup"' ERR

docker compose --env-file "$ENV_FILE" exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$database_backup"
docker compose --env-file "$ENV_FILE" exec -T backend \
  tar -C /app/media -czf - . > "$media_backup"
test -s "$database_backup"
test -s "$media_backup"
docker compose --env-file "$ENV_FILE" exec -T db pg_restore --list < "$database_backup" > /dev/null
tar -tzf "$media_backup" > /dev/null
chmod 600 "$database_backup" "$media_backup"
trap - ERR
echo "Database and media backups created in: $BACKUP_DIR"
