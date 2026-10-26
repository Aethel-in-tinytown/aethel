"""v0.35: reading-tone annotations (NLTK plan Phase 4, step 1).

Pins, in order: provisioning verification (the pinned lexicon's
checksum is checked; a corrupt or missing lexicon makes the tone
phase absent LOUDLY — one tone_unavailable event — while the
organism still boots and runs); annotation determinism, including
strongest-word tie-breaking; exactly one 'tone' journal event per
reading in NLTK mode with the required fields, and none ever in
heuristic mode (raising-stub parity); the load-bearing flag-off
proof — a seeded NLTK run with annotations on produces a state
trajectory identical to the same run with the tone seam disabled,
differing only by the 'tone' journal events themselves; the flag-on
cap and symmetry of the (shipped-disabled) effects path; and the
seeded 260-tick NLTK restart-fidelity life with tone active.

Isolation: in-memory stores via set_store and a temp AETHEL_HOME for
every organism built here — her live diary is never instantiated
against, and the audit script is the only reader of her real db.
"""

import contextlib
import hashlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aethel_pkg.organism as org_mod
from aethel_pkg import config, tone as tone_mod
from aethel_pkg.journal import set_store
from aethel_pkg.language_resources import LanguageError, data_dir, verify_resource
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store

from helpers import StubWorld

HAPPY = (
    "It was a bright and lovely morning, and she was filled with joy "
    "and gratitude for every good and kind thing in her life."
)
BLEAK = (
    "The fog was cruel and the night terrible; grief and misery and "
    "wretched sorrow pressed on every dark and lonely heart."
)


def provisioned_root():
    """The pinned data tree the runtime itself resolves, or None.

    Resolved through language_resources.data_dir() (AETHEL_NLTK_DATA,
    else the AETHEL_HOME tree), never a hard-coded developer path.
    CI provisions exactly the resolved directory in its nltk jobs
    (the workflow's --download step), so the tone integration tests
    run there against the same pinned bytes; where nothing is
    provisioned, they skip. This helper replaces a module constant
    that named one machine's home directory: on every other machine
    the provisioning tests crashed reading bytes that were never
    there, and the organism tests skipped even when CI had data
    provisioned at the resolved root.
    """
    root = data_dir()
    return root if root.is_dir() else None


def require_nltk_backend():
    """Skip unless the real NLTK backend constructs in this process.

    Constructing the backend is the check (the suite-wide pattern,
    test_language.TestNltkLanguage): it fails closed with
    LanguageError both when the nltk package is absent (the CI
    heuristic jobs install no [nlp] extra) and when the pinned
    resources are missing or mismatched. A directory check alone
    sees neither half, which is how ungated NLTK tests came to
    error in heuristic CI instead of skipping.
    """
    from aethel_pkg.language import NltkLanguage

    try:
        NltkLanguage()
    except LanguageError as exc:
        raise unittest.SkipTest(f"Optional NLTK integration: {exc}")


def nlp_data_env(testcase):
    """Point the backend at the provisioned, pinned data (read-only)."""
    if "AETHEL_NLTK_DATA" not in os.environ:
        root = provisioned_root()
        if root is not None:
            env = patch.dict(os.environ, {"AETHEL_NLTK_DATA": str(root)})
            env.start()
            testcase.addCleanup(env.stop)


def real_analyzer(testcase):
    try:
        return tone_mod.load_analyzer(data_dir())
    except tone_mod.ToneUnavailable as exc:
        raise unittest.SkipTest(f"Optional NLTK integration: {exc}")


# ------------------------------------------------------- provisioning
class TestProvisioning(unittest.TestCase):
    def test_pinned_lexicon_verifies(self):
        root = provisioned_root()
        if root is None:
            self.skipTest("NLTK data not provisioned")
        digest = verify_resource(root, "vader_lexicon")
        self.assertEqual(
            digest,
            "8adba4294eef3964d820bf655e37e61bdc3a341994356af59b74fb3b4a36ce5c",
        )
        lexicon = root / tone_mod.LEXICON_RELATIVE
        self.assertEqual(
            hashlib.sha256(lexicon.read_bytes()).hexdigest(),
            "0aabac74cd95def2dbedc04ce55e39698d91113ffadb6d86b87dd337c4d2184d",
        )

    def _broken_root(self, mode):
        root = Path(self._tmp.name) / "nltk_data"
        target = root / tone_mod.LEXICON_RELATIVE
        target.parent.mkdir(parents=True)
        if mode == "corrupt":
            data = (provisioned_root() / tone_mod.LEXICON_RELATIVE).read_bytes()
            target.write_bytes(data[:-50] + b"tampered" + data[-42:])
        # mode == "missing": write nothing at all
        return root

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_corrupt_lexicon_fails_verification(self):
        if provisioned_root() is None:
            self.skipTest("NLTK data not provisioned")
        root = self._broken_root("corrupt")
        with self.assertRaises(LanguageError):
            verify_resource(root, "vader_lexicon")
        with self.assertRaises(tone_mod.ToneUnavailable):
            tone_mod.load_analyzer(root)

    def test_missing_lexicon_fails_verification(self):
        root = self._broken_root("missing")
        with self.assertRaises(LanguageError):
            verify_resource(root, "vader_lexicon")
        with self.assertRaises(tone_mod.ToneUnavailable):
            tone_mod.load_analyzer(root)


class TestBootWithoutTone(unittest.TestCase):
    """A missing/corrupt lexicon removes the phase, not the organism."""

    @classmethod
    def setUpClass(cls):
        require_nltk_backend()
        cls.src_root = provisioned_root()

    def _linked_root(self, corrupt):
        """A full data tree: real copies of the core files (verify
        rejects symlinks, so copies carry the pinned bytes) and a
        real, optionally tampered, copy of the lexicon."""
        root = Path(self._tmp.name) / ("bad" if corrupt else "gone")
        for src in self.src_root.rglob("*"):
            if not src.is_file():
                continue
            dst = root / src.relative_to(self.src_root)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src == self.src_root / tone_mod.LEXICON_RELATIVE:
                if corrupt:
                    data = src.read_bytes()
                    dst.write_bytes(data[:-50] + b"tampered" + data[-42:])
                # not corrupt => the lexicon is simply absent
            else:
                shutil.copyfile(src, dst)
        return root

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def _boot(self, corrupt):
        root = self._linked_root(corrupt)
        with (
            patch.dict(
                os.environ,
                {"AETHEL_HOME": self.home.name, "AETHEL_NLTK_DATA": str(root)},
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            config.ensure_dirs()
            a = Aethel(
                StubWorld(), parents=("Donald",), seed=42, language_backend="nltk"
            )
            self.assertEqual(a.language.name, "nltk")  # she booted
            analysis = a.language.analyze(HAPPY)
            self.assertIsNone(a._tone_feed(analysis, "classic"))
            a.save()
        rows = self.store.recent(events=("tone_unavailable",))
        self.assertEqual(len(rows), 1)
        self.assertIn("vader_lexicon", rows[0][2]["reason"])
        self.assertEqual(self.store.recent(events=("tone",)), [])

    def test_corrupt_lexicon_boots_without_tone(self):
        self._boot(corrupt=True)

    def test_missing_lexicon_boots_without_tone(self):
        self._boot(corrupt=False)


# --------------------------------------------------------- annotation
class StubAnalyzer:
    """polarity_scores fixed; lexicon hand-set for tie-break pins."""

    def __init__(self, lexicon):
        self.lexicon = lexicon

    def polarity_scores(self, text):
        return {"compound": 0.25, "pos": 0.4, "neu": 0.5, "neg": 0.1}


class TestAnnotation(unittest.TestCase):
    def test_determinism_real_analyzer(self):
        analyzer = real_analyzer(self)
        first = tone_mod.annotate(HAPPY, analyzer)
        second = tone_mod.annotate(HAPPY, analyzer)
        self.assertEqual(first, second)
        self.assertGreater(first["compound"], 0)
        self.assertIsNotNone(first["strongest_positive_word"])
        bleak = tone_mod.annotate(BLEAK, analyzer)
        self.assertLess(bleak["compound"], 0)
        self.assertIsNotNone(bleak["strongest_negative_word"])

    def test_strongest_word_valence_beats_order(self):
        analyzer = StubAnalyzer({"good": 1.9, "great": 3.0, "bad": -1.5, "awful": -2.0})
        ann = tone_mod.annotate("good things, great things", analyzer)
        self.assertEqual(ann["strongest_positive_word"], "great")
        ann = tone_mod.annotate("bad luck and awful luck", analyzer)
        self.assertEqual(ann["strongest_negative_word"], "awful")

    def test_strongest_word_tie_breaks_by_first_occurrence(self):
        analyzer = StubAnalyzer({"good": 2.0, "kind": 2.0, "bad": -2.0, "sad": -2.0})
        ann = tone_mod.annotate("kind words and good words", analyzer)
        self.assertEqual(ann["strongest_positive_word"], "kind")
        ann = tone_mod.annotate("good words and kind words", analyzer)
        self.assertEqual(ann["strongest_positive_word"], "good")
        ann = tone_mod.annotate("sad news and bad news", analyzer)
        self.assertEqual(ann["strongest_negative_word"], "sad")

    def test_no_lexicon_hit_yields_none_not_invention(self):
        analyzer = StubAnalyzer({"good": 2.0})
        ann = tone_mod.annotate("the harbor lantern burned", analyzer)
        self.assertIsNone(ann["strongest_positive_word"])
        self.assertIsNone(ann["strongest_negative_word"])


# ---------------------------------------------------------- journaling
class TestJournaling(unittest.TestCase):
    def setUp(self):
        nlp_data_env(self)
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.env = patch.dict(os.environ, {"AETHEL_HOME": self.home.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        config.ensure_dirs()
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def _meal(self, a, text=HAPPY):
        meal = {"source": "classic", "title": "Fixture", "text": text}
        with contextlib.redirect_stdout(io.StringIO()):
            with (
                patch.object(a, "forage_classic", return_value=meal),
                patch.object(org_mod, "forage", return_value=meal),
                patch.object(org_mod, "forage_news", return_value=meal),
                patch.object(org_mod, "forage_school", return_value=meal),
            ):
                a.forage_and_eat()

    def test_nltk_reading_journals_exactly_one_tone_event(self):
        require_nltk_backend()
        with contextlib.redirect_stdout(io.StringIO()):
            a = Aethel(
                StubWorld(), parents=("Donald",), seed=42, language_backend="nltk"
            )
        self._meal(a)
        rows = self.store.recent(events=("tone",))
        self.assertEqual(len(rows), 1)
        tick, _, d = rows[0]
        self.assertEqual(tick, a.tick_count)
        for field in (
            "source",
            "compound",
            "pos",
            "neu",
            "neg",
            "top_pos_word",
            "top_neg_word",
        ):
            self.assertIn(field, d)
        self.assertEqual(d["source"], "classic")
        self.assertGreater(d["compound"], 0)
        a.save()
        blob = self.store.load_blob("state")
        self.assertNotIn("tone_effects", blob)  # flag off persists none
        self.assertEqual(self.store.recent(events=("tone_effect",)), [])

    def test_heuristic_reading_journals_no_tone_and_never_loads(self):
        with contextlib.redirect_stdout(io.StringIO()):
            a = Aethel(
                StubWorld(), parents=("Donald",), seed=42, language_backend="heuristic"
            )
        boom = AssertionError("tone touched in heuristic mode")
        with (
            patch.object(tone_mod, "load_analyzer", side_effect=boom),
            patch.object(tone_mod, "annotate", side_effect=boom),
        ):
            self._meal(a)
        self.assertEqual(self.store.recent(events=("tone",)), [])
        self.assertEqual(self.store.recent(events=("tone_unavailable",)), [])


# ------------------------------------------- flag-off zero-effect proof
MEALS = {
    "classic": HAPPY + " " + BLEAK,
    "wikipedia": (
        "London is a city on a river. Sailors spoke of joy and good "
        "harbors, and of grief in the terrible fog at dawn."
    ),
    "newsroom": (
        "Harbor officials said a whale entered the bay at dawn. "
        "Lanterns along the pier burned late while the town gathered."
    ),
    "schoolhouse": (
        "A lantern is a lamp with a case. The whale is a mammal that "
        "breathes air. The harbor shelters ships from the open sea."
    ),
}


def canned(source):
    return {"source": source, "title": f"Fixture {source}", "text": MEALS[source]}


def scrub(obj):
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if k not in ("t", "ts")}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def run_life(home, ticks, tone_enabled=True):
    with patch.dict(os.environ, {"AETHEL_HOME": home}):
        config.ensure_dirs()
        store = Store(config.db_path())
        set_store(store)
        try:
            patches = [
                patch.object(Aethel, "forage_classic", lambda self: canned("classic")),
                patch.object(org_mod, "forage", lambda rng=None: canned("wikipedia")),
                patch.object(
                    org_mod, "forage_news", lambda rng=None: canned("newsroom")
                ),
                patch.object(
                    org_mod, "forage_school", lambda rng=None: canned("schoolhouse")
                ),
            ]
            if not tone_enabled:
                patches.append(
                    patch.object(
                        Aethel, "_tone_feed", lambda self, analysis, source: None
                    )
                )
            for p in patches:
                p.start()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    a = Aethel(
                        StubWorld(),
                        parents=("Donald",),
                        seed=42,
                        language_backend="nltk",
                    )
                    for _ in range(ticks):
                        a.tick()
            finally:
                for p in patches:
                    p.stop()
            snap = {
                "journal": [(t, e, scrub(d)) for t, e, d in store.recent(limit=10**9)],
                "state": scrub(store.load_blob("state")),
            }
            store.close()
            return snap
        finally:
            set_store(Store(":memory:"))


class TestFlagOffZeroEffect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_nltk_backend()

    def setUp(self):
        nlp_data_env(self)

    def test_annotations_change_no_state(self):
        """The phase's load-bearing test: annotations on vs the tone
        seam disabled — identical state, identical journal except
        the 'tone' events themselves."""
        self.assertFalse(config.TONE_EFFECTS_ENABLED)  # shipped default
        with tempfile.TemporaryDirectory() as h1, tempfile.TemporaryDirectory() as h2:
            on = run_life(h1, 130, tone_enabled=True)
            off = run_life(h2, 130, tone_enabled=False)
        tone_events = [row for row in on["journal"] if row[1] == "tone"]
        self.assertGreater(len(tone_events), 0)
        self.assertEqual([row for row in off["journal"] if row[1] == "tone"], [])
        self.assertEqual(
            [row for row in on["journal"] if row[1] != "tone"],
            off["journal"],
        )
        self.assertEqual(on["state"], off["state"])
        self.assertNotIn("tone_effects", on["state"])


# ------------------------------------------------- flag-on: cap/symmetry
class TestEffectsFlagOn(unittest.TestCase):
    """The disabled path, exercised in tests only (flag never ships on)."""

    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.env = patch.dict(os.environ, {"AETHEL_HOME": self.home.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        config.ensure_dirs()
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def _organism_with_ache(self, ache=0.8):
        with contextlib.redirect_stdout(io.StringIO()):
            a = Aethel(
                StubWorld(), parents=("Donald",), seed=42, language_backend="heuristic"
            )
        a._ledger().top()["ache"] = ache
        a._sync_longing()
        return a

    def test_positive_and_negative_nudges_mirror(self):
        ann_pos = {"compound": 1.0}
        ann_neg = {"compound": -1.0}
        a = self._organism_with_ache()
        before = a.longing
        delta_pos = tone_mod.apply_tone_effects(a, ann_pos)
        self.assertLess(delta_pos, 0)  # uplifting eases longing
        self.assertAlmostEqual(before - a.longing, -delta_pos, places=9)
        b = self._organism_with_ache()
        self.assertAlmostEqual(b.longing, before, places=12)
        delta_neg = tone_mod.apply_tone_effects(b, ann_neg)
        self.assertGreater(delta_neg, 0)
        self.assertAlmostEqual(delta_neg, -delta_pos, places=12)
        self.assertAlmostEqual(b.longing - before, -delta_pos, places=9)

    def test_daily_cap_bounds_total_movement(self):
        a = self._organism_with_ache(ache=0.95)
        total = 0.0
        for _ in range(10):
            total += abs(tone_mod.apply_tone_effects(a, {"compound": -1.0}))
        self.assertLessEqual(total, tone_mod.LONGING_DAILY_CAP + 1e-9)
        self.assertAlmostEqual(
            a._tone_fx["applied"], min(total, tone_mod.LONGING_DAILY_CAP), places=9
        )
        # A new simulated day resets the cap.
        a.tick_count += a.DAY_LENGTH
        self.assertNotEqual(tone_mod.apply_tone_effects(a, {"compound": -1.0}), 0.0)

    def test_wiring_through_tone_feed_when_flag_on(self):
        nlp_data_env(self)
        require_nltk_backend()
        with contextlib.redirect_stdout(io.StringIO()):
            a = Aethel(
                StubWorld(), parents=("Donald",), seed=42, language_backend="nltk"
            )
        a._ledger().top()["ache"] = 0.8
        a._sync_longing()
        before = a.longing
        with patch.object(config, "TONE_EFFECTS_ENABLED", True):
            with contextlib.redirect_stdout(io.StringIO()):
                ann = a._tone_feed(a.language.analyze(HAPPY), "classic")
        self.assertIsNotNone(ann)
        self.assertLess(a.longing, before)
        self.assertEqual(len(self.store.recent(events=("tone_effect",))), 1)
        self.assertEqual(len(self.store.recent(events=("tone",))), 1)


# --------------------------------------------------- restart fidelity
class TestRestartFidelityRealBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_nltk_backend()

    def setUp(self):
        nlp_data_env(self)
        self.store = Store(":memory:")
        set_store(self.store)
        self.addCleanup(self.store.close)

    def _run(self, home, first, total):
        with patch.dict(os.environ, {"AETHEL_HOME": home}):
            config.ensure_dirs()
            store = Store(config.db_path())
            set_store(store)
            try:
                with (
                    patch.object(
                        Aethel, "forage_classic", lambda self: canned("classic")
                    ),
                    patch.object(
                        org_mod, "forage", lambda rng=None: canned("wikipedia")
                    ),
                    patch.object(
                        org_mod, "forage_news", lambda rng=None: canned("newsroom")
                    ),
                    patch.object(
                        org_mod, "forage_school", lambda rng=None: canned("schoolhouse")
                    ),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    a = Aethel(
                        StubWorld(),
                        parents=("Donald",),
                        seed=42,
                        language_backend="nltk",
                    )
                    for _ in range(first):
                        a.tick()
                    if first:
                        store.close()
                        store = Store(config.db_path())
                        set_store(store)
                        a = Aethel(
                            StubWorld(),
                            parents=("Donald",),
                            seed=42,
                            language_backend="nltk",
                        )
                    for _ in range(total - first):
                        a.tick()
                snap = {
                    "journal": [
                        (t, e, scrub(d)) for t, e, d in store.recent(limit=10**9)
                    ],
                    "state": scrub(store.load_blob("state")),
                }
                store.close()
                return snap
            finally:
                set_store(self.store)

    def test_nltk_life_restart_is_continuation_not_rebirth(self):
        """The seeded 260-tick gate, with tone active: interrupted
        equals uninterrupted, journal (tone events included) and
        state blob alike."""
        with tempfile.TemporaryDirectory() as h1, tempfile.TemporaryDirectory() as h2:
            interrupted = self._run(h1, first=130, total=260)
            uninterrupted = self._run(h2, first=0, total=260)
        events = [e for _, e, _ in interrupted["journal"]]
        self.assertIn("tone", events)
        self.assertEqual(interrupted, uninterrupted)


if __name__ == "__main__":
    unittest.main()
