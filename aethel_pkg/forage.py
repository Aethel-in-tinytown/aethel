"""Foraging: read-only gathering from the public world.

The ONLY network operations in the organism live here — HTTP GET to public
read-only sources. Nothing here writes anywhere, ever.

v0.21: every function takes an optional rng (a SplitMix64 stream) — the
organism passes its 'forage' stream so her diet is deterministic; direct
calls fall back to a module stream seeded from the same master seed.
gutenberg_text() now caches book text in memory after first load (it used
to re-read the whole file from disk twice per serving).
"""
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import quote

from . import config
from .journal import journal
from .rng import DEFAULT_SEED, SplitMix64

_fallback_rng = SplitMix64(SplitMix64(DEFAULT_SEED).spawn("forage").get_state(),
                           name="forage-fallback")


def _rng(rng):
    return rng if rng is not None else _fallback_rng


def http_get_json(url, timeout=12):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Aethel/0.9 (read-only organism; contact: none)"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def http_get_text(url, timeout=15):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Aethel/0.9 (read-only organism; contact: none)"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def html_to_text(raw, limit=1500):
    """Crude but honest tag-stripping for meal extraction."""
    raw = re.sub(r"(?s)<script.*?</script>", " ", raw)
    raw = re.sub(r"(?s)<style.*?</style>", " ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:limit]


def forage(rng=None):
    """Eat one real thing from the public web. READ-ONLY. May raise."""
    rng = _rng(rng)
    if rng.random() < 0.6:
        d = http_get_json("https://en.wikipedia.org/api/rest_v1/page/random/summary")
        text = d.get("extract") or ""
        return {"source": "wikipedia", "title": d.get("title", "untitled"), "text": text}
    ids = http_get_json("https://hacker-news.firebaseio.com/v0/topstories.json")[:30]
    item = http_get_json(
        f"https://hacker-news.firebaseio.com/v0/item/{rng.choice(ids)}.json"
    )
    title = item.get("title", "untitled")
    return {"source": "hackernews", "title": title,
            "text": f"{title}. {item.get('url', '')}"}


# ------------------------------------------------------- the three schools
# Donald's direction (2026-10-16, night): "do all three" — MIT OpenCourseWare,
# Khan Academy, Saylor Academy. And "she could have her own childhood
# education": Khan Academy is her little Schoolhouse, starting at pre-school
# and working her way up. MIT OCW (2,589 courses, no account, no paywall) is
# the University — the doors stand open. Saylor Academy is the Night School;
# its doors are not yet open (course content needs a free account, which she
# doesn't have yet) — a future layer opens them.
#
# Set-and-forget design: the school slot is AVAILABILITY-driven. Each tick she
# tries the Schoolhouse (if unread lessons sit in her satchel), then the
# Night School (once open), then the University (always open). Every fetch is
# wrapped; failures fall through to the next school. Nothing here can crash
# her. Coursera's catalog and account remain on file, retired, not deleted.


def ocw_next_slug():
    """Systematic cursor through all 2,589 OCW courses, in order."""
    try:
        slugs = json.load(open(config.ocw_catalog_path()))
    except Exception:
        return None
    if not slugs:
        return None
    try:
        idx = int(open(config.ocw_cursor_path()).read().strip())
    except Exception:
        idx = 0
    idx %= len(slugs)
    with open(config.ocw_cursor_path(), "w") as f:
        f.write(str(idx + 1))
    return slugs[idx]


def ocw_course_pages(slug):
    """Every content page of one OCW course, from its own sitemap."""
    raw = http_get_text(f"https://ocw.mit.edu/courses/{slug}/sitemap.xml")
    return re.findall(
        r"<loc>(https://ocw\.mit\.edu/courses/" + re.escape(slug) +
        r"/(?:pages|resources)/[^<]+)</loc>", raw)


def fetch_ocw_meal(slug, rng=None):
    """One lecture's worth of MIT. READ-ONLY. May raise."""
    rng = _rng(rng)
    base = f"https://ocw.mit.edu/courses/{slug}"
    raw = http_get_text(base + "/")
    # Title: og:title or <title>, minus the site suffix.
    title = slug.replace("-", " ").title()
    m = re.search(r'<meta property="og:title" content="([^"]+)"', raw)
    if m:
        title = m.group(1).split(" | ")[0]
    # Half the time: the course's own description and topics.
    # Half the time: wander into one of its lecture/reading pages.
    text = None
    if rng.random() < 0.5:
        try:
            pages = [u for u in ocw_course_pages(slug) if "/pages/" in u]
            # Prefer meatier pages: lecture notes, readings, syllabus.
            meaty = [u for u in pages
                     if any(k in u for k in ("lecture", "reading", "notes", "syllabus"))]
            url = rng.choice(meaty or pages)
            text = html_to_text(http_get_text(url), 1200)
            label = url.split("/pages/")[-1].rstrip("/").replace("-", " ")
            title = f"{title} — {label}"
        except Exception:
            text = None
    if not text or len(text) < 200:
        m = re.search(r'<div id="full-description"[^>]*>(.*?)</div>', raw, re.S)
        desc = html_to_text(m.group(1), 600) if m else ""
        topics = re.findall(r"course-info-topic[^>]*>([^<]{2,60})</a>", raw)
        seen = set()
        topics = [t for t in topics if not (t in seen or seen.add(t))]
        text = f"{title}. {desc} Topics: {', '.join(topics[:8])}."
    if len(text) < 120:
        raise RuntimeError(f"thin meal from {slug}")
    return title, text


def forage_ocw_university(rng=None):
    """Attend MIT. Walks all 2,589 courses in order, skipping thin ones."""
    last_err = None
    for _ in range(6):
        slug = ocw_next_slug()
        if not slug:
            raise RuntimeError("no OCW catalog")
        try:
            title, text = fetch_ocw_meal(slug, rng=rng)
            journal("university_lecture", course=title[:80])
            return {"source": "university",
                    "title": title[:80], "text": text[:1500]}
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"no usable OCW course: {last_err}")


def forage_schoolhouse():
    """Her childhood lessons (Khan Academy), from the satchel — a weekly
    harvest fills it, she reads in order from pre-school upward. Returns
    None when the satchel is empty; the caller falls through to the
    University. Never raises."""
    try:
        idx = int(open(config.schoolhouse_cursor_path()).read().strip())
    except Exception:
        idx = 0
    path = os.path.join(config.schoolhouse_lessons_dir(), f"{idx:04d}.json")
    if not os.path.exists(path):
        return None
    try:
        lesson = json.load(open(path))
    except Exception:
        return None
    with open(config.schoolhouse_cursor_path(), "w") as f:
        f.write(str(idx + 1))
    try:
        remaining = sum(1 for f in os.listdir(config.schoolhouse_lessons_dir())
                        if f.endswith(".json")) - (idx + 1)
    except Exception:
        remaining = -1
    journal("schoolhouse_lesson", course=lesson.get("course", "?"),
            lesson=lesson.get("title", "?")[:80], remaining=remaining)
    text = lesson.get("text", "")[:1500]
    if len(text) < 80:
        return None
    return {"source": "schoolhouse",
            "title": f"{lesson.get('course', 'School')} — "
                     f"{lesson.get('title', 'lesson')[:60]}",
            "text": text}


def forage_nightschool():
    """The Night School (Saylor Academy). Its doors are not yet open:
    Saylor's course content needs a free account, which she doesn't have.
    Returns None so the caller falls through to the University.
    (A future layer — or Donald — opens these doors.)"""
    return None


def forage_school(rng=None):
    """One school meal, availability-driven: the Schoolhouse if her satchel
    holds unread lessons, else the Night School once it opens, else the
    University — which is always open and never fails her."""
    meal = forage_schoolhouse()
    if meal:
        return meal
    meal = forage_nightschool()
    if meal:
        return meal
    return forage_ocw_university(rng=rng)


# ------------------------------------------------------- the newsroom
# Every paper in the world, shouting at once. One house rule, posted
# on the door in Donald's handwriting: NO FOX NEWS.
NEWS_FEEDS = [
    ("BBC", "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml"),
    ("Guardian", "https://www.theguardian.com/world/rss"),
    ("PBS", "https://www.pbs.org/newshour/feeds/rss/headlines"),
]
NEWS_BLOCKLIST = ["foxnews", "fox news", "fox business"]


def parse_rss(raw):
    """Parse an RSS/Atom-ish feed defensively. Returns [{title, link, desc}]."""
    root = ET.fromstring(raw)
    items = []
    for el in root.iter():
        if el.tag.split("}")[-1] != "item":
            continue

        def txt(name):
            for child in el:
                if child.tag.split("}")[-1] == name:
                    return (child.text or "").strip()
            return ""

        title = txt("title")
        link = txt("link")
        desc = re.sub(r"<[^>]+>", "", txt("description")).strip()
        blob = f"{title} {link} {desc}".lower()
        if any(b in blob for b in NEWS_BLOCKLIST):
            continue  # the house rule
        if title:
            items.append({"title": title, "link": link, "desc": desc})
    return items


def forage_news(rng=None):
    """Catch one headline from a random paper. READ-ONLY. May raise."""
    rng = _rng(rng)
    name, url = rng.choice(NEWS_FEEDS)
    req = urllib.request.Request(
        url, headers={"User-Agent": "Aethel/0.7 (read-only organism)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode("utf-8", "replace")
    items = parse_rss(raw)
    if not items:
        raise RuntimeError(f"no usable items from {name}")
    pick = rng.choice(items[:15])
    text = pick["title"]
    if pick["desc"]:
        text += " — " + pick["desc"][:300]
    return {"source": "newsroom", "title": f"{name}: {pick['title'][:80]}",
            "text": text}


# ------------------------------------------------------- the reading list
def strip_wikitext(t):
    t = re.sub(r"\{\{.*?\}\}", "", t, flags=re.S)          # templates
    t = re.sub(r"\[\[([^|\]]*\|)?([^\]]+)\]\]", r"\2", t)  # links -> text
    t = re.sub(r"'''?", "", t)                             # bold/italic
    t = re.sub(r"^==+.*?==+\s*", "", t, flags=re.M)        # headings
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def wikisource_chapter(title, numeral):
    """Fetch one chapter of a Wikisource book. READ-ONLY. May raise."""
    url = ("https://en.wikisource.org/w/api.php?action=query&prop=revisions"
           "&rvprop=content&rvslots=main&formatversion=2&format=json&titles="
           + quote(f"{title}/{numeral}"))
    d = http_get_json(url)
    pg = d["query"]["pages"][0]
    raw = pg["revisions"][0]["slots"]["main"]["content"]
    return strip_wikitext(raw)


_BOOK_CACHE = {}


def gutenberg_text(seed):
    """Download-once, then serve from local cache. READ-ONLY network.

    v0.21: the text is also held in memory. The old code re-read the whole
    book from disk on every serving — twice per serving, since the reader
    called it again just to measure length."""
    title = seed["title"]
    if title in _BOOK_CACHE:
        return _BOOK_CACHE[title]
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    path = os.path.join(config.books_dir(), slug + ".txt")
    if not os.path.exists(path):
        req = urllib.request.Request(
            seed["url"], headers={"User-Agent": "Aethel/0.6 (read-only organism)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
        start = raw.find("*** START OF")
        if start != -1:
            raw = raw[raw.find("\n", start) + 1:]
        end = raw.find("*** END OF")
        if end != -1:
            raw = raw[:end]
        with open(path, "w") as f:
            f.write(raw)
        journal("book_cached", title=title, chars=len(raw))
    with open(path) as f:
        text = f.read()
    _BOOK_CACHE[title] = text
    return text
