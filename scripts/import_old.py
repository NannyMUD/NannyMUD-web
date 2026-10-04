"""One-time import of the old Lysator pages into content/.

Keeps the original words. Only the markup changes: the 1990s FONT tags
become real headings, styling tags are dropped, internal links point at
the new pages, and the images are copied into static/img/old/.

    python scripts/import_old.py /path/to/NannyMUD-lib/www
"""
import os
import re
import shutil
import sys

from bs4 import BeautifulSoup, Comment, NavigableString

# old page -> (new slug, title)
PAGES = {
    "basics": ("introduction", "Introduction"),
    "whatis": ("what-is-nannymud", "What is NannyMUD?"),
    "game": ("the-game", "The Game"),
    "features": ("features", "Features"),
    "world": ("the-world", "The World"),
    "enter": ("connect", "Enter the Game"),
    "early": ("the-beginnings", "The Beginnings"),
    "time_line": ("timeline", "Time Line"),
    "musings": ("musings", "Musings of the Elders"),
    "events": ("events", "Events and Incidents"),
    "faq": ("faq", "Frequently Asked Questions"),
    "newbie_booklet": ("newbie-booklet", "The Newbie Booklet"),
    "people": ("the-people", "The People"),
    "pictures": ("pictures", "Picture Archives"),
    "other": ("other-topics", "Other Topics"),
    "contact": ("contact", "Contact Us"),
}

KEEP = {"p", "ul", "ol", "li", "a", "b", "strong", "i", "em", "pre", "br",
        "table", "tr", "td", "th", "h2", "h3", "img", "dl", "dt", "dd",
        "blockquote", "code", "tt"}


# old pages that are gone from Lysator, recovered from the Internet
# Archive into content/ by hand
RECOVERED = {
    "http://mud.lysator.liu.se/misc/attendence.html": "/attendance/",
    "http://mud.lysator.liu.se/guilds/statistics/": "/guild-statistics/",
    "http://www.lysator.liu.se/nanny/statistics/from_where.html": "/where-players-come-from/",
    "http://www.lysator.liu.se/~zander/ewan_dl.html": "/ewan/",
    "http://www.lysator.liu.se/nanny/pics/NannyMUD.small.jpg": "/static/img/old/NannyMUD.small.jpg",
}


def new_link(href):
    """Old internal links -> new slugs; everything else unchanged."""
    if href in RECOVERED:
        return RECOVERED[href]
    m = re.match(r"^(?:https?://mud\.lysator\.liu\.se/www/)?([a-z_]+)\.html(#.*)?$",
                 href or "", re.I)
    if m and m.group(1).lower() in PAGES:
        return "/" + PAGES[m.group(1).lower()][0] + "/" + (m.group(2) or "")
    if href and href.startswith("images/"):
        return "/static/img/old/" + href[len("images/"):]
    return href


def body_of(html):
    """Between the start marker and whichever end the page has: an END
    marker, a '/// Main Body' marker, or the footer include."""
    m = re.search(r"<!--\s*Main Body\s*-->", html, re.I)
    start = m.end() if m else 0
    end = len(html)
    for pat in (r"<!--\s*Main Body END\s*-->", r"<!--\s*///\s*Main Body\s*-->",
                r"<!--#include virtual=\"footer"):
        e = re.search(pat, html[start:], re.I)
        if e:
            end = min(end, start + e.start())
    return html[start:end]


def clean(html, images, src_dir):
    soup = BeautifulSoup(body_of(html), "html.parser")
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    # FONT SIZE=4 around bold text is how the old site made headings.
    for f in soup.find_all("font"):
        size = (f.get("size") or "").strip()
        if size in ("4", "+1", "5") and f.get_text(strip=True):
            f.name = "h2"
            f.attrs = {}
            f.string = f.get_text(" ", strip=True)
        else:
            f.unwrap()
    for tag in soup.find_all(True):
        name = tag.name.lower()
        if name not in KEEP:
            tag.unwrap()
            continue
        attrs = {}
        if name == "a" and tag.get("href"):
            attrs["href"] = new_link(tag["href"])
        if name == "a" and tag.get("name"):
            attrs["id"] = tag["name"]
        if name == "img" and tag.get("src"):
            src = tag["src"]
            local = src.split("/www/")[-1]
            if local.startswith("images/") or "/" not in local:
                path = os.path.join(src_dir, local if "/" in local else "images/" + local)
                if os.path.isfile(path):
                    images.add(path)
                attrs["src"] = "/static/img/old/" + os.path.basename(local)
                attrs["alt"] = tag.get("alt", "")
                attrs["loading"] = "lazy"
            else:
                tag.decompose()
                continue
        tag.attrs = attrs
    # an <h2> left inside a <p> is invalid; lift it out
    for h in soup.find_all("h2"):
        if h.parent and h.parent.name == "p":
            h.parent.insert_before(h.extract())
    text = str(soup)
    # the old pages put a <br> right after each heading; the heading's own
    # margin does that job now
    text = re.sub(r"(</h2>\s*(?:<p>)?)\s*(?:<br/>\s*)+", r"\1", text)
    text = re.sub(r"(<br/>\s*){3,}", "<br/><br/>", text)
    text = re.sub(r"<p>\s*</p>", "", text)
    return text.strip()


def game_lists(body):
    """The old Game page linked a partial guild list and a club list at
    Lysator, all dead now. Guilds point at the guilds page instead; the
    clubs keep their introduction, there are too many to list."""
    body = re.sub(r"(<h2>The Guilds</h2>.*?)Click below to read about\s*Nanny's various guilds:</p>\s*<ul>.*?</ul>",
                  r'\1The <a href="/guilds/">guilds page</a> lists every guild in the game.</p>',
                  body, flags=re.S)
    body = re.sub(r"\s*Not all clubs have webpages,.*?</p>\s*<ul>.*?</ul>",
                  "</p>", body, flags=re.S)
    # leaving the Adventurers leaves a player without a guild
    body = body.replace("Every player in Nanny is the member of some guild.",
                        "Most players in Nanny are members of a guild.")
    return body


def main(src_dir, out_dir="content", img_dir="static/img/old"):
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)
    images = set()
    for old, (slug, title) in PAGES.items():
        path = os.path.join(src_dir, old + ".html")
        with open(path, encoding="latin-1") as fh:
            html = fh.read()
        body = clean(html, images, src_dir)
        if old == "world":
            # wizard documentation is not public for now
            body = re.split(r"<h2>\s*Creating the World", body)[0].strip()
        if old == "game":
            body = game_lists(body)
        with open(os.path.join(out_dir, slug + ".html"), "w", encoding="utf-8") as fh:
            fh.write("<!-- title: %s -->\n<!-- from: www/%s.html -->\n%s\n"
                     % (title, old, body))
        print("%-16s -> %s (%d bytes)" % (old, slug, len(body)))
    for img in sorted(images):
        shutil.copy2(img, os.path.join(img_dir, os.path.basename(img)))
    for extra in ("mainland_map.jpg", "mainland_se.png", "antharis_map.jpg"):
        p = os.path.join(src_dir, "images", extra)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(img_dir, extra))
    print("images copied:", len(os.listdir(img_dir)))


if __name__ == "__main__":
    main(sys.argv[1])
