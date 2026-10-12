#!/bin/sh
# Download the mud's nightly export into the data folder. Reads .env (or
# the environment) for the wizard's FTP login; the login is chrooted, so
# %2f makes the path absolute in the lib. The password goes to curl on
# stdin, never on the command line.
set -eu
cd "$(dirname "$0")/.."
[ -f .env ] && . ./.env
: "${NANNY_FTP_HOST:?}" "${NANNY_FTP_PORT:?}" "${NANNY_FTP_USER:?}" "${NANNY_FTP_PASS:?}"
DATA="${NANNY_DATA_DIR:-data}"
mkdir -p "$DATA"
fetch() {
  printf 'user = "%s:%s"\n' "$NANNY_FTP_USER" "$NANNY_FTP_PASS" |
    curl -fsS --ftp-pasv -K - \
      "ftp://$NANNY_FTP_HOST:$NANNY_FTP_PORT/%2fwww/export/$1.json" -o "$DATA/$1.json.new" &&
  python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$DATA/$1.json.new" &&
  mv "$DATA/$1.json.new" "$DATA/$1.json"
}
for f in quests puzzles staff areas guilds help stats; do
  fetch "$f"
done
# newer exports: a mud that does not write them yet keeps the rest going
for f in booklets tops; do
  fetch "$f" || { rm -f "$DATA/$f.json.new"; echo "no $f.json in the export"; }
done
echo "fetched export"
