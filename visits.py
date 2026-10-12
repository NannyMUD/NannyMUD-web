"""Visits to the website, counted from the web server's own log.

The front nginx writes a small log for the site (nanny.thorn.vip-visits.log,
rotated daily, ten days kept), with the visitor's address as Cloudflare
passes it on. Every build reads what is there and keeps, per day, only
counts: page views, distinct visitors, the pages and the sites that sent
people here. No address is stored; the visitors of a day are counted in
memory and only the number is kept, in visits.json in the data folder,
so the days stay after the log has rotated them away.
"""

import collections
import datetime as dt
import glob
import gzip
import json
import os
import re

from stats import TZ, bars, line_chart

LOGS = os.environ.get("NANNY_VISIT_LOGS", "/hostlogs/nanny.thorn.vip-visits.log")
SITE_HOST = "nanny.thorn.vip"
KEEP = 50                       # pages and referrers kept a day

# not a page: the site's files, the wiki's machinery, the favicon
NOT_PAGE = re.compile(r"\.(css|js|png|jpe?g|gif|svg|ico|webp|mp4|webm|woff2?|ttf|json|xml|txt|map)$"
                      r"|^/w/|^/static/|^/favicon", re.I)
BOT = re.compile(r"bot|crawl|spider|slurp|curl|wget|python|httpx|go-http|java/|"
                 r"monitor|uptime|preview|facebookexternal|headless|scan|feed", re.I)


def log_lines():
    for path in sorted(glob.glob(LOGS + "*")):
        opener = gzip.open if path.endswith(".gz") else open
        try:
            with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
                yield from fh
        except OSError:
            continue


def count():
    """{day: {"views", "visitors", "pages", "referrers"}} from the logs."""
    views = collections.Counter()
    who = collections.defaultdict(set)
    pages = collections.defaultdict(collections.Counter)
    refs = collections.defaultdict(collections.Counter)
    for line in log_lines():
        f = line.rstrip("\n").split("\t")
        if len(f) < 8:
            continue
        msec, ip, _, status, method, uri, ref, ua = f[:8]
        if method != "GET" or status not in ("200", "304") or BOT.search(ua):
            continue
        path = uri.split("?", 1)[0]
        if NOT_PAGE.search(path):
            continue
        try:
            day = dt.datetime.fromtimestamp(float(msec), TZ).date().isoformat()
        except ValueError:
            continue
        views[day] += 1
        who[day].add((ip, ua))
        pages[day][path] += 1
        host = re.sub(r"^https?://([^/:]+).*", r"\1", ref) if ref not in ("", "-") else ""
        if host and host != SITE_HOST and not host.endswith("." + SITE_HOST):
            refs[day][host] += 1
    return {d: {"views": views[d], "visitors": len(who[d]),
                "pages": dict(pages[d].most_common(KEEP)),
                "referrers": dict(refs[d].most_common(KEEP))}
            for d in views}


def tally(data_dir):
    """The kept days, with what the logs hold now added in. A day the
    logs cover only in part, once its first hours have rotated away,
    never replaces the fuller count already kept."""
    path = os.path.join(data_dir, "visits.json")
    kept = {"days": {}}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                kept = json.load(fh)
        except ValueError:
            pass
    changed = False
    for day, c in count().items():
        old = kept["days"].get(day)
        if not old or c["views"] >= old["views"]:
            if old != c:
                kept["days"][day] = c
                changed = True
    if changed:
        with open(path + ".new", "w", encoding="utf-8") as fh:
            json.dump(kept, fh)
        os.replace(path + ".new", path)
    return kept


def page(kept, now=None):
    """What the Stats page shows: the last 30 days, and a chart of
    visitors a day since counting began. None before the first day."""
    days = sorted(kept.get("days", {}).items())
    if len(days) < 2:               # nothing worth showing before a second day
        return None
    today = (now or dt.datetime.now(TZ)).date()
    since = (today - dt.timedelta(days=30)).isoformat()
    month = [(d, c) for d, c in days if d > since]
    pages, refs = collections.Counter(), collections.Counter()
    for _, c in month:
        pages.update(c["pages"])
        refs.update(c["referrers"])

    def noon(d):
        return dt.datetime.fromisoformat(d).replace(hour=12, tzinfo=TZ).timestamp()

    return {
        "since": dt.date.fromisoformat(days[0][0]).strftime("%-d %B %Y"),
        "views": sum(c["views"] for _, c in month),
        "visitors_day": round(sum(c["visitors"] for _, c in month) / len(month)) if month else 0,
        "today": dict(days[-1][1]) if days[-1][0] == today.isoformat() else None,
        "chart": line_chart([(noon(d), c["visitors"]) for d, c in days], "visitors"),
        "pages": bars(pages.most_common(10)),
        "referrers": bars(refs.most_common(8)),
    }
