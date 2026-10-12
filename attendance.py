"""Players seen, from the mud's attendance.json: how many characters
exist, how many were seen each day, and how that splits by guild and by
country. Counts only, never a player's name.

This is the one place that reads attendance.json's shape (version 1):

    totals: {characters, active_ever, active_7d, active_30d, active_365d}
    daily: [[day, distinct players that day, logins that day], ...],
           oldest first, up to 400 days, only days that were recorded
    guilds: [{id, name, members_ever, active_7d, active_30d, active_365d}, ...]
    countries: [{code, name, active_7d, active_30d, active_365d, ever}, ...]
    countries_updated: unix time of the last finished daily rescan, or
           missing/null before the first one
    the active_* fields are level 2 and up; a country's "ever" counts
    every character at any level by their last login, so it sums to
    totals.characters

The file may not exist yet, or may be an earlier or later shape than
this; every part below is read defensively and turns into None or
"have": False (the template prints "No data yet.") rather than a build
error. When the schema changes, this module is the only place that
needs to follow it.
"""
import datetime as dt
import html
import json
import os
import re

from stats import dual_chart, line_chart, noon

# the three windows the page offers, and the export's field for each
WINDOWS = [("Week", "active_7d"), ("Month", "active_30d"), ("Year", "active_365d")]
# the map and its own table add a fourth: everyone ever seen, by the
# country of their last login
MAP_WINDOWS = WINDOWS + [("All time", "ever")]
TOP_COUNTRIES = 15

# the export's guild id, where it differs from the /guilds/ page's own
# slug (build.py's GUILD_PAGES); every other id is tried as the slug
# itself, and "none" or an id with no page of its own is left unlinked
GUILD_SLUG = {"adv_guild": "adventurers"}

MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "world-map.svg")
CODE = re.compile(r"^[a-z]{2}$")
# a country's share of the window's top value, highest tier first
TIERS = [(0.5, "92%"), (0.2, "68%"), (0.05, "44%"), (0, "24%")]
# the same four tiers, weakest first, as the map legend reads them
LEGEND_LABELS = [("24%", "Least"), ("44%", "Some"), ("68%", "More"), ("92%", "Most")]
_map_svg = None


def base_map():
    """The vendored world outline, read once. None if it is missing."""
    global _map_svg
    if _map_svg is None:
        try:
            with open(MAP_PATH, encoding="utf-8") as fh:
                _map_svg = fh.read()
        except OSError:
            _map_svg = ""
    return _map_svg or None


def day_text(iso):
    try:
        return dt.date.fromisoformat(iso).strftime("%-d %B %Y")
    except (TypeError, ValueError):
        return ""


def stamp_text(ts):
    """A unix time (countries_updated) as a plain date; empty without one."""
    try:
        return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%-d %B %Y")
    except (TypeError, ValueError, OSError):
        return ""


def since_caption(iso):
    """The caption above the daily chart: no login has been counted yet
    until the export's first day, so there is nothing to date."""
    text = day_text(iso)
    return "Counted since %s." % text if text else "Counting starts soon."


def daily_periods(daily):
    """The attendance daily chart's Week/Month/Year panes: players seen
    and logins, each day, for the last 7, 30 or 365 recorded days. None
    in a pane with fewer than two days to draw a line between."""
    def pane(rows):
        if len(rows) < 2:
            return None
        seen = [(noon(dt.date.fromisoformat(d)), v) for d, v, _ in rows]
        logins = [(noon(dt.date.fromisoformat(d)), k) for d, _, k in rows]
        return (dual_chart(seen, logins, "Players seen and logins, each day",
                           "players seen", "logins", str, str)
                or line_chart(seen, "Players seen each day"))
    return [(label, pane(daily[-n:])) for label, n in (("Week", 7), ("Month", 30), ("Year", 365))]


def ranked(rows, key, tiebreak):
    """rows sorted by key (the chosen window), highest first, equal
    scores broken by tiebreak (also highest first)."""
    return sorted(rows, key=lambda r: (-(r.get(key) or 0), -(r.get(tiebreak) or 0)))


def guild_href(gid, guild_slugs):
    """The guild's own /guilds/ page, or None when it has none (closed
    guilds, "none" for no guild, or an id the site does not know)."""
    slug = GUILD_SLUG.get(gid, gid)
    return "/guilds/%s/" % slug if guild_slugs and slug in guild_slugs else None


def country_name(c):
    """The export sends country names upper case; title-cased for
    display (small words such as 'of' are not worth special-casing)."""
    return str(c.get("name", "")).title()


def table_rows(rows, key, extra, guild_slugs=None, country=False):
    """A guild or country table's body rows for one window: name, the
    window's count and the all-time count, highest first. A guild name
    links to its /guilds/ page when guild_slugs says there is one; a
    country name is title-cased. Escaped by hand since this whole
    section is built outside Jinja."""
    out = []
    for r in ranked(rows, key, extra):
        name = html.escape(country_name(r) if country else str(r.get("name", "")))
        href = guild_href(r.get("id", ""), guild_slugs) if guild_slugs is not None else None
        if href:
            name = '<a href="%s">%s</a>' % (href, name)
        out.append("<tr><td>%s</td><td class=\"nm-num\">%s</td><td class=\"nm-num\">%s</td></tr>"
                   % (name, "{:,}".format(r.get(key) or 0), "{:,}".format(r.get(extra) or 0)))
    return "".join(out)


def map_tiers(countries, key):
    """[(css colour, [country ids]), ...] for one window, strongest
    first; a country already claimed by a stronger tier is left out of
    the weaker ones. Empty when nothing in `countries` has a count."""
    top = max((c.get(key) or 0) for c in countries) if countries else 0
    if not top:
        return []
    claimed, out = set(), []
    for ratio, colour in TIERS:
        ids = []
        for c in countries:
            code = str(c.get("code", "")).lower()
            v = c.get(key) or 0
            if v > 0 and v / top > ratio and code not in claimed and CODE.fullmatch(code):
                ids.append(code)
                claimed.add(code)
        if ids:
            out.append((colour, ids))
    return out


def map_style(tiers, gid, index):
    """The <style> rules that colour the shared map for one Week/Month/
    Year radio: only in effect while that radio is checked."""
    prefix = "#%s-%d:checked ~ .nm-worldmap " % (gid, index)
    return "".join("%s#%s{fill:color-mix(in srgb, var(--nm-accent) %s, var(--nm-rule-soft))}"
                   % (prefix, cid, colour)
                   for colour, ids in tiers for cid in ids)


def fact_block(totals, key, label):
    if not totals:
        return '<p class="nm-muted">No data yet.</p>'
    return ('<div class="nm-facts">'
           '<div class="nm-fact"><b>{:,}</b><span>characters, ever</span></div>'
           '<div class="nm-fact"><b>{:,}</b><span>played, last {}</span></div>'
           '<div class="nm-fact"><b>{:,}</b><span>played at all</span></div>'
           '</div>').format(totals.get("characters") or 0, totals.get(key) or 0,
                            label.lower(), totals.get("active_ever") or 0)


def sheet_block(rows, key, label, head, title, guild_slugs=None):
    if not rows:
        return "<h3>%s</h3><p class=\"nm-muted\">No data yet.</p>" % title
    body = table_rows(rows, key, "members_ever", guild_slugs)
    return ('<h3>%s</h3><div class="nm-table-wrap"><table class="nm-table"><thead><tr>'
           '<th>%s</th><th class="nm-num">Last %s</th><th class="nm-num">Ever</th>'
           '</tr></thead><tbody>%s</tbody></table></div>' % (title, head, label.lower(), body))


def section(totals, guilds, guild_slugs=None):
    """The 'players seen' block: totals and a guilds table, under one
    shared Week/Month/Year control (they are facets of the same
    window). Built as one HTML string, not Jinja, to match map_section
    below. None when neither part of attendance.json is there."""
    if not totals and not guilds:
        return None
    gid = "players-seen"
    radios = "".join('<input type="radio" name="%s" id="%s-%d" class="nm-period-radio"%s>'
                     % (gid, gid, i, " checked" if i == 1 else "")
                     for i in (1, 2, 3))
    nav = "".join('<label for="%s-%d">%s</label>' % (gid, i, label)
                  for i, (label, _) in enumerate(WINDOWS, 1))
    panes = "".join(
        '<div class="nm-period-pane">%s%s</div>'
        % (fact_block(totals, key, label),
           sheet_block(guilds, key, label, "Guild", "By guild", guild_slugs))
        for label, key in WINDOWS)
    return ('<div class="nm-period">%s<div class="nm-period-nav">%s</div>'
            '<div class="nm-period-panes">%s</div></div>'
            % (radios, nav, panes))


def top_countries_table(countries, key):
    """The top 15 countries for one window/All time: name (title-cased)
    and the count, nothing else — the full breakdown with the all-time
    figure beside it lives in the guild table's sibling style above."""
    rows = ranked(countries, key, "ever")[:TOP_COUNTRIES]
    body = "".join("<tr><td>%s</td><td class=\"nm-num\">%s</td></tr>"
                   % (html.escape(country_name(c)), "{:,}".format(c.get(key) or 0))
                   for c in rows)
    return ('<div class="nm-table-wrap"><table class="nm-table"><thead><tr>'
           '<th>Country</th><th class="nm-num">Players</th>'
           '</tr></thead><tbody>%s</tbody></table></div>' % body)


def map_legend():
    """The swatches for the map's four tiers plus "no record", in the
    same colours attendance.py and worldmap.js both shade countries
    with."""
    swatches = [("None", "var(--nm-rule-soft)")] + [
        (label, "color-mix(in srgb, var(--nm-accent) %s, var(--nm-rule-soft))" % pct)
        for pct, label in LEGEND_LABELS]
    return '<div class="nm-map-legend">%s</div>' % "".join(
        '<span><i style="background:%s"></i>%s</span>' % (colour, label)
        for label, colour in swatches)


def map_data_json(countries):
    """Per-country counts for worldmap.js to colour and hover: ever and
    the three active_* windows, keyed by the lower-case alpha-2 code the
    map and its small-country markers both use. Counts only, nothing
    that identifies a player."""
    out = {}
    for c in countries or []:
        code = str(c.get("code", "")).lower()
        if CODE.fullmatch(code):
            out[code] = {"ever": c.get("ever") or 0,
                        "active_7d": c.get("active_7d") or 0,
                        "active_30d": c.get("active_30d") or 0,
                        "active_365d": c.get("active_365d") or 0}
    return out


def map_section(countries, countries_updated):
    """The map and its own Week/Month/Year/All time control: all time
    (countries[].ever, the country of every character's last login) is
    the new global view and the one this opens on, since it is the
    point of the section; the other three windows are here too so the
    map can also show who has been active lately. None without a usable
    map or without any country data at all."""
    base = base_map()
    if not countries or not base:
        return ('<h3>On the map</h3><p class="nm-muted">No data yet.</p>')
    gid = "players-map"
    radios = "".join('<input type="radio" name="%s" id="%s-%d" class="nm-period-radio"%s>'
                     % (gid, gid, i, " checked" if i == len(MAP_WINDOWS) else "")
                     for i in range(1, len(MAP_WINDOWS) + 1))
    nav = "".join('<label for="%s-%d">%s</label>' % (gid, i, label)
                  for i, (label, _) in enumerate(MAP_WINDOWS, 1))
    css = "".join(map_style(map_tiers(countries, key), gid, i)
                  for i, (label, key) in enumerate(MAP_WINDOWS, 1))
    updated = stamp_text(countries_updated)
    asof = '<p class="nm-muted nm-small">As of %s.</p>' % updated if updated else ""
    # "ever" counts every character at any level, not just the active
    # ones the other three windows count, so it is labelled apart
    alltime_note = ('<p class="nm-muted nm-small">All characters ever, '
                    'by country of their last login.</p>')
    panes = "".join(
        '<div class="nm-period-pane">%s</div>' % top_countries_table(countries, key)
        for _, key in MAP_WINDOWS[:-1]) + (
        '<div class="nm-period-pane">%s%s%s</div>'
        % (alltime_note, asof, top_countries_table(countries, "ever")))
    # the JSON blob is for worldmap.js only (hover/tap figures on the
    # interactive map); "</" is escaped so it cannot close the script
    # tag early, though none of these keys or integers can produce it
    data_json = json.dumps(map_data_json(countries), separators=(",", ":")).replace("</", "<\\/")
    return ('<h3>On the map</h3>'
           '<p class="nm-muted nm-small">Shaded by how many were seen, least to most; '
           'a blank country has none on record.</p>%s'
           '<div class="nm-period">%s<div class="nm-period-nav">%s</div>'
           '<div class="nm-worldmap">%s</div>'
           '<script type="application/json" id="nm-worldmap-data">%s</script>'
           '<style>%s</style>'
           '<div class="nm-period-panes">%s</div></div>'
           % (map_legend(), radios, nav, base, data_json, css, panes))


def page(data, guild_slugs=None):
    """Everything the Players page shows from attendance.json.
    guild_slugs is the set of /guilds/<slug>/ pages that exist, from
    build.py's own guild_pages(): a guild row links to its page only
    when its (mapped) id is in there."""
    if not data:
        return {"have": False}
    totals = data.get("totals")
    daily = data.get("daily") or []
    guilds = data.get("guilds")
    countries = data.get("countries")
    return {
        "have": True,
        "since_caption": since_caption(data.get("since")),
        "daily_periods": daily_periods(daily) if len(daily) >= 2 else None,
        "section": section(totals, guilds, guild_slugs),
        "map_section": map_section(countries, data.get("countries_updated")),
    }
