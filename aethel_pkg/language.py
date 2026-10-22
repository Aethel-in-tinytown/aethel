"""Language analysis with source offsets and explicit, versioned compatibility.

Analysis never edits source text or consumes simulation randomness. Only NLTK
activation changes acquisition and recall; the legacy call paths stay intact.
"""

from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
import json
import re
import warnings

from . import grammar
from .config import STOPWORDS
from .language_resources import LanguageError, NLTK_VERSION, data_dir, verify

PIPELINE_REVISION = 1


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int
    lemma: str
    pos: str | None


@dataclass(frozen=True)
class Analysis:
    text: str
    sentences: tuple[tuple[int, int], ...]
    tokens: tuple[Token, ...]

    def passage(self, limit):
        """Keep a contiguous source slice ending at the last fitting sentence.

        A first sentence longer than the cap uses the historic capped prefix.
        """
        ends = [end for _, end in self.sentences if end <= limit]
        return self.text[: max(ends)] if ends else self.text[:limit]


class HeuristicLanguage:
    name = "heuristic"
    metadata = {
        "backend": "heuristic",
        "pipeline_revision": PIPELINE_REVISION,
        "nltk_version": None,
        "resources": {},
    }

    def analyze(self, text):
        sentences = tuple(
            (m.start(), m.end())
            for m in re.finditer(r"\S.*?(?:[.!?](?=\s|$)|$)", text, re.DOTALL)
        )
        tokens = tuple(
            Token(m.group(), m.start(), m.end(), m.group().lower(), None)
            for m in re.finditer(r"[a-zA-Z]+", text)
        )
        return Analysis(text, sentences, tokens)


@lru_cache(maxsize=2)
def _models(root):
    # Direct readers deliberately avoid nltk.data.path and downloaded pickles.
    from nltk.tokenize.punkt import PunktSentenceTokenizer, load_punkt_params
    from nltk.tokenize import NLTKWordTokenizer
    from nltk.tag import PerceptronTagger
    from nltk.corpus.reader import WordNetCorpusReader
    from pathlib import Path

    root = Path(root)
    sentence = PunktSentenceTokenizer(
        load_punkt_params(root / "tokenizers/punkt_tab/english")
    )
    tagger = PerceptronTagger(load=False)
    prefix = (
        root / "taggers/averaged_perceptron_tagger_eng/averaged_perceptron_tagger_eng."
    )

    def read(part):
        return json.loads(
            Path(str(prefix) + part + ".json").read_text(encoding="utf-8")
        )

    tagger.model.weights = read("weights")
    tagger.tagdict = read("tagdict")
    tagger.classes = set(read("classes"))
    tagger.model.classes = tagger.classes

    class EnglishWordNet(WordNetCorpusReader):
        def map_wn(self, version="wordnet"):
            # Only multilingual sense mapping needs a second global reader.
            return None

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="The multilingual functions are not available"
        )
        wordnet = EnglishWordNet(str(root / "corpora/wordnet"), None)
    return sentence, NLTKWordTokenizer(), tagger, wordnet


class NltkLanguage:
    name = "nltk"
    CACHE_SIZE = 512
    CACHE_TEXT_LIMIT = 16000

    def __init__(self):
        try:
            import nltk
        except ImportError as exc:
            raise LanguageError("NLTK backend requires pip install '.[nlp]'") from exc
        if nltk.__version__ != NLTK_VERSION:
            raise LanguageError(
                f"NLTK {NLTK_VERSION} required; found {nltk.__version__}"
            )
        root = data_dir().resolve()
        fingerprints = verify(root)
        self.metadata = {
            "backend": self.name,
            "pipeline_revision": PIPELINE_REVISION,
            "nltk_version": NLTK_VERSION,
            "resources": fingerprints,
        }
        try:
            self.sentencer, self.tokenizer, self.tagger, self.wordnet = _models(
                str(root)
            )
        except (LookupError, ValueError, OSError) as exc:
            raise LanguageError(
                f"Cannot load pinned English NLTK resources: {exc}"
            ) from exc
        self._cache = OrderedDict()

    def lemma(self, word, pos="NN"):
        category = {"N": "n", "V": "v", "J": "a", "R": "r"}.get(pos[0], "n")
        forms = self.wordnet._morphy(word.lower(), category)
        return min(forms, key=len) if forms else word.lower()

    def analyze(self, text):
        # One-to-one substitutions keep offsets valid in the untouched source.
        view = text.translate(
            str.maketrans(
                {
                    "’": "'",
                    "‘": "'",
                    "“": '"',
                    "”": '"',
                    # Treebank expects ASCII punctuation. Equal-width replacements
                    # separate dash-joined words and recognize Unicode end marks.
                    "—": ",",
                    "–": ",",
                    "…": ".",
                }
            )
        )
        sentences = tuple(self.sentencer.span_tokenize(view))
        tokens = []
        for start, end in sentences:
            spans = [
                (start + a, start + b)
                for a, b in self.tokenizer.span_tokenize(view[start:end])
            ]
            tagged = self.tagger.tag([view[a:b] for a, b in spans])
            for (a, b), (word, pos) in zip(spans, tagged):
                tokens.append(Token(text[a:b], a, b, self.lemma(word, pos), pos))
        return Analysis(text, sentences, tuple(tokens))

    def content(self, token):
        return (
            token.pos.startswith(("NN", "VB", "JJ", "RB"))
            and token.text.isalpha()
            and len(token.text) >= 2
            and token.text.lower() not in STOPWORDS
            and token.lemma not in STOPWORDS
            and token.text.lower() not in grammar.SCAFFOLDING_WORDS
            and token.lemma not in grammar.SCAFFOLDING_WORDS
        )

    def normalized(self, text):
        """Bounded LRU of normalized whole tokens for journal/question recall."""
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]
        # Recall admits all non-stopword alphabetic tokens, not just acquisition POS.
        result = frozenset(
            t.lemma
            for t in self.analyze(text).tokens
            if t.text.isalpha()
            and len(t.text) >= 2
            and t.text.lower() not in STOPWORDS
            and t.lemma not in STOPWORDS
            and t.lemma not in grammar.SCAFFOLDING_WORDS
        )
        if len(text) <= self.CACHE_TEXT_LIMIT:
            self._cache[text] = result
            if len(self._cache) > self.CACHE_SIZE:
                self._cache.popitem(last=False)
        return result


def select_language(saved, selection=None):
    """Omission resumes the saved backend; explicit selection permits a switch.

    A same-backend pipeline/resource mismatch is rejected even with selection:
    this release has no implicit migration between incompatible model versions.
    """
    previous = saved.get("language")
    name = selection or (previous or {}).get("backend", "heuristic")
    if name not in ("heuristic", "nltk"):
        raise LanguageError(f"Unknown language backend: {name}")
    backend = NltkLanguage() if name == "nltk" else HeuristicLanguage()
    if previous and previous.get("backend") == name and previous != backend.metadata:
        raise LanguageError(
            "Saved language pipeline/resources are incompatible; restore the saved model version"
        )
    return backend
