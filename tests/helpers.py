"""Shared test scaffolding: a stub World and canned forage.

Nothing here touches the network or the live diary. Tests set AETHEL_HOME
to a tempdir (or inject Store(':memory:')) BEFORE the organism is built —
paths are lazy since v0.21, so that's all the isolation we need.
"""
import json
import os

from aethel_pkg.world import World


class StubWorld(World):
    """A two-room world: enough geography for dreams and greetings."""

    def __init__(self):
        self.places = {"classic": "the Old Bookshop",
                       "wikipedia": "the Library",
                       "postbox": "the wooden postbox at the end of the lane",
                       "home": "my rooms above the Old Bookshop"}

    def poll(self, n, observer_location):
        return {"moves": [], "present": []}

    def describe(self, place):
        return self.places.get(place, place)

    def random_place_name(self):
        return "the Old Bookshop"


FAKE_BOOK = ("whale ocean duty revenge fate captain obsession loneliness "
             "storm prophecy brotherhood integrity love dignity freedom "
             "conscience passion darkness redemption sacrifice courage ") * 400


def stub_forage(monkey_module):
    """Patch a forage/organism module's fetch functions with canned meals.
    Returns a dict of the canned pieces for assertions."""
    def fake_json(url, timeout=12):
        if "topstories" in url:
            return list(range(1, 31))
        if "item/" in url:
            return {"title": "The lost art of handwritten letters",
                    "url": "https://example.test/letters"}
        if "wikisource" in url:
            body = ("Ivan Ilych's life had been most simple and most "
                    "ordinary and therefore most terrible. " * 40)
            return {"query": {"pages": [{"revisions": [
                {"slots": {"main": {"content": body}}}]}]}}
        return {"title": "Honeybee communication",
                "text": "",
                "extract": "Honeybees perform a waggle dance describing "
                           "direction and distance of flowers — patience, "
                           "movement, angle, and sweetness."}

    def fake_gutenberg(seed):
        return FAKE_BOOK

    def fake_news(rng=None):
        return {"source": "newsroom",
                "title": "BBC: the town library opens a reading room",
                "text": "A story about patience, attention, kindness, "
                        "libraries, and care."}

    def fake_ocw(rng=None):
        return {"source": "university",
                "title": "Intro Philosophy — the examined life",
                "text": "Socrates on virtue, knowledge, justice, the good; "
                        "the examined life. " * 12}

    monkey_module.http_get_json = fake_json
    monkey_module.gutenberg_text = fake_gutenberg
    monkey_module.forage_news = fake_news
    monkey_module.forage_ocw_university = fake_ocw
    return {"json": fake_json, "gutenberg": fake_gutenberg,
            "news": fake_news, "ocw": fake_ocw}


def write_lessons(config, n=4):
    """Fill the schoolhouse satchel with local lessons."""
    os.makedirs(config.schoolhouse_lessons_dir(), exist_ok=True)
    for i in range(n):
        with open(os.path.join(config.schoolhouse_lessons_dir(),
                               f"{i:04d}.json"), "w") as f:
            json.dump({"course": "Early Math", "title": f"Lesson {i+1}",
                       "text": "counting numbers addition sharing fairness "
                               "patterns measurement kindness curiosity "
                               "seasons weather plants friendship honesty "
                               "patience gratitude wonder. " * 10}, f)
