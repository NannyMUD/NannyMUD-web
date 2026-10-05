# NannyMUD-web

NannyMUD on the web: the website, built every night from the mud's own
export, and the player wiki beside it. One command brings it all up.

    cp .env.example .env     # fill it in
    ./run.sh

Then the site is at `http://localhost:8080/` and the wiki at
`http://localhost:8080/wiki/`. Run `./run.sh` again after pulling
changes. Docker with Compose is all it needs.

## What runs

| Service | What it does |
|---|---|
| `builder` | Fetches the mud's export over FTP and builds the site; again at `NANNY_BUILD_AT` (`:30`, half past every hour, by default; or a time of day such as `04:30` for once a night). |
| `web` | nginx. The site at `/`; MediaWiki's pages at `/wiki/Name` and its files at `/w/`. |
| `mediawiki` | MediaWiki as PHP-FPM. Its settings live in `wiki/settings/`, uploads in `wiki/images/`. |
| `database` | MariaDB for the wiki. |
| `wikibackup` | Every night: the wiki's database and uploads to a private git repository. |

## The site

1. In the mud, `/obj/daemon/webexport` writes `quests`, `staff`, `areas`,
   `guilds`, `help` and `stats` as JSON into `/www/export/` every night
   at 04:00, readable by every wizard.
2. `scripts/fetch.sh` downloads them with the wizard's FTP login from
   `.env`. A failed fetch keeps the last good data.
3. `build.py` (with `stats.py`) turns them, `content/` and `times/` into
   static pages. No page uses JavaScript: everything is in the HTML, so
   every page is indexable.

- `templates/` the pages; `static/css/nanny.css` the look, shared with the wiki
- `content/` the old Lysator pages (`scripts/import_old.py`) and the guild pages
- `times/` the NannyMUD Times, 1996 to 2010, as the paper printed it

To build without the containers:

    docker build -t nanny-web -f docker/Dockerfile .
    docker run --rm -v "$PWD":/site --env-file .env nanny-web sh -c "scripts/fetch.sh && python build.py"

## The wiki

On the first `./run.sh` with an empty `wiki/settings/`, the wiki is set
up from scratch with the administrator named in `.env`.

To move an existing wiki in instead, before the first run:

1. Put its `LocalSettings.php` in `wiki/settings/` and its uploads in
   `wiki/images/`. In `LocalSettings.php` set `$wgServer` to the site's
   address, `$wgScriptPath = "/w";`, `$wgArticlePath = "/wiki/$1";` and
   `$wgDBserver = "database";`, with the database name, user and
   password from `.env`.
2. `./run.sh`, then load its database dump:

       docker compose exec -T database sh -c 'mariadb -u "$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"' < wiki.sql
       docker compose exec mediawiki php maintenance/run.php update --quick

Old links of the form `/index.php/Name` are sent on to `/wiki/Name`.

## Backups of the wiki

Set `WIKI_BACKUP_REPO` in `.env` to a **private** repository (the
database holds the users' e-mail addresses and password hashes), add a
deploy key with write access to it, and save the private key as
`wiki/backup_key`. Every night at `WIKI_BACKUP_AT` the database is dumped
as SQL, one row a line, and committed with the uploads; only what
changed shows in the history. To restore, load `wiki.sql` as above and
copy `images/` to `wiki/images/`.

## Files that never go in git

`.env` (logins and passwords), `wiki/` (settings with the database
password, uploads, the backup key), `data/` and `public/`.
