"""Fetch public reading material and maintain local caches and course cursors.

External operations are read-only HTTP requests with timeouts. Callers handle
source failures; tests and explicit offline mode supply deterministic food."""

import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import quote

from . import config
from .journal import journal
from .rng import DEFAULT_SEED, SplitMix64

_fallback_rng = SplitMix64(
    SplitMix64(DEFAULT_SEED).spawn("forage").get_state(), name="forage-fallback"
)


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
    """Remove markup and collapse whitespace before a source becomes a meal."""
    raw = re.sub(r"(?s)<script.*?</script>", " ", raw)
    raw = re.sub(r"(?s)<style.*?</style>", " ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:limit]


def forage(rng=None):
    """Select and fetch public reading material using the supplied RNG; source errors propagate."""
    rng = _rng(rng)
    if rng.random() < 0.6:
        d = http_get_json("https://en.wikipedia.org/api/rest_v1/page/random/summary")
        text = d.get("extract") or ""
        return {
            "source": "wikipedia",
            "title": d.get("title", "untitled"),
            "text": text,
        }
    ids = http_get_json("https://hacker-news.firebaseio.com/v0/topstories.json")[:30]
    item = http_get_json(
        f"https://hacker-news.firebaseio.com/v0/item/{rng.choice(ids)}.json"
    )
    title = item.get("title", "untitled")
    return {
        "source": "hackernews",
        "title": title,
        "text": f"{title}. {item.get('url', '')}",
    }


def ocw_next_slug():
    """Advance the persisted course cursor through the local MIT catalog."""
    try:
        with open(config.ocw_catalog_path()) as catalog_file:
            slugs = json.load(catalog_file)
    except Exception:
        return None
    if not slugs:
        return None
    try:
        with open(config.ocw_cursor_path()) as cursor_file:
            idx = int(cursor_file.read().strip())
    except Exception:
        idx = 0
    idx %= len(slugs)
    with open(config.ocw_cursor_path(), "w") as f:
        f.write(str(idx + 1))
    return slugs[idx]


def ocw_course_pages(slug):
    """Discover content pages from an MIT course sitemap."""
    raw = http_get_text(f"https://ocw.mit.edu/courses/{slug}/sitemap.xml")
    return re.findall(
        r"<loc>(https://ocw\.mit\.edu/courses/"
        + re.escape(slug)
        + r"/(?:pages|resources)/[^<]+)</loc>",
        raw,
    )


def fetch_ocw_meal(slug, rng=None):
    """Fetch one substantial public course page; propagate unusable-source errors."""
    rng = _rng(rng)
    base = f"https://ocw.mit.edu/courses/{slug}"
    raw = http_get_text(base + "/")

    title = slug.replace("-", " ").title()
    m = re.search(r'<meta property="og:title" content="([^"]+)"', raw)
    if m:
        title = m.group(1).split(" | ")[0]

    text = None
    if rng.random() < 0.5:
        try:
            pages = [u for u in ocw_course_pages(slug) if "/pages/" in u]

            meaty = [
                u
                for u in pages
                if any(k in u for k in ("lecture", "reading", "notes", "syllabus"))
            ]
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
    """Traverse courses until a usable lecture is found, skipping thin pages."""
    last_err = None
    for _ in range(6):
        slug = ocw_next_slug()
        if not slug:
            raise RuntimeError("no OCW catalog")
        try:
            title, text = fetch_ocw_meal(slug, rng=rng)
            journal("university_lecture", course=title[:80])
            return {"source": "university", "title": title[:80], "text": text[:1500]}
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"no usable OCW course: {last_err}")


def forage_schoolhouse():
    """Consume the next local lesson and advance its cursor; return None if unavailable."""
    try:
        with open(config.schoolhouse_cursor_path()) as cursor_file:
            idx = int(cursor_file.read().strip())
    except Exception:
        idx = 0
    path = os.path.join(config.schoolhouse_lessons_dir(), f"{idx:04d}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as lesson_file:
            lesson = json.load(lesson_file)
    except Exception:
        return None
    with open(config.schoolhouse_cursor_path(), "w") as f:
        f.write(str(idx + 1))
    try:
        remaining = sum(
            1
            for f in os.listdir(config.schoolhouse_lessons_dir())
            if f.endswith(".json")
        ) - (idx + 1)
    except Exception:
        remaining = -1
    journal(
        "schoolhouse_lesson",
        course=lesson.get("course", "?"),
        lesson=lesson.get("title", "?")[:80],
        remaining=remaining,
    )
    text = lesson.get("text", "")[:1500]
    if len(text) < 80:
        return None
    return {
        "source": "schoolhouse",
        "title": f"{lesson.get('course', 'School')} — "
        f"{lesson.get('title', 'lesson')[:60]}",
        "text": text,
        # Keep lesson provenance for curriculum-specific study hooks.
        "course": lesson.get("course"),
        "unit": lesson.get("unit"),
    }


def forage_nightschool():
    """Represent the unavailable night-school source without inventing material."""
    return None


def forage_school(rng=None):
    """Prefer a local schoolhouse lesson, falling back to university material."""
    meal = forage_schoolhouse()
    if meal:
        return meal
    meal = forage_nightschool()
    if meal:
        return meal
    return forage_ocw_university(rng=rng)


NEWS_FEEDS = [
    ("BBC", "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml"),
    ("Guardian", "https://www.theguardian.com/world/rss"),
    ("PBS", "https://www.pbs.org/newshour/feeds/rss/headlines"),
]
NEWS_BLOCKLIST = ["foxnews", "fox news", "fox business"]


def parse_rss(raw):
    """Extract title, link and description fields from RSS or Atom feeds defensively."""
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
            continue
        if title:
            items.append({"title": title, "link": link, "desc": desc})
    return items


def forage_news(rng=None):
    """Choose a paper with the supplied RNG and fetch a public headline."""
    rng = _rng(rng)
    name, url = rng.choice(NEWS_FEEDS)
    req = urllib.request.Request(
        url, headers={"User-Agent": "Aethel/0.7 (read-only organism)"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode("utf-8", "replace")
    items = parse_rss(raw)
    if not items:
        raise RuntimeError(f"no usable items from {name}")
    pick = rng.choice(items[:15])
    text = pick["title"]
    if pick["desc"]:
        text += " — " + pick["desc"][:300]
    return {
        "source": "newsroom",
        "title": f"{name}: {pick['title'][:80]}",
        "text": text,
    }


def strip_wikitext(t):
    t = re.sub(r"\{\{.*?\}\}", "", t, flags=re.S)
    t = re.sub(r"\[\[([^|\]]*\|)?([^\]]+)\]\]", r"\2", t)
    t = re.sub(r"'''?", "", t)
    t = re.sub(r"^==+.*?==+\s*", "", t, flags=re.M)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def wikisource_chapter(title, numeral):
    """Fetch one public Wikisource chapter; leave failure handling to the caller."""
    url = (
        "https://en.wikisource.org/w/api.php?action=query&prop=revisions"
        "&rvprop=content&rvslots=main&formatversion=2&format=json&titles="
        + quote(f"{title}/{numeral}")
    )
    d = http_get_json(url)
    pg = d["query"]["pages"][0]
    raw = pg["revisions"][0]["slots"]["main"]["content"]
    return strip_wikitext(raw)


_BOOK_CACHE = {}


def gutenberg_text(seed):
    """Reuse a local book cache, downloading it with a read-only request when absent."""
    title = seed["title"]
    if title in _BOOK_CACHE:
        return _BOOK_CACHE[title]
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    path = os.path.join(config.books_dir(), slug + ".txt")
    if not os.path.exists(path):
        req = urllib.request.Request(
            seed["url"], headers={"User-Agent": "Aethel/0.6 (read-only organism)"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
        start = raw.find("*** START OF")
        if start != -1:
            raw = raw[raw.find("\n", start) + 1 :]
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
