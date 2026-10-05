#!/bin/sh
# The builder container: fetch the mud's export and build the site, now
# and then again at NANNY_BUILD_AT: by default half past every hour,
# since the mud writes its export on the hour. A failed fetch keeps the
# last good data, so the site is rebuilt from it rather than left empty.
set -u
cd /site
AT="${NANNY_BUILD_AT:-:30}"

build() {
  echo "$(date '+%F %T') fetching the export"
  sh scripts/fetch.sh || echo "fetch failed; building from the last data"
  # mail Dan when the export has gone stale (and when it recovers)
  python scripts/stale_alarm.py || echo "stale check failed"
  echo "$(date '+%F %T') building"
  # build into a fresh folder, then swap it in, so nginx never serves a
  # half written site
  rm -rf "$NANNY_OUT_DIR.new"
  if NANNY_OUT_DIR="$NANNY_OUT_DIR.new" python build.py; then
    mkdir -p "$NANNY_OUT_DIR"
    find "$NANNY_OUT_DIR" -mindepth 1 -delete
    cp -a "$NANNY_OUT_DIR.new/." "$NANNY_OUT_DIR/"
    rm -rf "$NANNY_OUT_DIR.new"
  else
    echo "build failed; the site stays as it was"
  fi
}

build
# NANNY_BUILD_AT is a time of day ("04:30", once a night) or a minute
# past every hour (":30", hourly: the mud exports on the hour).
while true; do
  now=$(date +%s)
  case "$AT" in
    :*)
      min=${AT#:}
      min=${min#0}
      next=$(( now - now % 3600 + min * 60 ))
      [ "$next" -le "$now" ] && next=$(( next + 3600 ))
      ;;
    *)
      next=$(date -d "today $AT" +%s)
      [ "$next" -le "$now" ] && next=$(date -d "tomorrow $AT" +%s)
      ;;
  esac
  sleep $((next - now))
  build
done
