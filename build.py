"""Build the NannyMUD website into public/.

Reads the mud's hourly export (data/*.json, fetched by scripts/fetch.sh),
the pages carried over from the old site (content/*.html) and the NannyMUD
Times archive (times/), and writes static pages. No server code, no
tracking; any web server can serve public/.

    python build.py            # writes public/
"""
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil

from jinja2 import Environment, FileSystemLoader, select_autoescape

import attendance
import stats as numbers
import visits

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("NANNY_OUT_DIR", os.path.join(ROOT, "public"))
DATA = os.environ.get("NANNY_DATA_DIR", os.path.join(ROOT, "data"))
# the wiki runs beside the site, under /wiki/ (see docker/nginx.conf)
WIKI = os.environ.get("NANNY_WIKI_URL", "/wiki/Main_Page")
DISCORD = "https://discord.gg/JqMrZqKU2D"
# where the site is served; canonical links and the sitemap use it
SITE = os.environ.get("NANNY_SITE_URL", "https://nanny.thorn.vip").rstrip("/")
DESCRIPTION = ("NannyMUD, an internet game and community since 1990: a text based "
               "world of epic fantasy, quests, guilds and riddles.")

NAV = [
    ("Play", "/play/"),
    ("World", "/world/"),
    ("Quests", "/quests/"),
    ("Puzzles", "/puzzles/"),
    ("Guilds", "/guilds/"),
    ("Help", "/help/"),
    ("Times", "/times/"),
    ("History", "/history/"),
    ("Admins", "/staff/"),
    ("Stats", "/stats/"),
    ("Wiki", WIKI),
]


# old pages whose content lives elsewhere now, and old addresses whose
# page moved: both get a redirect, and MOVED's targets are also rewritten
# into any content page's own links
MOVED = {"the-world": "/world/", "connect": "/play/",
         "history/web": "/history/old-web/"}
# short addresses that send the visitor elsewhere
SHORT = {"discord": DISCORD}

# Where each content page sits, for its breadcrumb: the slug of its
# parent page, or a fixed (title, url) for a page built from a template.
# A page not listed here is top level and has none.
HELP, HISTORY = ("Help", "/help/"), ("History", "/history/")
WEBHISTORY = ("Old web presence", "/history/old-web/")
PARENT = {
    "the-beginnings": HISTORY, "timeline": HISTORY, "musings": HISTORY,
    "events": HISTORY, "the-people": HISTORY, "pictures": HISTORY,
    "other-topics": WEBHISTORY, "attendance": WEBHISTORY,
    "guild-statistics": WEBHISTORY, "where-players-come-from": WEBHISTORY,
    "old-art": WEBHISTORY,
    "faq": HELP, "newbie-booklet": HELP, "introduction": HELP, "the-game": HELP,
    "ewan": "faq", "what-is-nannymud": "introduction", "features": "introduction",
}


# ------------------------------------------------------------------ data

def load(name):
    """One export file, or an empty stand-in when it is missing."""
    path = os.path.join(DATA, name + ".json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def hour_tally(stats):
    """How often each count of players has been seen at each hour of the
    day, for all time: {"last": time of the newest row counted, "since":
    of the first, "hours": {"0": {"5": 12, ...}, ...}}. The export keeps
    only recent rows, so every new one is added here once and the old
    ones are never needed again. Kept in the data folder beside the
    export, which the fetch leaves alone."""
    path = os.path.join(DATA, "hour_tally.json")
    tally = {"last": 0, "since": 0, "hours": {}}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                tally = json.load(fh)
        except ValueError:
            pass
    cols = stats.get("columns", [])
    if "users" not in cols:
        return tally
    u = cols.index("users")
    added = 0
    for r in stats.get("hourly", []):
        if not r or len(r) <= u or r[u] is None or r[0] <= tally["last"]:
            continue
        hour = str(numbers.local(r[0]).hour)
        counts = tally["hours"].setdefault(hour, {})
        counts[str(r[u])] = counts.get(str(r[u]), 0) + 1
        tally["last"] = r[0]
        tally["since"] = tally["since"] or r[0]
        added += 1
    if added:
        with open(path + ".new", "w", encoding="utf-8") as fh:
            json.dump(tally, fh)
        os.replace(path + ".new", path)
    return tally


def site_visits():
    """The website's own visits, or None when there is no log to read."""
    try:
        return visits.page(visits.tally(DATA))
    except Exception as e:          # a stats panel must never stop the build
        print("visits:", e)
        return None


def crumbs(slug, pages):
    """The breadcrumb for a content page, top first: [(title, url)]."""
    trail, seen = [], {slug}
    up = PARENT.get(slug)
    while up:
        if isinstance(up, tuple):
            trail.insert(0, up)
            if up == WEBHISTORY:
                trail.insert(0, HISTORY)
            break
        if up in seen or up not in pages:
            break
        seen.add(up)
        trail.insert(0, (pages[up]["title"], "/%s/" % up))
        up = PARENT.get(up)
    return trail


def day(ts):
    if not ts:
        return ""
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%-d %B %Y")


def stamp(ts):
    """The export's time, for the snapshot note: the site is rebuilt every
    hour, so the hour matters."""
    if not ts:
        return ""
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%-d %B %Y, %H:%M UTC")


def duration(seconds):
    if not seconds:
        return ""
    h, m = divmod(int(seconds) // 60, 60)
    return "%d h %d min" % (h, m) if h else "%d min" % m


# include/level.h, highest first
ROLES = [(50, "God"), (42, "Driver Wizards"), (40, "Arch Wizards"),
         (35, "High Wizards"), (33, "Retired Arch Wizards"),
         (30, "Retired High Wizards")]


def roles(staff):
    """Admins grouped by their level's role, empty roles left out."""
    groups = []
    for i, (low, name) in enumerate(ROLES):
        high = ROLES[i - 1][0] if i else 1000
        people = sorted((s for s in staff if low <= s.get("level", 0) < high),
                        key=lambda s: -(s.get("seen") or 0))
        if people:
            groups.append((name, people))
    return groups


ACTIVE = 365 * 86400    # an admin seen within a year of the snapshot


def last_seen(s):
    """The day an admin was last seen: the export's own figure, or for an
    older export the login day plus the length of that session."""
    return s.get("last_seen") or (s.get("last_login") or 0) + (s.get("last_session") or 0)


def split_staff(staff, now):
    """(active, inactive): each a list of role groups."""
    staff = [dict(s, seen=last_seen(s)) for s in staff]
    active = [s for s in staff if s["seen"] >= now - ACTIVE]
    inactive = [s for s in staff if s not in active]
    return roles(active), roles(inactive)


def quest_title(q):
    """The quest room's line, without its own '(N points, by X)' tail."""
    line = (q.get("line") or "").strip()
    line = re.sub(r"\s*\(\d+\s+points?(,\s*by\s+[^)]*)?\)\s*$", "", line)
    return line or q.get("name", "")


# ------------------------------------------------------------- content

def content_pages():
    """content/*.html: '<!-- title: X -->' then the page body."""
    pages = {}
    folder = os.path.join(ROOT, "content")
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".html"):
            continue
        with open(os.path.join(folder, f), encoding="utf-8") as fh:
            text = fh.read()
        m = re.search(r"<!--\s*title:\s*(.*?)\s*-->", text)
        pages[f[:-5]] = {"title": m.group(1) if m else f[:-5], "body": text}
    return pages


# guild name in the game's help -> its page under content/guilds/
GUILD_PAGES = {"Vikings guild": "vikings", "The Holy Monks Order": "monks",
               "Alchemists": "alchemy", "Strigoi": "strigoi",
               "Chefs Guild": "chefs", "Cult of Cthulhu": "cthulhu",
               "Druids": "druids", "Champions of Khorne": "khorne",
               "Kitten guild": "kittens", "Damneds": "damneds",
               "Adventurers guild": "adventurers", "Dark": "dark",
               "Lepers": "lepers", "The Assembly of Knights": "knights",
               "The Hunters Guild": "hunters", "Simyarin": "simyarin",
               "Prophets": "prophets", "Vampires guild": "vampires",
               "The Masters of NannyMUD": "masters"}


def versioned(path):
    """A static file's URL with a hash of the file, so a picture replaced
    under the same name gets a new URL past any cache (Cloudflare keeps
    /static/ for hours)."""
    full = os.path.join(ROOT, path.lstrip("/"))
    try:
        with open(full, "rb") as fh:
            return path + "?v=" + hashlib.sha1(fh.read()).hexdigest()[:10]
    except OSError:
        return path


def guild_pages():
    """content/guilds/<slug>.html, and the pictures for each one:
    static/img/guilds/<slug>-1.jpg, -2.png and so on, in order."""
    folder = os.path.join(ROOT, "content", "guilds")
    imgs = os.path.join(ROOT, "static", "img", "guilds")
    found = sorted(os.listdir(imgs)) if os.path.isdir(imgs) else []
    pages = {}
    for f in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not f.endswith(".html"):
            continue
        slug = f[:-5]
        with open(os.path.join(folder, f), encoding="utf-8") as fh:
            text = fh.read()
        m = re.search(r"<!--\s*title:\s*(.*?)\s*-->", text)
        pics = [i for i in found if re.fullmatch(r"%s-\d+\.(jpe?g|png|gif|webp)" % slug, i)]
        pics.sort(key=lambda i: int(re.search(r"-(\d+)\.", i).group(1)))
        clip = "%s-clip.mp4" % slug
        poster = "%s-clip.jpg" % slug
        thumb = "%s-thumb.jpg" % slug
        pages[slug] = {"title": m.group(1) if m else slug, "body": text,
                       # a short looping clip shown at the end of the page
                       "clip": versioned("/static/img/guilds/" + clip) if clip in found else None,
                       "poster": versioned("/static/img/guilds/" + poster) if poster in found else None,
                       # small crop of the art for the /guilds/ list
                       "thumb": versioned("/static/img/guilds/" + thumb) if thumb in found else None,
                       # big files are artwork, shown wide; small ones are
                       # the old sites' banners, shown as they are
                       "images": [{"src": versioned("/static/img/guilds/" + i),
                                   "art": os.path.getsize(os.path.join(imgs, i)) > 100000}
                                  for i in pics]}
        # the guild art leads the page, the rest go at the end
        pages[slug]["later"] = pages[slug]["images"][1:]
        pages[slug]["images"] = pages[slug]["images"][:1]
    return pages


def times_issues():
    """times/YYYY_MM/pageN, plain text, page 1 is the index."""
    folder = os.path.join(ROOT, "times")
    issues = []
    for d in sorted(os.listdir(folder)):
        path = os.path.join(folder, d)
        if not os.path.isdir(path):
            continue
        pages = sorted((f for f in os.listdir(path) if re.fullmatch(r"page\d+", f)),
                       key=lambda f: int(f[4:]))
        texts = []
        for p in pages:
            with open(os.path.join(path, p), encoding="latin-1") as fh:
                texts.append((int(p[4:]), fh.read().rstrip()))
        year, month = d.split("_")
        try:
            label = dt.date(int(year), int(month), 1).strftime("%B %Y")
        except ValueError:
            label = year
        issues.append({"id": d, "label": label, "year": year, "pages": texts})
    return issues


def lightbox(html):
    """Every picture that links to its own file opens over the page
    instead: a hidden copy, shown by CSS while its #id is the target.
    Clicking it goes to #close, which matches nothing, so it hides."""
    def zoom(m):
        src, attrs = m.group(1), m.group(2)
        zid = "zoom-" + hashlib.sha1(src.encode()).hexdigest()[:8]
        alt = re.search(r'alt="[^"]*"', attrs)
        return ('<a href="#%s"><img %s></a><a id="%s" class="nm-zoom" href="#close">'
                '<img src="%s" %s loading="lazy"></a>'
                % (zid, attrs, zid, src, alt.group(0) if alt else 'alt=""'))
    return re.sub(r'<a href="(/static/img/[^"#]+)"><img ([^>]*)></a>', zoom, html)


def describe(page):
    """A search engine description: the first real paragraph of the
    page's main content, cut at a word near 155 characters."""
    main = page.split("<main", 1)[-1]
    for attrs, p in re.findall(r"<p(\s[^>]*)?>(.*?)</p>", main, re.S):
        if "nm-snapshot" in attrs:
            continue
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", " ", p)))).strip()
        if len(text) >= 40:
            if len(text) > 155:
                text = text[:155].rsplit(" ", 1)[0] + "..."
            return text
    return DESCRIPTION


def help_description(name, text):
    """The DESCRIPTION section of an in-game help file, as one line."""
    m = re.search(r"^DESCRIPTION\s*\n(.*?)(?:\n[A-Z][A-Z ]+\n|\Z)", text, re.S | re.M)
    body = re.sub(r"\s+", " ", m.group(1) if m else text).strip()
    if len(body) > 155:
        body = body[:155].rsplit(" ", 1)[0] + "..."
    return body or "NannyMUD help on %s." % name


# ---------------------------------------------------------------- build

def main():
    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, "templates")),
                      autoescape=select_autoescape(["html"]))
    # the skin picker in the header and footer (templates/_theme_pick.html)
    env.globals["theme_preview"] = True
    env.globals["versioned"] = versioned
    env.filters["day"] = day
    env.filters["lightbox"] = lightbox
    env.filters["duration"] = duration
    env.filters["quest_title"] = quest_title

    quests = load("quests")
    puzzles = load("puzzles")
    staff = load("staff")
    areas = load("areas")
    guilds = load("guilds")
    helps = load("help")
    stats = load("stats")
    pages = content_pages()
    issues = times_issues()

    generated = max([d.get("generated", 0) for d in
                     (quests, staff, areas, guilds, helps, stats)] or [0])
    # a hash of the stylesheet in its link, so a changed file gets a new
    # URL and no cache (Cloudflare keeps static files for hours) serves
    # the old one
    # one hash over every stylesheet, skins included: nginx serves the
    # skin behind the one nanny.css URL, so any change must bust it
    digest = hashlib.sha1()
    for folder, _, files in sorted(os.walk(os.path.join(ROOT, "static", "css"))):
        for f in sorted(files):
            with open(os.path.join(folder, f), "rb") as fh:
                digest.update(f.encode() + fh.read())
    digest.update(b"skins-1")   # bump to force a new URL past any cache
    css_version = digest.hexdigest()[:10]
    common = {"nav": NAV, "wiki": WIKI, "site": SITE, "discord": DISCORD,
              "css_version": css_version, "updated": stamp(generated),
              "year": dt.date.today().year}

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "static"), os.path.join(OUT, "static"))

    def write(path, template, sitemap=True, **kw):
        target = os.path.join(OUT, path.strip("/"), "index.html")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        html_text = env.get_template(template).render(current=path, **common, **kw)
        desc = kw.get("description") or (DESCRIPTION if path == "/" else describe(html_text))
        html_text = html_text.replace("__DESC__", html.escape(desc, quote=True))
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(html_text)
        if sitemap:
            written.append(path)

    written = []

    hourly = stats.get("hourly", [])
    recent = hourly[-24:]
    facts = {
        "quests": len(quests.get("open", [])),
        "quest_points": quests.get("open_points", 0),
        "areas": len(areas.get("areas", [])),
        "guilds": len(guilds.get("guilds", [])),
        "online_avg": round(sum(s[1] for s in recent) / len(recent)) if recent else None,
        "online_peak": max((s[1] for s in recent), default=None),
    }

    tiles = {
        "Play": "How to connect, which client to use, and your first steps.",
        "World": "Over 50,000 locations built by its wizards, every open area, and maps of the mainland and Antharis.",
        "Quests": "Every quest in the game, its points, its maintainer and a hint.",
        "Puzzles": "The puzzles of every open area, and the charms they earn in the Charmers club.",
        "Guilds": "Every guild in the game, and what it is like to play.",
        "Help": "The help pages players read in the game, and the Newbie Booklet.",
        "Times": "The mud's own newspaper, every issue from 1996 to 2010.",
        "History": "How NannyMUD began, its time line, and the people who made it.",
        "Admins": "The admins who run the game, past and present, and when they were last seen.",
        "Stats": "Players online, uptime, the main shop and the money in the game.",
        "Wiki": "Pages written by the players themselves.",
    }
    write("/", "home.html", facts=facts, page_title=None, snapshot=True, tiles=tiles)
    write("/play/", "page.html", page_title="Play NannyMUD",
          body=env.get_template("play.html").render(**common))
    write("/play/mudlet/", "page.html", page_title="Mudlet for NannyMUD",
          crumbs=[("Play", "/play/")],
          body=env.get_template("play_mudlet.html").render(**common))
    write("/play/tintin/", "page.html", page_title="TinTin++ for NannyMUD",
          crumbs=[("Play", "/play/")],
          body=env.get_template("play_tintin.html").render(**common))
    every_quest = quests.get("open", []) + quests.get("closed", [])
    most = max(every_quest, key=lambda q: q.get("solved") or 0, default=None)
    latest = max(every_quest, key=lambda q: q.get("last_solved") or 0, default=None)
    write("/quests/", "quests.html", page_title="Quests", snapshot=True,
          most_solved=most if most and most.get("solved") else None,
          last_solved=latest if latest and latest.get("last_solved") else None,
          open=quests.get("open", []), closed=quests.get("closed", []),
          total=quests.get("open_points", 0))
    write("/puzzles/", "puzzles.html", page_title="Puzzles", snapshot=True,
          # the original areas first, then the wizards' areas by name
          areas=sorted([a for a in puzzles.get("areas", []) if a.get("open")],
                       key=lambda a: ({"mainland": 0, "antharis": 1}.get(a.get("area"), 2), a.get("area", ""))),
          open_count=puzzles.get("open", 0), charm_count=puzzles.get("charms", 0))
    booklets = load("booklets").get("booklets", {})
    open_names = {a.lower() for a in areas.get("areas", [])}
    write("/world/", "world.html", page_title="The World", snapshot=True,
          areas=areas.get("areas", []), booklets=booklets,
          other_booklets=sorted(w for w in booklets if w not in open_names),
          intro=pages.get("the-world", {}).get("body", ""))
    # a booklet gets a page only when its wizard's area is open: the
    # others are named on the World page, without a link
    for wiz, book in booklets.items():
        if wiz not in open_names:
            continue
        write("/world/%s/" % wiz, "booklet.html", snapshot=True,
              page_title="%s's tourist booklet" % wiz.capitalize(),
              wiz=wiz.capitalize(), chapters=book.get("chapters", []),
              antharis=book.get("antharis", []))
    gpages = guild_pages()
    write("/guilds/", "guilds.html", page_title="Guilds", snapshot=True,
          guilds=[dict(g, page="/guilds/%s/" % GUILD_PAGES[g["name"]]
                       if GUILD_PAGES.get(g["name"]) in gpages else None,
                       thumb=gpages.get(GUILD_PAGES.get(g["name"]), {}).get("thumb"))
                  for g in sorted(guilds.get("guilds", []),
                                  key=lambda g: re.sub(r"^the\s+", "", g["name"].lower()))])
    for slug, page in gpages.items():
        write("/guilds/%s/" % slug, "guild.html", page_title=page["title"], page=page)
    topics = helps.get("topics", {})
    tree = {}
    for name in topics:
        top, _, sub = name.partition("/")
        tree.setdefault(top, [])
        if sub:
            tree[top].append(sub)
    write("/help/", "help.html", page_title="Help", snapshot=True,
          topics=sorted((t, sorted(subs)) for t, subs in tree.items()),
          extra=[(pages[s]["title"], "/" + s + "/") for s in
                 ("faq", "newbie-booklet", "introduction", "the-game") if s in pages])
    for name, text in topics.items():
        write("/help/%s/" % name, "help_topic.html", page_title="Help: " + name.replace("/", " ").replace("_", " "), snapshot=True,
              name=name, text=text, description=help_description(name, text))
    write("/staff/", "staff.html", page_title="Administration", snapshot=True,
          **dict(zip(("active", "inactive"),
                     split_staff(staff.get("staff", []), staff.get("generated", 0)))))
    numbers_page = numbers.page(stats, hour_tally(stats))
    attend = attendance.page(load("attendance"), guild_slugs=set(gpages.keys()))
    stats_crumb = [("Stats", "/stats/")]
    write("/stats/", "stats_index.html", page_title="Stats", snapshot=True,
          totals=[("Open quests", len(quests.get("open", []))),
                  ("Closed quests", len(quests.get("closed", []))),
                  ("Quest points", quests.get("total_points", 0)),
                  ("Open areas", len(areas.get("areas", []))),
                  ("Guilds", len(guilds.get("guilds", []))),
                  ("Help topics", len(helps.get("topics", {}))),
                  ("Times issues", len(issues))])
    write("/stats/players/", "stats_players.html", page_title="Players", snapshot=True,
          crumbs=stats_crumb, players=numbers_page["players"], attendance=attend)
    write("/stats/market/", "stats_market.html", page_title="Market", snapshot=True,
          crumbs=stats_crumb, shops=numbers_page["shops"], wealth=numbers_page["wealth"])
    write("/stats/driver/", "stats_driver.html", page_title="Driver", snapshot=True,
          crumbs=stats_crumb, uptime=numbers_page["uptime"],
          driver_version=stats.get("driver_version"), driver=numbers_page["driver"])
    # not linked from anywhere, and kept out of the sitemap: a visitor
    # count is not something to put in front of players
    write("/stats/visits/", "stats_visits.html", page_title="Website visits",
          visits=site_visits(), sitemap=False, noindex=True)
    # the toplists and the wizards' tables, under tabs of the Stats page
    tops = load("tops")

    def prep(t):
        """A sheet drawn as the mud would: a box of text, the first five
        rows open, the rest under 'show all'."""
        t = dict(t)
        # a sheet's own time only when it is older than the export: a
        # wizard's last good sheets, kept while their export is broken
        old = (t.get("at") or 0) < (tops.get("generated") or 0) - 3600
        t["at_text"] = stamp(t.get("at")) if old else ""
        if t.get("text"):               # a map or a drawing, as written
            t["sheet"], t["sheet_all"], t["count"] = t["text"].rstrip("\n"), "", 0
            return t
        rows, cols = t.get("rows", []), t.get("columns", [])
        numeric = [bool(rows) and all(isinstance(r[i], (int, float))
                                      for r in rows if len(r) > i)
                   for i in range(len(cols))]

        def text(v):
            return "{:,}".format(v) if isinstance(v, (int, float)) else str(v)

        head = ["#"] + [str(c) for c in cols]
        # equal scores share a place, as the game's plaques show them: the
        # place only where the score (the last column) changes
        body, last = [], object()
        for n, r in enumerate(rows, 1):
            score = r[-1] if r and numeric[-1] else object()
            body.append([str(n) if score != last else ""] + [text(v) for v in r])
            last = score
        right = [True] + numeric
        width = [max([len(head[i])] + [len(r[i]) for r in body if len(r) > i])
                 for i in range(len(head))]
        # "across": the rows in blocks side by side, each read downwards
        across = t.get("across") if isinstance(t.get("across"), int) else 1
        across = max(1, min(across, len(body) or 1))
        height = -(-len(body) // across)
        n = len(head)

        def cell(i, c):
            return c.rjust(width[i]) if right[i] else c.ljust(width[i])

        def line(blocks):
            return "│ " + " ║ ".join(" │ ".join(cell(i, c) for i, c in enumerate(cells))
                                     for cells in blocks) + " │"

        def rule(l, m, d, r):
            one = m.join("─" * (w + 2) for w in width)
            return l + d.join([one] * across) + r

        def lines(k):
            out = []
            for j in range(k):
                blocks = [body[b * height + j] if b * height + j < len(body)
                          else [""] * n for b in range(across)]
                out.append(line(blocks))
            return out

        top = [rule("┌", "┬", "╥", "┐"), line([head] * across),
               rule("├", "┼", "╫", "┤")]
        bottom = rule("└", "┴", "╨", "┘")
        if across > 1:                  # shown whole: blocks do not fold
            t["sheet"] = "\n".join(top + lines(height) + [bottom])
            t["sheet_all"] = ""
        else:
            t["sheet"] = "\n".join(top + lines(min(5, height)) + [bottom])
            t["sheet_all"] = ("\n".join(top + lines(height) + [bottom])
                              if len(body) > 5 else "")
        t["count"] = len(body)
        return t

    def by_wizard(tables):
        groups = {}
        for t in tables:
            groups.setdefault(t.get("wizard") or "", []).append(prep(t))
        return sorted(groups.items(), key=lambda g: g[0].lower())

    mud = [prep(t) for t in tops.get("mud", [])]
    write("/stats/tops/", "stats_tables.html", page_title="Toplists",
          snapshot=True, active="tops", crumbs=stats_crumb,
          intro="The game's own toplists, as far down as the game shows them.",
          groups=[(None, mud)] if mud else [],
          empty="The toplists show here once the mud exports them.")
    write("/stats/clubs/", "stats_tables.html", page_title="Clubs",
          snapshot=True, active="clubs", crumbs=stats_crumb,
          intro="Information sheets the clubs keep, given by the wizards who run them.",
          groups=[("Kept by " + w, ts) for w, ts in by_wizard(tops.get("clubs", []))],
          empty="No club has given the website an information sheet yet.")
    areas = by_wizard(tops.get("areas", []))
    write("/stats/areas/", "stats_tables.html", page_title="Areas",
          snapshot=True, active="areas", crumbs=stats_crumb,
          intro="Information sheets from the wizards' own areas, a page for each wizard.",
          index=[(w, len(ts)) for w, ts in areas], groups=[],
          empty="No area has given the website an information sheet yet.")
    for w, ts in areas:
        write("/stats/areas/%s/" % w.lower(), "stats_tables.html",
              page_title=w + "'s area", snapshot=True, active="areas",
              crumbs=stats_crumb + [("Areas", "/stats/areas/")],
              groups=[(None, ts)], empty="")
    write("/times/", "times.html", page_title="The NannyMUD Times", issues=issues)
    for issue in issues:
        write("/times/%s/" % issue["id"], "times_issue.html",
              page_title="NannyMUD Times, " + issue["label"], issue=issue,
              description="The NannyMUD Times of %s, the mud's own newspaper, "
                          "written by its players and wizards." % issue["label"])
    write("/history/", "history.html", page_title="History",
          links=[(pages[s]["title"], "/" + s + "/") for s in
                 ("the-beginnings", "timeline", "musings", "events", "the-people",
                  "pictures") if s in pages])
    # the old site's own pages, kept as they were, each dated
    write("/history/old-web/", "history_web.html", page_title="Old web presence",
          crumbs=[HISTORY],
          links=[(pages[s]["title"], "/" + s + "/") for s in
                 ("attendance", "guild-statistics", "where-players-come-from",
                  "other-topics", "old-art") if s in pages])
    for slug, page in pages.items():
        if slug in MOVED:
            continue
        body = page["body"]
        for old, new in MOVED.items():
            body = body.replace('href="/%s/' % old, 'href="%s' % new)
        write("/%s/" % slug, "page.html", page_title=page["title"], body=body,
              crumbs=crumbs(slug, pages))
    # old addresses keep working, and short ones lead out: a page that
    # sends the visitor on
    for old, new in list(MOVED.items()) + list(SHORT.items()):
        full = new if new.startswith("http") else SITE + new
        target = os.path.join(OUT, old, "index.html")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write('<!doctype html><meta charset="utf-8"><title>NannyMUD</title>'
                     '<link rel="canonical" href="%s">'
                     '<meta http-equiv="refresh" content="0; url=%s">'
                     '<a href="%s">%s</a>\n' % (full, new, new, full))
    with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for path in written:
            fh.write("  <url><loc>%s%s</loc></url>\n" % (SITE, html.escape(path)))
        fh.write("</urlset>\n")
    with open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8") as fh:
        fh.write("User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % SITE)
    # the site's header and footer for the wiki: nginx puts them around
    # every wiki page (docker/nginx.conf, location = /w/index.php)
    os.makedirs(os.path.join(OUT, "_wiki"), exist_ok=True)
    for part in ("header", "footer"):
        with open(os.path.join(OUT, "_wiki", part + ".html"), "w", encoding="utf-8") as fh:
            fh.write(env.get_template("_%s.html" % part).render(current=WIKI, **common))
    print("built %d pages into %s" % (sum(len(f) for _, _, f in os.walk(OUT)), OUT))


if __name__ == "__main__":
    main()
