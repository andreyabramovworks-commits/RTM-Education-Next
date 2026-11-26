#!/bin/sh
# Run as rtmedu from a dedicated cron entry after the first approved release.
set -eu

ROOT=/opt/rtm-education-next
BACKUPS=/home/rtmedu/rtm-next-production-backups
LOCK=/tmp/rtm-education-next-deploy.lock

if [ "$(realpath "$(dirname "$0")/..")" != "$ROOT" ]; then
  echo 'Refusing to deploy from an unexpected directory' >&2
  exit 1
fi

exec 9>"$LOCK"
flock -n 9 || exit 0
cd "$ROOT"
if [ -f data/bitrix-client-secret.txt ]; then
  BITRIX_CLIENT_SECRET=$(cat data/bitrix-client-secret.txt)
  export BITRIX_CLIENT_SECRET
fi
git fetch --quiet origin main --tags
target=$(git rev-parse origin/main)
current=$(git rev-parse HEAD)
deployed=$(cat data/deployed-commit 2>/dev/null || true)
if [ "$target" = "$deployed" ]; then
  exit 0
fi
git diff --quiet
git diff --cached --quiet
if [ "$current" != "$target" ]; then
  git merge-base --is-ancestor "$current" "$target"
fi

python3 deploy/backup.py create --project rtm-education-next --backup-root "$BACKUPS"
if [ "$current" != "$target" ]; then
  git checkout --quiet main
  git merge --ff-only --quiet origin/main
fi

docker compose -f compose.yaml -f deploy/production.compose.yaml build api worker migrate frontend
docker compose -f compose.yaml -f deploy/production.compose.yaml up -d db
docker compose -f compose.yaml -f deploy/production.compose.yaml --profile migrate run --rm migrate
docker compose -f compose.yaml -f deploy/production.compose.yaml up -d api worker frontend

i=0
until curl -fsS --max-time 5 http://127.0.0.1:18094/education-next/api/ready >/dev/null; do
  i=$((i + 1))
  [ "$i" -lt 24 ] || { echo 'Readiness check failed' >&2; exit 1; }
  sleep 5
done
curl -fsS --max-time 5 http://127.0.0.1:18094/education-next/ >/dev/null
printf '%s\n' "$target" > data/deployed-commit.tmp
chmod 600 data/deployed-commit.tmp
mv data/deployed-commit.tmp data/deployed-commit
echo "Deployed $target"
