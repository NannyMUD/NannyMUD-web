#!/bin/sh
# The builder container: fetch the mud's export and build the site, now
# and then every night once the mud has written its export (04:00 mud
# time), at NANNY_BUILD_AT. A failed fetch keeps the last good data, so
# the site is rebuilt from it rather than left empty.
set -u
cd /site
AT="${NANNY_BUILD_AT:-04:30}"

build() {
  echo "$(date '+%F %T') fetching the export"
  sh scripts/fetch.sh || echo "fetch failed; building from the last data"
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
while true; do
  now=$(date +%s)
  next=$(date -d "today $AT" +%s)
  [ "$next" -le "$now" ] && next=$(date -d "tomorrow $AT" +%s)
  sleep $((next - now))
  build
done
