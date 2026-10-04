"""One-time import of the guild pages kept in the mudlib.

Two guilds kept a small website of their own in their directory: the
Vikings (guilds/vikings/www) and the Monks (guilds/monks/www). Each
becomes one page, content/guilds/<slug>.html, with the original words;
the layout tables and menus are dropped and the pictures copied.

    python scripts/import_guilds.py /path/to/NannyMUD-lib/guilds
"""
import os
import re
import shutil
import sys

from bs4 import BeautifulSoup

OUT = "content/guilds"
IMG = "static/img/guilds"


def soup(path):
    with open(path, encoding="latin-1") as fh:
        return BeautifulSoup(fh.read(), "html.parser")


def text(node):
    return re.sub(r"\s+", " ", node.get_text(" ")).strip()


def paragraphs(nodes):
    return "\n".join("<p>%s</p>" % html_escape(t) for t in nodes if t)


def html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def vikings(src):
    """index.html has the welcome, each other page a heading in its
    banner and the text in <P> blocks."""
    www = os.path.join(src, "vikings", "www")
    intro = soup(os.path.join(www, "index.html"))
    for s in intro(["script", "style"]):
        s.decompose()
    welcome = [text(p) for p in intro.find_all(["p", "td"]) if len(text(p)) > 120 and not p.find(["td", "p"])]
    parts = [paragraphs(welcome[:1])]
    for page, heading in (("beginning", "The Beginning"), ("gods", "The Gods"),
                          ("leaders", "Our Leaders"), ("joining", "Joining and Leaving")):
        s = soup(os.path.join(www, page + ".html"))
        body = []
        for p in s.find_all("p"):
            if p.find("img") or p.find("table"):
                continue
            t = text(p)
            if len(t) > 20:
                body.append(t)
        html = "<h2>%s</h2>\n" % heading
        html += paragraphs(body)
        parts.append(html)
    for img in ("title.jpg",):
        shutil.copy2(os.path.join(www, img), os.path.join(IMG, "vikings-2.jpg"))
    return "The Vikings", "guilds/vikings/www", "\n".join(parts)


def monks(src):
    """Every page has the menu in its first cell and the text in the
    second, after the lily."""
    www = os.path.join(src, "monks", "www")
    parts = []
    for page, heading in (("monks", None), ("location", "The Monastery"),
                          ("mass", "Mass"), ("healing", "Healing"),
                          ("herbalism", "Herbalism"), ("lily", "The White Lily")):
        s = soup(os.path.join(www, page + ".html"))
        cells = s.find_all("td")
        cell = cells[1] if len(cells) > 1 else s.body
        for x in cell.find_all(["img", "center"]):
            x.decompose()
        raw = str(cell)
        chunks = re.split(r"<p\s*/?>|</p>", raw, flags=re.I)
        body = []
        for c in chunks:
            t = text(BeautifulSoup(c, "html.parser"))
            if t:
                body.append(t)
        html = ("<h2>%s</h2>\n" % heading) if heading else ""
        html += paragraphs(body)
        parts.append(html)
    shutil.copy2(os.path.join(www, "lily_2.gif"), os.path.join(IMG, "monks-2.gif"))
    return "The Order of the White Lily", "guilds/monks/www", "\n".join(parts)


def main(src):
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(IMG, exist_ok=True)
    for slug, fn in (("vikings", vikings), ("monks", monks)):
        title, origin, body = fn(src)
        with open(os.path.join(OUT, slug + ".html"), "w", encoding="utf-8") as fh:
            fh.write("<!-- title: %s -->\n<!-- from: %s -->\n%s\n" % (title, origin, body))
        print("%-8s %d bytes" % (slug, len(body)))


if __name__ == "__main__":
    main(sys.argv[1])
