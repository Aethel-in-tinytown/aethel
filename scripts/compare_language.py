"""Compare isolated seeded lives and reading fixtures; never touch live state.

Run with an interpreter that has the nlp extra and provisioned resources:
AETHEL_NLTK_DATA=/path/to/data python scripts/compare_language.py
Each backend runs in its own subprocess so peak RSS includes its own models.
"""

import contextlib
import io
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from aethel_pkg.journal import set_store
from aethel_pkg.organism import Aethel
from aethel_pkg import grammar
import test_determinism as deterministic

FIXTURES = [
    "Dr. Smith said, ‘I can’t go.’ Then the mice swam! The red gem shone. "
    "She swims through gardens, thinking of kindness and courage.",
    "A curious quokka slept. She sings beautifully. The building was quiet. "
    "They record the record carefully. Captain Donald teaches a course.",
    "Login subscribe navigation. A noun names a thing. A sentence has a subject "
    "and a predicate. Adverbs describe verbs; adjectives describe nouns.",
]


def measure(name):
    started = time.perf_counter()
    original = Aethel
    with patch.object(
        deterministic,
        "Aethel",
        side_effect=lambda **kw: original(**kw, language_backend=name),
    ):
        with tempfile.TemporaryDirectory() as home:
            a, store = deterministic._build(home, 20261019)
            startup = time.perf_counter() - started
            with contextlib.redirect_stdout(io.StringIO()):
                for text in FIXTURES:
                    meal = {
                        "title": "Reading fixture",
                        "source": "classic",
                        "text": text,
                    }
                    with (
                        patch.object(a, "forage_classic", return_value=meal),
                        patch("aethel_pkg.organism.forage", return_value=meal),
                        patch("aethel_pkg.organism.forage_news", return_value=meal),
                        patch("aethel_pkg.organism.forage_school", return_value=meal),
                    ):
                        a.forage_and_eat()
            vocabulary = list(a._concept_counts())
            classes = {
                w: a._word_class(w)
                for w in (
                    "red",
                    "quokka",
                    "building",
                    "beautifully",
                    "donald",
                    "course",
                    "navigation",
                )
            }
            a.tick_count = 100
            for text in (
                "She swam through the gardens.",
                "A garden has a swimsuit.",
                "The discussion was full of information.",
            ):
                store.log("experience", {"text": text}, tick=1)
            recall = {
                query: a.recall([query])
                for query in ("swimming garden", "discuss inform")
            }
            fixture_meals = [
                data["new_terms"] for _, _, data in store.recent(events=("meal",))
            ][::-1]
            store.close()
            set_store(None)
        life_started = time.perf_counter()
        with tempfile.TemporaryDirectory() as home:
            life = deterministic._run(home, 20261019, total=160)
        life_seconds = time.perf_counter() - life_started
    counts = life["aethel/state"]["concepts"]
    return {
        "backend": name,
        "startup_seconds": round(startup, 4),
        "life_160_ticks_seconds": round(life_seconds, 4),
        "peak_rss_mib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2
        ),
        "fixture_surface_words": len(a.concepts),
        "fixture_canonical_words": len(vocabulary),
        "fixture_vocabulary": vocabulary,
        "fixture_new_terms": fixture_meals,
        "classes": classes,
        "recall": recall,
        "life_surface_words": len(counts),
        "life_meals": life["aethel/state"]["meals_eaten"],
        "life_canonical_words": len(life["aethel/state"].get("lemma_index", counts)),
        "life_scaffolding_words": sorted(set(counts) & grammar.SCAFFOLDING_WORDS),
    }


if __name__ == "__main__":
    if len(sys.argv) == 2:
        print(json.dumps(measure(sys.argv[1]), indent=2))
    else:
        results = [
            json.loads(
                subprocess.check_output([sys.executable, __file__, backend], text=True)
            )
            for backend in ("heuristic", "nltk")
        ]
        print(json.dumps(results, indent=2))
