"""Optional English analysis, activation, and deterministic continuation gates."""

import contextlib
import copy
import io
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from aethel_pkg import config, grammar
from aethel_pkg.journal import get_store, set_store
from aethel_pkg.language import HeuristicLanguage, NltkLanguage, select_language
from aethel_pkg.language_resources import LanguageError, provision
from aethel_pkg.main import parse_args
from aethel_pkg.organism import Aethel
from aethel_pkg.store import Store
from helpers import StubWorld


class TestLanguageSelection(unittest.TestCase):
    def test_provisioning_entrypoint_is_independent_of_simulation_imports(self):
        result = subprocess.run(
            [sys.executable, "-m", "aethel_pkg.language_resources", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        from aethel_pkg import Aethel as exported

        self.assertIs(exported, Aethel)

    def test_legacy_saves_default_to_heuristics(self):
        self.assertEqual(select_language({"tick_count": 70}).name, "heuristic")
        backend = HeuristicLanguage()
        self.assertEqual(
            select_language({"language": backend.metadata}).metadata, backend.metadata
        )

    def test_missing_package_is_explicit(self):
        with patch.dict("sys.modules", {"nltk": None}):
            with self.assertRaisesRegex(LanguageError, "pip install"):
                select_language({}, "nltk")

    def test_package_version_mismatch_is_explicit(self):
        from types import SimpleNamespace

        with patch.dict("sys.modules", {"nltk": SimpleNamespace(__version__="0.0")}):
            with self.assertRaisesRegex(LanguageError, "3.9.2 required"):
                NltkLanguage()

    def test_omission_resumes_saved_selection_and_checks_revision(self):
        backend = HeuristicLanguage()
        backend.name = "nltk"
        backend.metadata = dict(backend.metadata, backend="nltk")
        with patch("aethel_pkg.language.NltkLanguage", return_value=backend):
            self.assertIs(select_language({"language": backend.metadata}), backend)
            incompatible = dict(backend.metadata, pipeline_revision=999)
            with self.assertRaisesRegex(LanguageError, "incompatible"):
                select_language({"language": incompatible}, "nltk")
            self.assertEqual(
                select_language({"language": incompatible}, "heuristic").name,
                "heuristic",
            )

    def test_launcher_selection_is_optional_in_both_modes(self):
        for argv in ([], ["--serve"]):
            self.assertIsNone(parse_args(argv).language_backend)
            self.assertEqual(
                parse_args(argv + ["--language-backend", "nltk"]).language_backend,
                "nltk",
            )

    def test_bad_archive_never_leaves_a_partial_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "averaged_perceptron_tagger_eng.zip").write_bytes(b"incorrect")
            with self.assertRaisesRegex(LanguageError, "checksum mismatch"):
                provision(root / "installed", root)
            self.assertFalse((root / "installed").exists())

    def test_heuristic_interface_preserves_offsets(self):
        text = "A sentence. Another one!"
        result = HeuristicLanguage().analyze(text)
        self.assertEqual(
            [text[a:b] for a, b in result.sentences], ["A sentence.", "Another one!"]
        )
        for token in result.tokens:
            self.assertEqual(text[token.start : token.end], token.text)

    def test_context_never_invents_semantics_for_unknown_nouns(self):
        for word in ("quokka", "building", "zorb"):
            self.assertIsNone(grammar.classify_word(word, pos="NN"))
        self.assertEqual(
            grammar.classify_word("mysteriously", pos="JJ"), grammar.ADJECTIVE
        )
        self.assertEqual(grammar.classify_word("course", pos="VB"), grammar.STUDY)
        self.assertEqual(grammar.classify_word("login", pos="NN"), grammar.SCAFFOLDING)


class TestNltkLanguage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.backend = NltkLanguage()
        except LanguageError as exc:
            raise unittest.SkipTest(f"Optional NLTK integration: {exc}")

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

    def organism(self, selection="nltk"):
        return Aethel(
            StubWorld(), parents=("Donald",), seed=42, language_backend=selection
        )

    def feed(self, organism, text, source="wikipedia"):
        meal = {
            "source": source,
            "title": "Grammar" if source == "schoolhouse" else "Fixture",
            "text": text,
        }
        # Force the existing source choice while preserving the normal meal code.
        with (
            patch.object(organism, "forage_classic", return_value=meal),
            patch("aethel_pkg.organism.forage", return_value=meal),
            patch("aethel_pkg.organism.forage_news", return_value=meal),
            patch("aethel_pkg.organism.forage_school", return_value=meal),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            organism.forage_and_eat()
        return meal

    def test_contractions_abbreviations_unicode_and_source_offsets(self):
        text = "Dr. Smith said, ‘I can’t go.’ Then the mice ran!"
        result = self.backend.analyze(text)
        self.assertEqual(len(result.sentences), 2)
        self.assertIn("n’t", [token.text for token in result.tokens])
        self.assertEqual(result.text, text)
        for token in result.tokens:
            self.assertEqual(text[token.start : token.end], token.text)
        self.assertTrue(all(0 <= a < b <= len(text) for a, b in result.sentences))
        content = self.backend.analyze("A naïve café owner smiled.")
        self.assertTrue(
            {"naïve", "café"}
            <= {t.text for t in content.tokens if self.backend.content(t)}
        )
        text = "She sings—beautifully. A red gem… The mice swim–quickly!"
        result = self.backend.analyze(text)
        self.assertEqual(len(result.sentences), 3)
        self.assertTrue(
            {"sings", "beautifully", "gem", "swim", "quickly"}
            <= {t.text for t in result.tokens if self.backend.content(t)}
        )
        self.assertTrue(all(text[t.start : t.end] == t.text for t in result.tokens))
        self.assertEqual(
            text[result.sentences[1][0] : result.sentences[1][1]], "A red gem…"
        )

    def test_pos_aware_irregular_lemmas_and_ambiguous_pos(self):
        result = self.backend.analyze(
            "They ate apples and ran through the gardens. I record the record carefully."
        )
        words = [(t.text, t.lemma, t.pos) for t in result.tokens]
        self.assertIn(("ate", "eat", "VBP"), words)
        self.assertIn(("ran", "run", "VBD"), words)
        self.assertIn(("apples", "apple", "NNS"), words)
        self.assertEqual(
            [t.pos for t in result.tokens if t.text == "record"], ["VBP", "NN"]
        )

    def test_short_words_scaffolding_names_and_unknown_nouns(self):
        a = self.organism()
        self.feed(
            a,
            "Donald found a red gem. A curious quokka slept. The building was quiet. Login subscribe navigation.",
        )
        self.assertIn("red", a.concepts)
        self.assertIn("gem", a.concepts)
        self.assertNotIn("login", a.concepts)
        self.assertNotIn("subscribe", a.concepts)
        self.assertNotIn("navigation", a.concepts)
        self.assertEqual(a._word_class("donald"), grammar.PERSON)
        self.assertIsNone(a._word_class("quokka"))
        self.assertIsNone(a._word_class("building"))
        self.assertEqual(a._word_tags["quokka"]["src"], "wikipedia")
        a._word_tags["login"] = {"c": grammar.CONCRETE, "src": "legacy"}
        self.assertEqual(a._word_class("login"), grammar.SCAFFOLDING)

    def test_acquisition_uses_context_before_suffixes_and_keeps_provenance(self):
        a = self.organism()
        self.feed(a, "She sings beautifully. A curious quokka found a red gem.")
        self.assertEqual(a._word_class("sing"), grammar.VERB)
        self.assertEqual(a._word_class("beautifully"), grammar.ADVERB)
        tag = copy.deepcopy(a._word_tags["beautifully"])
        self.feed(a, "She sings beautifully.", source="schoolhouse")
        self.assertEqual(a._word_tags["beautifully"], tag)
        self.assertEqual(a._word_class("course", pos="VB"), grammar.STUDY)

    def test_alias_novelty_counts_and_cooccurrence(self):
        a = self.organism()
        self.feed(a, "She swam through the gardens.")
        counts = a._concept_counts().copy()
        self.feed(a, "She swims through the gardens.")
        self.assertEqual(a.lemma_index["swim"], {"swam": 1, "swims": 1})
        self.assertEqual(a.concepts["swam"], 1)
        self.assertEqual(a.concepts["swims"], 1)
        self.assertEqual(a._concept_counts()["swim"], counts["swim"] + 1)
        self.assertIn("garden", a.cooc["swim"])
        self.assertNotIn("swam", a.cooc)
        self.assertEqual(
            get_store().recent(events=("meal",), limit=1)[0][2]["new_terms"], 0
        )

    def test_activation_retains_historical_knowledge_and_goal_progress(self):
        a = self.organism("heuristic")
        a.concepts = {"swimming": 7, "swim": 3, "mice": 4, "mouse": 2}
        a._word_tags = {"swimming": {"c": "verb", "src": "classic"}}
        a.beliefs = ["I believe the running mice."]
        a.kept_passages = [{"text": "The mice were running.", "source": "classic"}]
        a.goals = [
            {
                "term": "swimming",
                "question": "what is swimming?",
                "start_count": 3,
                "progress": 0.4,
            }
        ]
        a.completed_terms = {"mice"}
        a.save()
        before = copy.deepcopy(self.store.load_blob("state"))
        self.assertEqual(self.organism(None).language.name, "heuristic")
        active = self.organism("nltk")
        self.assertEqual(active.concepts, before["concepts"])
        self.assertEqual(active.beliefs, before["beliefs"])
        self.assertEqual(active.kept_passages, before["kept_passages"])
        self.assertEqual(active.goals[0]["lemma_start_count"], 6)
        active.update_goals()
        self.assertEqual(active.goals[0]["progress"], 0.4)
        active.save()
        resumed = self.organism(None)
        self.assertEqual(resumed.lemma_index, active.lemma_index)
        self.feed(resumed, "She swims through the gardens.")
        resumed.update_goals()
        self.assertEqual(resumed.goals[0]["progress"], 0.5)
        resumed.save()
        switched = self.organism("heuristic")
        switched.update_goals()
        self.assertEqual(switched.goals[0]["progress"], 0.5)
        switched.goals = []
        # Completion aliases must block adopting mouse/mice as a new goal.
        active.goals = []
        active.adopt_goal()
        active.adopt_goal()
        self.assertEqual([g["term"] for g in active.goals], ["swim"])

    def test_recall_uses_whole_lemmas_and_stable_ties(self):
        a = self.organism()
        a.tick_count = 10
        for text in (
            "She swims in the garden.",
            "She swam in the gardens.",
            "A garden has a swimsuit.",
        ):
            self.store.log("experience", {"text": text}, tick=1)
        self.store.log(
            "experience", {"text": "She swims in the garden today."}, tick=10
        )
        self.assertEqual(
            a.recall(["swimming garden"]),
            ["She swam in the gardens.", "She swims in the garden."],
        )
        a.language = HeuristicLanguage()
        self.store.log("experience", {"text": "The discussion of information."}, tick=1)
        a.language = self.backend
        self.assertEqual(a.recall(["discuss inform"]), [])

    def test_open_question_keywords_share_normalization(self):
        a = self.organism()
        a.open_questions = [
            {
                "text": "Why do mice swim?",
                "keywords": ["mice", "swimming"],
                "touches": 0,
            }
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            a._check_open_questions(["mouse", "swim"])
        self.assertEqual(a.open_questions[0]["touches"], 1)

    def test_meal_is_analyzed_once_and_kept_on_sentence_boundaries(self):
        a = self.organism()
        a.vitals["excitement"] = 0.9
        text = (
            "Dr. Smith describes the subject of a sentence. "
            + "The noun names a small thing. " * 30
        )
        with patch.object(a.language, "analyze", wraps=a.language.analyze) as analyze:
            self.feed(a, text, source="schoolhouse")
        self.assertEqual(analyze.call_count, 1)
        passage = a.kept_passages[-1]
        self.assertEqual(passage["source"], "schoolhouse")
        self.assertTrue(text.startswith(passage["text"]))
        self.assertLessEqual(len(passage["text"]), 600)
        self.assertTrue(passage["text"].endswith("."))
        self.assertEqual(passage["text"], self.backend.analyze(text).passage(600))
        example = self.store.recent(events=("grammar_learned",), limit=1)[0][2][
            "example"
        ]
        self.assertIn(example, text)

    def test_rule_examples_keep_the_actual_lesson_source(self):
        lessons = [
            {"text": "The sea is calm.", "source": "first"},
            {"text": "Dr. Smith says a noun names a thing.", "source": "second"},
        ]
        found = grammar.extract_rules_from_lessons(
            lessons, [self.backend.analyze(l["text"]) for l in lessons]
        )
        result = next(r for r in found.values() if "noun" in r["example_candidate"])
        self.assertEqual(result["source"], "second")
        self.assertTrue(result["example_candidate"].startswith("Dr. Smith"))

    def test_cache_is_bounded(self):
        n = NltkLanguage()
        n.CACHE_SIZE = 4
        for i in range(10):
            n.normalized(f"They run in garden {i}.")
        self.assertEqual(len(n._cache), 4)
        before = list(n._cache)
        n.normalized("A" * (n.CACHE_TEXT_LIMIT + 1))
        self.assertEqual(list(n._cache), before)

    def test_offline_startup_ignores_global_nltk_search_paths(self):
        from aethel_pkg.language import _models

        _models.cache_clear()
        with (
            patch("socket.socket", side_effect=AssertionError("network forbidden")),
            patch(
                "nltk.data.find", side_effect=AssertionError("global search forbidden")
            ),
        ):
            self.assertEqual(NltkLanguage().name, "nltk")

    def test_missing_changed_and_incompatible_resources_fail_before_mutation(self):
        a = self.organism()
        a.save()
        state = copy.deepcopy(self.store.load_blob("state"))
        for field, value in (
            ("pipeline_revision", 999),
            ("resources", {}),
            ("nltk_version", "0.0"),
        ):
            bad = copy.deepcopy(state)
            bad["language"][field] = value
            self.store.save_blob("state", bad)
            with self.assertRaises(LanguageError):
                self.organism(None)
            self.assertEqual(self.store.load_blob("state"), bad)
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"AETHEL_NLTK_DATA": tmp}),
        ):
            with self.assertRaisesRegex(LanguageError, "Missing or mismatched"):
                self.organism("nltk")
        # A tampered installed model is checked even when models are cached.
        from aethel_pkg.language_resources import data_dir

        original = Path.read_bytes
        target = data_dir().resolve() / "tokenizers/punkt_tab/english/abbrev_types.txt"

        def read_bytes(path):
            return b"tampered" if path == target else original(path)

        with patch.object(Path, "read_bytes", read_bytes):
            with self.assertRaisesRegex(LanguageError, "Missing or mismatched"):
                self.organism("nltk")

    def test_same_seed_and_save_rebuild_continuation(self):
        import test_determinism as deterministic

        with patch.object(
            deterministic,
            "Aethel",
            side_effect=lambda **kw: Aethel(**kw, language_backend="nltk"),
        ):
            with (
                tempfile.TemporaryDirectory() as h1,
                tempfile.TemporaryDirectory() as h2,
                tempfile.TemporaryDirectory() as h3,
            ):
                first = deterministic._run(h1, 20261019, total=160)
                same = deterministic._run(h2, 20261019, total=160)
                resumed = deterministic._run(h3, 20261019, first=100, total=160)
        self.assertEqual(first, same)
        self.assertEqual(first, resumed)
        self.assertTrue(any(e == "dream" for _, e, _ in first["aethel"]))

    def test_headless_offline_activation_resume_and_rejection(self):
        launcher = Path(__file__).resolve().parents[1] / "aethel_live.py"
        command = [
            sys.executable,
            str(launcher),
            "--offline",
            "--ticks",
            "2",
            "--time-scale",
            "10000",
        ]
        for selection in (["--language-backend", "nltk"], []):
            result = subprocess.run(
                command + selection, capture_output=True, text=True, timeout=20
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        with contextlib.closing(Store(config.db_path())) as store:
            state = store.load_blob("state")
            self.assertEqual(state["tick_count"], 4)
            self.assertEqual(state["language"]["backend"], "nltk")
            state["language"]["pipeline_revision"] = 999
            store.save_blob("state", state)
        rejected = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("incompatible", rejected.stderr)
        with contextlib.closing(Store(config.db_path())) as store:
            self.assertEqual(store.load_blob("state"), state)

    def test_offline_worker_publishes_backend_and_resumes_it(self):
        from threading import Event
        from aethel_web.worker import worker_main

        options = {
            "home": self.home.name,
            "seed": 42,
            "ticks": 1,
            "interval": 0.001,
            "offline": True,
            "language_backend": "nltk",
        }
        # worker_main installs offline fetch functions and ignores SIGINT; restore both.
        import signal
        import aethel_pkg.forage as forage
        import aethel_pkg.organism as organism

        names = (
            "forage",
            "forage_news",
            "forage_ocw_university",
            "http_get_json",
            "gutenberg_text",
            "wikisource_chapter",
        )
        with contextlib.ExitStack() as stack:
            for module in (forage, organism):
                for name in names:
                    stack.enter_context(
                        patch.object(
                            module, name, getattr(module, name, None), create=True
                        )
                    )
            handler = signal.getsignal(signal.SIGINT)
            self.addCleanup(signal.signal, signal.SIGINT, handler)
            for selection in ("nltk", None):
                options["language_backend"] = selection
                set_store(Store(config.db_path()))
                incoming, outgoing = queue.Queue(), queue.Queue()
                with contextlib.redirect_stdout(io.StringIO()):
                    worker_main(options, incoming, outgoing, Event())
                first = outgoing.get_nowait()["snapshot"]
                self.assertEqual(first["status"]["language"]["backend"], "nltk")
                self.assertEqual(first["status"]["language"]["nltk_version"], "3.9.2")


class TestLanguageStartupFailure(unittest.TestCase):
    def test_worker_reports_backend_rejection_without_ticking(self):
        import signal
        from threading import Event
        from aethel_web.worker import worker_main

        with (
            tempfile.TemporaryDirectory() as home,
            patch.dict(os.environ, {"AETHEL_HOME": home}),
        ):
            config.ensure_dirs()
            store = Store(config.db_path())
            set_store(store)
            self.addCleanup(store.close)
            handler = signal.getsignal(signal.SIGINT)
            self.addCleanup(signal.signal, signal.SIGINT, handler)
            stop, outgoing = Event(), queue.Queue()
            with patch(
                "aethel_web.worker.Aethel",
                side_effect=LanguageError("incompatible resources"),
            ):
                with self.assertRaisesRegex(LanguageError, "incompatible"):
                    worker_main(
                        {"home": home, "seed": 42}, queue.Queue(), outgoing, stop
                    )
            self.assertTrue(stop.is_set())
            self.assertEqual(outgoing.get_nowait(), {"fatal": "incompatible resources"})
            check = Store(config.db_path())
            self.addCleanup(check.close)
            self.assertIsNone(check.load_blob("state"))
            self.assertFalse(check.recent(events=("meal",)))
