#!/bin/sh
# Bring up NannyMUD on the web: the site (rebuilt every night from the
# mud's export), the wiki and its database. Run it again to update.
set -eu
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is needed: https://docs.docker.com/get-docker/" >&2
  exit 1
fi
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Made .env from .env.example. Fill it in, then run ./run.sh again." >&2
  exit 1
fi
mkdir -p wiki/images wiki/settings
[ -e wiki/backup_key ] || : > wiki/backup_key   # no key: no backups

docker compose up -d --build
sh docker/wiki-install.sh
port=$(grep -E '^NANNY_HTTP_PORT=' .env | cut -d= -f2)
echo
echo "Up. The site:  http://localhost:${port:-8080}/"
echo "    The wiki:  http://localhost:${port:-8080}/wiki/"
echo "Logs: docker compose logs -f builder"
