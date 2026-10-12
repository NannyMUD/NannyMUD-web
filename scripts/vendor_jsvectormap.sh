#!/bin/sh
# Re-fetch the vendored jsVectorMap files under static/js/vendor/, pinned
# to 1.7.0 (MIT, Mustafa Omar). Run from the repo root in a throwaway
# docker container, never on the host:
#
#   docker run --rm -v "$PWD":/repo -w /tmp node:20-slim sh /repo/scripts/vendor_jsvectormap.sh
#
# Check the upstream diff before bumping VERSION; the site only uses
# jsvectormap.min.js and the world-merc map data, both unmodified apart
# from the header comment this script adds.
set -e
VERSION=1.7.0
REPO=/repo
OUT="$REPO/static/js/vendor"

npm install "jsvectormap@$VERSION" --no-save >/dev/null
SRC=node_modules/jsvectormap

{
  echo "// jsVectorMap $VERSION (MIT, Mustafa Omar), vendored unmodified from"
  echo "// https://www.npmjs.com/package/jsvectormap. Full text: LICENSE-jsvectormap.txt"
  echo "// in this folder. Re-fetch with scripts/vendor_jsvectormap.sh."
  cat "$SRC/dist/jsvectormap.min.js"
} > "$OUT/jsvectormap.min.js"

{
  echo "// jsVectorMap $VERSION world_merc map data (MIT, Mustafa Omar), vendored"
  echo "// unmodified. See jsvectormap.min.js in this folder for provenance."
  cat "$SRC/dist/maps/world-merc.js"
} > "$OUT/world-merc.js"

cp "$SRC/LICENSE" "$OUT/LICENSE-jsvectormap.txt"
echo "done: $(wc -c < "$OUT/jsvectormap.min.js") + $(wc -c < "$OUT/world-merc.js") bytes"
