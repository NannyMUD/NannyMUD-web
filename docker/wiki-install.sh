#!/bin/sh
# First start of an empty wiki: run MediaWiki's installer from .env and
# keep LocalSettings.php in wiki/settings/. Pages live at /wiki/Name,
# scripts at /w/. To move the live wiki instead, see README.md.
set -eu
cd "$(dirname "$0")/.."
[ -f wiki/settings/LocalSettings.php ] && exit 0
. ./.env
: "${WIKI_ADMIN_USER:?}" "${WIKI_ADMIN_PASSWORD:?}" "${WIKI_DB_PASSWORD:?}" "${NANNY_SITE_URL:?}"

echo "Setting up the wiki ..."
for i in $(seq 30); do
  docker compose exec -T database sh -c 'mariadb-admin ping -u root --silent 2>/dev/null || mariadb -u "$MARIADB_USER" -p"$MARIADB_PASSWORD" -e "select 1" >/dev/null 2>&1' && break
  sleep 2
done
docker compose exec -T mediawiki php maintenance/run.php install \
  --dbtype mysql --dbserver database \
  --dbname "${WIKI_DB_NAME:-my_wiki}" --dbuser "${WIKI_DB_USER:-wikiuser}" --dbpass "$WIKI_DB_PASSWORD" \
  --server "$NANNY_SITE_URL" --scriptpath /w \
  --pass "$WIKI_ADMIN_PASSWORD" --confpath /tmp \
  "${WIKI_NAME:-NannyMUD Wiki}" "$WIKI_ADMIN_USER"
docker compose exec -T mediawiki sh -c 'cat /tmp/LocalSettings.php && cat <<EOF

# NannyMUD: pages at /wiki/Name, scripts at /w/ (docker/nginx.conf)
\$wgArticlePath = "/wiki/\$1";
\$wgUsePathInfo = true;
# the site's skin, the same one the visitor picked on the site (nginx
# serves it by cookie behind this one URL)
\$wgHooks["BeforePageDisplay"][] = static function ( \$out, \$skin ) {
	\$out->addStyle( "/static/css/nanny-wiki.css?skin=2" );
};
EOF' > wiki/settings/LocalSettings.php
# readable by the web server's group (www-data, gid 33), not by everyone:
# it holds the database password
chmod 640 wiki/settings/LocalSettings.php
docker run --rm -v "$PWD/wiki/settings:/s" alpine chgrp 33 /s/LocalSettings.php
docker compose restart mediawiki >/dev/null
echo "The wiki is set up. Log in as $WIKI_ADMIN_USER."
