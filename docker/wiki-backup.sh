#!/bin/sh
# The wiki's nightly backup: the database as SQL and the uploaded files,
# committed to a git repository and pushed. The repository must be
# PRIVATE: the database holds the users' e-mail addresses and password
# hashes. Without WIKI_BACKUP_REPO set, this container only waits.
set -u
AT="${WIKI_BACKUP_AT:-05:00}"
REPO_DIR=/backup/repo
KEY=/run/backup_key

if [ -z "${WIKI_BACKUP_REPO:-}" ]; then
  echo "WIKI_BACKUP_REPO is not set; no wiki backups."
  exec sleep infinity
fi
if [ ! -f "$KEY" ]; then
  echo "No deploy key at wiki/backup_key; no wiki backups."
  exec sleep infinity
fi
mkdir -p ~/.ssh
cp "$KEY" ~/.ssh/id_ed25519 && chmod 600 ~/.ssh/id_ed25519
ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null
git config --global user.name "NannyMUD wiki backup"
git config --global user.email "wiki-backup@localhost"

backup() {
  echo "$(date '+%F %T') wiki backup"
  if [ ! -d "$REPO_DIR/.git" ]; then
    git clone "$WIKI_BACKUP_REPO" "$REPO_DIR" || { echo "clone failed"; return; }
  fi
  cd "$REPO_DIR" || return
  git pull --quiet --rebase || true
  # one row a line, no dump date: the nightly diff shows only what changed
  if mariadb-dump -h database -u "$WIKI_DB_USER" -p"$WIKI_DB_PASSWORD" \
       --single-transaction --skip-extended-insert --skip-dump-date \
       --default-character-set=binary "$WIKI_DB_NAME" > wiki.sql.new; then
    mv wiki.sql.new wiki.sql
  else
    rm -f wiki.sql.new
    echo "dump failed; nothing pushed"
    return
  fi
  rsync -a --delete --exclude 'thumb/' --exclude 'temp/' --exclude 'lockdir/' \
    /images/ images/
  git add -A
  if git diff --cached --quiet; then
    echo "nothing changed"
  else
    git commit --quiet -m "backup $(date +%F)" && git push --quiet && echo "pushed"
  fi
}

backup
while true; do
  now=$(date +%s)
  next=$(date -d "today $AT" +%s)
  [ "$next" -le "$now" ] && next=$(date -d "tomorrow $AT" +%s)
  sleep $((next - now))
  backup
done
