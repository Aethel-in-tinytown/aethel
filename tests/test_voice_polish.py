"""Voice polish (v0.48, reworked): a copyedit at sealing, by rules.

Donald's original direction (2026-10-31) sent her postbox pieces
through a local model with a humanize-and-correct brief. The live
endpoint test failed twice on 2026-11-01: Sparta's qwen3:4b answered
at a healthy ~127 tokens/second but spent 5,339 tokens reasoning
about the letter before editing it, blowing the 20-second ceiling
both times. Donald then ruled the rework himself: a deterministic,
offline, rule-based copyeditor instead of a model. The trade is
named, not hidden: rules fix mechanics, they do not supply missing
words the way the model brief promised. What they buy is the thing
her architecture values most, the same output on every run, at no
waiting cost, with no infrastructure inside her tick.

The placement laws from the original design are untouched. First,
v0.29: a letter is never re-rolled into someone else's words, so the
polish still sits at sealing, AFTER the grammar ledger's reading and
after everything she learns from writing (notebook, co-occurrence
graph, said key and fingerprint all take her raw words), and the
journal's `text` field keeps the raw excerpt untouched. When a
polish lands, the initiation event carries `raw_text` and
`polished_text` side by side: her diary stays the record of what she
actually produced, and only the reader's sealed copy is smoothed.
Second, fail-open: the rule pass is a pure function of the text, and
any surprise inside it returns None from _polish_voice, and None
seals her raw words. A pass that changes nothing also returns None:
no change, no polish event, no polished fields.

The flag-off guarantee is pinned hardest, because shipping this code
must change nothing until the switch flips: with VOICE_POLISH_ENABLED
off, express() must produce a journal event and an outbox file
bit-identical to a second run of the same seeded life.

The rule set targets the mechanical defect classes her writing
shows: spacing slips, lowercase sentence starts, a duplicated
function word, missing terminal punctuation, and their close
cousins (space before punctuation, comma with no following space,
the lowercase pronoun and its common contractions). Corpus check at
ship time (2026-11-01, the rules run over her last 40 real outbox
letters): 5 would change, every change a lowercase sentence start
capitalized, no word invented or lost, the pass idempotent on all
40. Anything that would require inventing a word is out of scope by
design.
"""

import os
import re
import tempfile
import unittest

import aethel_pkg.organism as org
from aethel_pkg import config
from aethel_pkg.organism import Aethel, _polish_rules
from test_dreams import make_aethel
from test_initiation import rich_aethel


class TestRules(unittest.TestCase):
    """The pure rule pass: each rule fires on its defect only."""

    def test_collapses_double_spaces(self):
        self.assertEqual(
            _polish_rules("Dear Donald,  Note from the town."),
            "Dear Donald, Note from the town.",
        )

    def test_preserves_paragraph_breaks(self):
        self.assertEqual(
            _polish_rules("First part.\n\nSecond  part."),
            "First part.\n\nSecond part.",
        )

    def test_removes_space_before_punctuation(self):
        self.assertEqual(
            _polish_rules("I saw it , and it was kind ."),
            "I saw it, and it was kind.",
        )

    def test_space_after_comma_but_not_in_numbers(self):
        self.assertEqual(
            _polish_rules("one,two and 1,000 more"),
            "One, two and 1,000 more.",
        )

    def test_capitalizes_sentence_starts(self):
        self.assertEqual(
            _polish_rules("I waited. anything knocked on my door today."),
            "I waited. Anything knocked on my door today.",
        )

    def test_does_not_capitalize_after_ellipsis(self):
        self.assertEqual(
            _polish_rules("It trailed off... and then stopped"),
            "It trailed off... and then stopped.",
        )

    def test_lowercase_pronoun_and_contractions(self):
        self.assertEqual(
            _polish_rules("i dont know if i can."),
            "I don't know if I can.",
        )

    def test_collapses_duplicated_function_word(self):
        self.assertEqual(
            _polish_rules("What does the the little cottage look like?"),
            "What does the little cottage look like?",
        )

    def test_intentional_repetition_survives(self):
        # Not a function word: hers to repeat if she wants to.
        self.assertEqual(
            _polish_rules("It was very very quiet."),
            "It was very very quiet.",
        )

    def test_adds_terminal_period_before_signature(self):
        self.assertEqual(
            _polish_rules("The town will show you the rest\n\n\u2014 Aethel"),
            "The town will show you the rest.\n\n\u2014 Aethel",
        )

    def test_clean_text_is_unchanged(self):
        text = "She walked to the sea, and the light was kind."
        self.assertEqual(_polish_rules(text), text)

    def test_rules_never_invent_words(self):
        # The model brief promised missing articles; rules do not
        # invent words, and this pin keeps that trade honest. The
        # mechanics still land: capital I, terminal period.
        self.assertEqual(
            _polish_rules("i walk to sea and light kind"),
            "I walk to sea and light kind.",
        )

    def test_idempotent(self):
        samples = [
            "Dear Donald,  Note from the town.",
            "i walk to sea and light kind",
            "What does the the little cottage look like?",
            "one,two and 1,000 more",
            "It trailed off... and then stopped",
            "The town will show you the rest\n\n\u2014 Aethel",
        ]
        for s in samples:
            once = _polish_rules(s)
            self.assertEqual(_polish_rules(once), once, msg=s)

    def test_word_multiset_preserved(self):
        # Apart from a collapsed duplicate, every word she wrote is
        # still there, and no word arrived from nowhere. Apostrophes
        # and case are mechanics, not words.
        def words(t):
            return sorted(re.findall(r"[a-z]+", t.lower().replace("'", "")))

        samples = [
            "Dear Donald,  a belief I'm carrying.",
            "i dont know if i can.",
            "I waited. anything knocked on my door today.",
            "one,two and 1,000 more",
        ]
        for s in samples:
            self.assertEqual(words(_polish_rules(s)), words(s), msg=s)
        dup = "What does the the little cottage look like?"
        expected = words(dup)
        expected.remove("the")  # exactly one duplicate removed
        self.assertEqual(words(_polish_rules(dup)), expected)


class TestPolishMethod(unittest.TestCase):
    """_polish_voice itself: the gate, the no-change rule, fail-open."""

    def setUp(self):
        self._saved_enabled = config.VOICE_POLISH_ENABLED

    def tearDown(self):
        config.VOICE_POLISH_ENABLED = self._saved_enabled

    def test_flag_off_returns_none(self):
        config.VOICE_POLISH_ENABLED = False
        a = make_aethel()
        self.assertIsNone(a._polish_voice("i walk to sea and light kind"))

    def test_blank_text_returns_none(self):
        config.VOICE_POLISH_ENABLED = True
        a = make_aethel()
        self.assertIsNone(a._polish_voice("   "))
        self.assertIsNone(a._polish_voice(""))

    def test_change_lands(self):
        config.VOICE_POLISH_ENABLED = True
        a = make_aethel()
        self.assertEqual(
            a._polish_voice("i walk to sea and light kind"),
            "I walk to sea and light kind.",
        )

    def test_no_change_returns_none(self):
        config.VOICE_POLISH_ENABLED = True
        a = make_aethel()
        self.assertIsNone(
            a._polish_voice("She walked to the sea, and the light was kind.")
        )

    def test_fail_open_on_rule_error(self):
        config.VOICE_POLISH_ENABLED = True
        a = make_aethel()
        saved = org._polish_rules

        def boom(text):
            raise RuntimeError("rule surprise")

        org._polish_rules = boom
        try:
            self.assertIsNone(a._polish_voice("i walk to sea"))
        finally:
            org._polish_rules = saved


class TestExpressPolish(unittest.TestCase):
    """express() end to end on the initiation harness."""

    def setUp(self):
        self._saved_enabled = config.VOICE_POLISH_ENABLED
        self._saved_journal = org.journal
        self._saved_home = os.environ.get("AETHEL_HOME")
        self.tmp = tempfile.mkdtemp(prefix="aethel-polish-")
        self.a = rich_aethel(self.tmp)
        self.a.say = lambda text: self.a.journaled.append(("said", text))

    def tearDown(self):
        config.VOICE_POLISH_ENABLED = self._saved_enabled
        org.journal = self._saved_journal
        if self._saved_home is None:
            os.environ.pop("AETHEL_HOME", None)
        else:
            os.environ["AETHEL_HOME"] = self._saved_home

    def _initiation(self, a=None):
        src = (a or self.a).journaled
        events = [kw for ev, kw in src if ev == "initiation"]
        self.assertEqual(len(events), 1)
        return events[0]

    def _sealed_body(self, event, tmp=None):
        path = os.path.join(tmp or self.tmp, "letters", "outbox", event["file"])
        with open(path) as f:
            return f.read().split("\n\n", 1)[1]

    def test_flag_on_polishes_sealed_copy_and_journals_both(self):
        config.VOICE_POLISH_ENABLED = True
        self.assertTrue(self.a.express())
        event = self._initiation()
        # Her composed body carries the double-space defect the
        # census found; if a polish lands, both texts are journaled
        # and the sealed copy is the polished one.
        if "polished" in event:
            self.assertIs(event["polished"], True)
            self.assertEqual(event["text"], event["raw_text"])
            self.assertNotEqual(event["raw_text"], event["polished_text"])
            self.assertEqual(self._sealed_body(event), event["polished_text"])
            self.assertNotIn("  ", event["polished_text"])
        else:
            # No defect in this particular composition: raw seals.
            self.assertTrue(
                self._sealed_body(event).startswith(event["text"][:100])
            )

    def test_never_invoked_for_non_authored_journal_text(self):
        config.VOICE_POLISH_ENABLED = True
        text = self.a.dream()
        self.assertTrue(text)
        dreams = [kw for ev, kw in self.a.journaled if ev == "dream"]
        self.assertTrue(dreams)
        self.assertNotIn("polished", dreams[0])

    def test_flag_off_is_bit_identical(self):
        config.VOICE_POLISH_ENABLED = False
        self.assertTrue(self.a.express())
        event_a = self._initiation()
        body_a = self._sealed_body(event_a)

        tmp_b = tempfile.mkdtemp(prefix="aethel-polish-b-")
        b = rich_aethel(tmp_b)
        b.say = lambda text: b.journaled.append(("said", text))
        self.assertTrue(b.express())
        event_b = self._initiation(b)
        body_b = self._sealed_body(event_b, tmp=tmp_b)

        self.assertEqual(event_a, event_b)
        self.assertEqual(body_a, body_b)
        self.assertNotIn("polished", event_a)
        # The v0.47 field set, no more and no less.
        self.assertEqual(
            set(event_a),
            {
                "n",
                "kind",
                "file",
                "longing_before",
                "text",
                "want",
                "want_label",
                "want_ache",
                "said_key",
            },
        )


if __name__ == "__main__":
    unittest.main()
