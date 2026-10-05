"""The numbers behind the Stats page, worked out from stats.json.

stats.json carries an hourly sample of the game (players on, money,
inflation, the gold the main shop paid out and the items it bought), imfd's wealth figures with their
daily history, and the boot time and every boot the mud has logged.
Everything here is arithmetic on
those; the charts are inline SVG drawn now, so the page needs no script.
"""
import datetime as dt
import html
import math
import statistics
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")       # the mud's own clock
YEAR = 365 * 86400


def local(ts):
    return dt.datetime.fromtimestamp(ts, TZ)


def gold(n):
    return "{:,}".format(int(n or 0))


def span(seconds):
    """'12 days 4 h', '5 h 20 min', '7 min'."""
    seconds = int(seconds or 0)
    d, rest = divmod(seconds, 86400)
    h, rest = divmod(rest, 3600)
    m = rest // 60
    if d:
        return "%d day%s %d h" % (d, "" if d == 1 else "s", h)
    if h:
        return "%d h %d min" % (h, m)
    return "%d min" % m


# ---------------------------------------------------------------- charts

def line_chart(points, label, fmt=str):
    """An SVG line for (time, value) pairs, with the top value and the
    first and last day as labels. None when there is nothing to draw.
    Drawn twice, wide and narrow; the CSS shows the narrow one on phones,
    where the wide one's text would shrink too small to read."""
    pts = [(t, v) for t, v in points if v is not None]
    if len(pts) < 2:
        return None
    return (draw_line(pts, label, fmt, 640, 180, 12, "nm-chart-wide")
            + draw_line(pts, label, fmt, 440, 220, 15, "nm-chart-narrow"))


def draw_line(pts, label, fmt, width, height, size, cls):
    t0, t1 = pts[0][0], pts[-1][0]
    lo = min(v for _, v in pts)
    hi = max(v for _, v in pts)
    # start at zero, unless that would flatten a line that only moves
    # near its top; a line that does not move at all sits at the top
    base = lo if 0 < lo < hi and lo >= hi / 2 else 0
    top = hi if hi > base else base + 1
    top_text = fmt(hi)
    base_text = fmt(base) if base else ""
    # the values sit in a gutter left of the plot, level with their lines
    left = (14 + 7 * max(len(top_text), len(base_text))) * size // 12
    right, up, down = 8, 10, 2 * size

    def x(t):
        return left + (t - t0) / max(t1 - t0, 1) * (width - left - right)

    def y(v):
        return height - down - (v - base) / (top - base) * (height - up - down)

    line = " ".join("%.1f,%.1f" % (x(t), y(v)) for t, v in pts)
    first = local(t0).strftime("%-d %b")
    last = local(t1).strftime("%-d %b %Y")
    parts = [
        '<svg class="nm-chart %s" viewBox="0 0 %d %d" role="img" aria-label="%s">'
        % (cls, width, height, html.escape(label)),
        '<line class="nm-axis" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>'
        % (left, y(top), width - right, y(top)),
        '<line class="nm-axis" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>'
        % (left, y(base), width - right, y(base)),
        '<polyline points="%s" fill="none" stroke="currentColor" stroke-width="2"/>' % line,
        '<text x="%d" y="%.1f" text-anchor="end">%s</text>'
        % (left - 6, y(top) + size / 3, html.escape(top_text)),
    ]
    if base_text:
        parts.append('<text x="%d" y="%.1f" text-anchor="end">%s</text>'
                     % (left - 6, y(base) + size / 3, html.escape(base_text)))
    parts += [
        '<text x="%d" y="%d">%s</text>' % (left, height - size / 2, first),
        '<text x="%d" y="%d" text-anchor="end">%s</text>' % (width - right, height - size / 2, last),
        '</svg>',
    ]
    return "".join(parts)


def dual_chart(left, right, label, lname, rname, lfmt=str, rfmt=str):
    """Two (time, value) series over the same time, one SVG: the left
    one on a log scale read on the left, the right one on its own log
    scale read on the right, each named at its top corner in its colour.
    None when either has nothing to draw."""
    a = [(t, v) for t, v in left if v is not None]
    b = [(t, v) for t, v in right if v is not None]
    if len(a) < 2 or len(b) < 2:
        return None
    return (draw_dual(a, b, label, lname, rname, lfmt, rfmt, 640, 200, 12, "nm-chart-wide")
            + draw_dual(a, b, label, lname, rname, lfmt, rfmt, 440, 240, 15, "nm-chart-narrow"))


def draw_dual(a, b, label, lname, rname, lfmt, rfmt, width, height, size, cls):
    t0 = min(a[0][0], b[0][0])
    t1 = max(a[-1][0], b[-1][0])
    ltop, rtop = max(v for _, v in a), max(v for _, v in b)
    ltext, rtext = lfmt(ltop), rfmt(rtop)
    left = (14 + 7 * len(ltext)) * size // 12
    right = (14 + 7 * len(rtext)) * size // 12
    up, down = int(size * 2.2), 2 * size

    def x(t):
        return left + (t - t0) / max(t1 - t0, 1) * (width - left - right)

    def y(v, top):
        # log10(1 + v): zero sits on the floor, the top value at the top
        return height - down - math.log10(1 + max(v, 0)) / math.log10(1 + max(top, 1)) \
            * (height - up - down)

    def line(pts, top, var):
        return ('<polyline points="%s" fill="none" style="stroke: var(%s)" stroke-width="2"/>'
                % (" ".join("%.1f,%.1f" % (x(t), y(v, top)) for t, v in pts), var))

    ybase = height - down

    def ticks(top, fmt, tx, anchor):
        # the powers of ten under the top, far enough from it to read
        out, n = [], 10
        while n < top and y(n, top) - up > size * 1.6:
            out.append('<text x="%d" y="%.1f"%s class="nm-tick">%s</text>'
                       % (tx, y(n, top) + size / 3, anchor, html.escape(fmt(n))))
            n *= 10
        return "".join(out)
    first = local(t0).strftime("%-d %b")
    last = local(t1).strftime("%-d %b %Y")
    return "".join([
        '<svg class="nm-chart %s" viewBox="0 0 %d %d" role="img" aria-label="%s">'
        % (cls, width, height, html.escape(label)),
        '<line class="nm-axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, up, width - right, up),
        '<line class="nm-axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, ybase, width - right, ybase),
        line(a, ltop, "--nm-chart-1"),
        line(b, rtop, "--nm-chart-2"),
        '<text x="%d" y="%d" style="fill: var(--nm-chart-1)">%s</text>'
        % (left, size, html.escape(lname)),
        '<text x="%d" y="%d" text-anchor="end" style="fill: var(--nm-chart-2)">%s</text>'
        % (width - right, size, html.escape(rname)),
        '<text x="%d" y="%.1f" text-anchor="end">%s</text>' % (left - 6, up + size / 3, html.escape(ltext)),
        '<text x="%d" y="%.1f">%s</text>' % (width - right + 6, up + size / 3, html.escape(rtext)),
        ticks(ltop, lfmt, left - 6, ' text-anchor="end"'),
        ticks(rtop, rfmt, width - right + 6, ""),
        '<text x="%d" y="%.1f" text-anchor="end">0</text>' % (left - 6, ybase + size / 3),
        '<text x="%d" y="%.1f">0</text>' % (width - right + 6, ybase + size / 3),
        '<text x="%d" y="%d">%s</text>' % (left, height - size / 2, first),
        '<text x="%d" y="%d" text-anchor="end">%s</text>' % (width - right, height - size / 2, last),
        '</svg>',
    ])


def bars(items, fmt=str):
    """(label, value) pairs as bar rows for the template: label, the
    value as text, and its width as a share of the largest."""
    top = max((v for _, v in items), default=0) or 1
    return [{"label": k, "value": fmt(v), "pct": round(100 * v / top, 1)}
            for k, v in items]


# ---------------------------------------------------------------- parts

def players(rows, col):
    """Who is on: now, the last day, the month, and the busy hours."""
    if not rows or "users" not in col:
        return None
    u = col["users"]
    last = rows[-1]
    day = [r for r in rows if r[0] > last[0] - 86400]
    peak = max(rows, key=lambda r: r[u])
    by_hour = {}
    by_day = {}
    for r in rows:
        when = local(r[0])
        by_hour.setdefault(when.hour, []).append(r[u])
        key = when.date()
        by_day[key] = max(by_day.get(key, 0), r[u])
    days = sorted(by_day.items())
    if len(days) > 3:
        days = days[1:-1]              # first and last day are partial
    daily = [(int(dt.datetime.combine(d, dt.time(12), TZ).timestamp()), v)
             for d, v in days]
    return {
        "now": last[u],
        "mortals": last[col["mortals"]] if "mortals" in col else None,
        "wizards": last[col["wizards"]] if "wizards" in col else None,
        "day_peak": max(r[u] for r in day),
        "day_avg": round(sum(r[u] for r in day) / len(day), 1),
        "peak": peak[u],
        "peak_when": local(peak[0]).strftime("%-d %B, %H:00"),
        "hours": len(rows),
        "chart": line_chart([(r[0], r[u]) for r in rows], "Players online, hourly"),
        "daily_chart": line_chart(daily, "Most players online each day")
                       if len(daily) >= 7 else None,
        "by_hour": hour_candles(by_hour),
    }


def hour_candles(by_hour):
    """Each hour of the day as a candle: the wick from the fewest to the
    most ever on at that hour, the body from the median to the last
    count, filled when the last is at or above the median and hollow
    when below. Drawn wide and narrow, like line_chart."""
    rows = [(h, min(v), max(v), statistics.median(v), v[-1])
            for h, v in sorted(by_hour.items())]
    if len(rows) < 2:
        return None
    return (draw_candles(rows, 640, 200, 12, "nm-chart-wide")
            + draw_candles(rows, 440, 240, 15, "nm-chart-narrow"))


def draw_candles(rows, width, height, size, cls):
    top = max(r[2] for r in rows) or 1
    left = (14 + 7 * len(str(top))) * size // 12
    right, up, down = 8, 10, 2 * size
    step = (width - left - right) / 24
    body = max(step * 0.6, 3)

    def y(v):
        return height - down - v / top * (height - up - down)

    parts = [
        '<svg class="nm-chart %s" viewBox="0 0 %d %d" role="img" aria-label="%s">'
        % (cls, width, height, "Players on by hour of the day"),
        '<line class="nm-axis" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>'
        % (left, y(top), width - right, y(top)),
        '<line class="nm-axis" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>'
        % (left, y(0), width - right, y(0)),
        '<text x="%d" y="%.1f" text-anchor="end">%d</text>' % (left - 6, y(top) + size / 3, top),
        '<text x="%d" y="%.1f" text-anchor="end">0</text>' % (left - 6, y(0) + size / 3),
    ]
    for h, lo, hi, med, last in rows:
        cx = left + (h + 0.5) * step
        y1, y2 = y(max(med, last)), y(min(med, last))
        parts.append('<g style="stroke: var(--nm-chart-1); fill: %s"><title>%02d:00: '
                     '%d to %d, median %g, last %d</title>'
                     % ("none" if last < med else "var(--nm-chart-1)",
                        h, lo, hi, round(med, 1), last))
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke-width="1.5"/>'
                     % (cx, y(hi), cx, y(lo)))
        parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" stroke-width="1.5"/></g>'
                     % (cx - body / 2, y1 - (1 if y2 - y1 < 2 else 0), body, max(y2 - y1, 2)))
        if h % 3 == 0:
            parts.append('<text x="%.1f" y="%d" text-anchor="middle">%02d</text>'
                         % (cx, height - size / 2, h))
    parts.append('</svg>')
    return "".join(parts)


def uptime(booted, boots, generated):
    """Reboots: the current run, the year, the record, and per year."""
    if not boots and not booted:
        return None
    boots = sorted(set(boots + ([booted] if booted else [])))
    runs = [(a, b - a) for a, b in zip(boots, boots[1:])]
    year = [r for r in runs if r[0] >= generated - YEAR]
    record = max(runs, key=lambda r: r[1]) if runs else None
    per_year = {}
    for b in boots:
        per_year[local(b).year] = per_year.get(local(b).year, 0) + 1
    recent = [{"start": local(a).strftime("%-d %B %Y"), "length": span(n)}
              for a, n in reversed(runs[-4:])]
    if booted:
        recent.insert(0, {"start": local(booted).strftime("%-d %B %Y"),
                          "length": span(generated - booted) + ", up now"})
    return {
        "current": span(generated - booted) if booted else "",
        "booted": local(booted).strftime("%-d %B %Y, %H:%M") if booted else "",
        "boots": len(boots),
        "since": local(boots[0]).strftime("%B %Y"),
        "year_reboots": len([b for b in boots if b >= generated - YEAR]),
        "year_median": span(statistics.median(n for _, n in year)) if year else "",
        "record": span(record[1]) if record else "",
        "record_when": "%s to %s" % (local(record[0]).strftime("%-d %B %Y"),
                                     local(record[0] + record[1]).strftime("%-d %B %Y"))
                       if record else "",
        "per_year": bars(sorted(per_year.items())),
        "recent": recent,
    }


def gains(rows, p):
    """(time, growth since the sample before) for a counter that starts
    over at a reboot: a drop means a new start, so the new value is the
    growth."""
    out = []
    prev = None
    for r in rows:
        if len(r) <= p or r[p] is None:
            prev = None
            continue
        if prev is not None:
            out.append((r[0], r[p] - prev if r[p] >= prev else r[p]))
        prev = r[p]
    return out


def noon(d):
    return int(dt.datetime.combine(d, dt.time(12), TZ).timestamp())


def shops(rows, col, daily, weekly=None, yearly=None):
    """The main shop: what it bought, by the hour, the day, the week and
    the year. daily, weekly and yearly are the export's ({start, gold,
    items}); the mud keeps 92 days, two years of weeks and every year.
    Without them (older exports) days are added up from the hourly
    samples, and weeks and years from the days."""
    if not rows or "shop_paid" not in col:
        return None
    p = col["shop_paid"]
    n = col.get("shop_items")
    hourly_gold = gains(rows, p)[-24 * 7:]
    hourly_items = gains(rows, n)[-24 * 7:] if n is not None else []
    days = {}
    if daily:
        for t, g, k in daily:
            days[local(t).date()] = (g, k)
    else:
        for t, g in gains(rows, p):
            d = local(t).date()
            days[d] = (days.get(d, (0, 0))[0] + g, days.get(d, (0, 0))[1])
        if n is not None:
            for t, k in gains(rows, n):
                d = local(t).date()
                days[d] = (days.get(d, (0, 0))[0], days.get(d, (0, 0))[1] + k)
    if not days and not hourly_gold:
        return None
    ordered = sorted(days.items())
    full = ordered[1:-1] if len(ordered) > 3 else ordered      # first and last are partial
    weeks, years = {}, {}
    for d, (g, k) in ordered:
        wk = d - dt.timedelta(days=d.weekday())
        w = weeks.get(wk, (0, 0))
        weeks[wk] = (w[0] + g, w[1] + k)
        y = years.get(d.year, (0, 0))
        years[d.year] = (y[0] + g, y[1] + k)
    if weekly:
        weeks = {local(t).date(): (g, k) for t, g, k in weekly}
    if yearly:
        years = {y: (g, k) for y, g, k in yearly}
    last = rows[-1]
    recent = [v for _, v in full[-30:]]
    return {
        "gold": gold(last[p]) if len(last) > p else "",
        "bought": gold(last[n]) if n is not None and len(last) > n else "",
        "day_gold": gold(sum(g for g, _ in recent) / len(recent)) if recent else "",
        "day_items": gold(sum(k for _, k in recent) / len(recent)) if recent else "",
        "hour_chart": dual_chart(hourly_gold, hourly_items,
                                 "Gold the main shop paid out and items it bought each hour",
                                 "gold paid out", "items bought", gold, gold)
                      or line_chart(hourly_gold, "Gold the main shop paid out each hour", gold),
        "day_chart": dual_chart([(noon(d), g) for d, (g, _) in full[-90:]],
                                [(noon(d), k) for d, (_, k) in full[-90:]],
                                "Gold the main shop paid out and items it bought each day",
                                "gold paid out", "items bought", gold, gold)
                     or line_chart([(noon(d), g) for d, (g, _) in full[-90:]],
                                   "Gold the main shop paid out each day", gold),
        "week_chart": line_chart([(noon(w + dt.timedelta(days=3)), g)
                                  for w, (g, _) in sorted(weeks.items())[-52:]],
                                 "Gold the main shop paid out each week", gold),
        "years": [{"year": y, "gold": gold(g), "items": gold(k)}
                  for y, (g, k) in sorted(years.items(), reverse=True)],
    }


BUCKETS = [("lt1k", "under 1,000"), ("lt10k", "1,000 to 10,000"),
           ("lt100k", "10,000 to 100,000"), ("lt1m", "100,000 to 1 million"),
           ("lt10m", "1 to 10 million"), ("ge10m", "over 10 million")]


def wealth(now, columns, daily, rows, col):
    """imfd's figures: what the players own, how it is spread, and how
    it moved. Aggregates only; imfd never names anyone."""
    if not now or not now.get("count"):
        return None
    idx = {c: i for i, c in enumerate(columns)}

    def series(key, scale=1):
        if key not in idx:
            return []
        return [(r[0], r[idx[key]] / scale) for r in daily if len(r) > idx[key]]

    inflation = [(r[0], r[col["inflation"]]) for r in rows
                 if "inflation" in col and len(r) > col["inflation"]]
    return {
        "total": gold(now.get("total")),
        "count": now.get("count"),
        "mean": gold(now.get("mean")),
        "median": gold(now.get("median")),
        "p90": gold(now.get("p90")),
        "top1": round(now.get("top1_pm", 0) / 10, 1),
        "top10": round(now.get("top10_pm", 0) / 10, 1),
        "seen": [("the last day", now.get("seen1d")),
                 ("the last week", now.get("seen7d")),
                 ("the last 30 days", now.get("seen30d"))],
        "buckets": bars([(label, now.get(key, 0)) for key, label in BUCKETS]),
        "total_chart": line_chart(series("total"), "All the gold players own", gold),
        "median_chart": line_chart(series("median"), "Median player wealth", gold),
        "top10_chart": line_chart(series("top10_pm", 10), "Share owned by the richest 10% of players",
                                  lambda v: "%.1f%%" % v),
        "inflation": inflation[-1][1] if inflation else None,
        "inflation_chart": line_chart(inflation, "What shops pay, as a share of the value, hourly",
                                      lambda v: "%d%%" % v)
                           if any(v for _, v in inflation) else None,
    }


def page(stats):
    """Everything the Stats page shows, from stats.json."""
    cols = stats.get("columns", [])
    col = {c: i for i, c in enumerate(cols)}
    rows = [r for r in stats.get("hourly", []) if r]
    generated = stats.get("generated", 0)
    return {
        "players": players(rows, col),
        "uptime": uptime(stats.get("booted", 0), stats.get("boots", []), generated),
        "shops": shops(rows, col, stats.get("shop_daily", []),
                       stats.get("shop_weekly"), stats.get("shop_yearly")),
        "wealth": wealth(stats.get("wealth"), stats.get("wealth_columns", []),
                         stats.get("wealth_daily", []), rows, col),
    }
