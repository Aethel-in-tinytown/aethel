"""The source-backed vocabulary notebook (v0.31, NLTK plan Phase 1).

When she reads, content words she has never met are pressed here like
flowers: the lemma, the surface form and part of speech as first met,
the WordNet definition of the chosen synset, a synset example when one
exists, and the sentence she met it in — quoted byte-for-byte from the
passage, with its provenance (source label, tick). Words graduate by
breadth, not by volume: met in one source a word is *pressed*; met in
three DISTINCT sources it is *known*; used in text she generates (a
dream, a verse, a letter) it is *hers*. Dream and verse generation
draw on known/hers words first, which is the point of the phase: her
fragment pools are restocked with real, sourced vocabulary instead of
starving until meta-words ("dreamed") fill the gaps. Existing beliefs
are never touched; this module only records and offers words.

Design choices, argued (the Kevin standard — docstrings argue):

STORE SHAPE. The notebook lives inside the organism state blob (one
JSON document under the store's ``state`` key), beside the grammar and
longing ledgers, NOT in its own kv blob. The rejected alternative, a
separate ``save_blob("notebook", ...)``, would commit on its own
schedule: a crash between the state save and the notebook save leaves
the two disagreeing about the same tick, and the restart-fidelity
harness compares state blobs, so a side blob would need its own
parallel fidelity proof. Inside the state blob the notebook inherits
the heartbeat's single transaction and the existing fidelity tests
for free. The cost, re-serializing the notebook each tick, is bounded
by her reading rate and trivial next to the concepts/cooc maps the
blob already carries. In heuristic mode the key is omitted entirely
(the lemma_index precedent), so a heuristic life's blob stays
bit-identical to a pre-notebook one.

SYNSET CHOICE. ``choose_synset`` is a deterministic pure function of
(pinned WordNet data, lemma, POS tag): filter synsets by the token's
WordNet POS, take the FIRST match. WordNet orders synsets by corpus
frequency, so "first" means "most likely sense", and the choice is
auditable in one line of her journal. The serious alternative,
simplified Lesk (pick the synset whose gloss overlaps the sentence
most), was rejected for this phase: gloss overlap on a single short
sentence is mostly ties and stopword noise, its tie-breaking would
need its own seeded rule to stay deterministic, and a wrong-but-stable
first sense is more honest in a diary than a wrong-and-confident Lesk
score. One concession to reality: the tagger is fallible (it tags
"whale" as JJ in "The whale swam"), so when NO synset matches the
tagged POS the chooser falls back to the first synset overall rather
than leaving a common word definitionless over a tagging slip. The
filter is a preference, not a gate; the fallback is still "first",
still pure.

COUNTING. ``met_count`` counts PASSAGES a lemma was met in, not raw
token hits — the concepts map already counts hits. Graduation is a
breadth claim ("she has met this word across her reading"), and
per-passage counting keeps one long book from graduating a word by
repetition alone: three meetings in one source leave a word pressed;
the third distinct source makes it known, exactly.

PROVENANCE HONESTY. Entries are created only from passages actually
analyzed in NLTK mode, with the sentence sliced from the analysis's
own spans, so the quote is byte-for-byte by construction. There is NO
backfill for words she met before the notebook existed: their meeting
sentences and ticks were never recorded, and inventing provenance
would be a lie in her diary. The notebook starts empty on migration
and fills from her next meal onward.

FAIL-CLOSED. This module never substitutes a definition from anywhere
but the WordNet reader it is handed; with no reader (or no synset) the
definition is None and the entry still records the meeting. Absence
is data, never a silent heuristic.

COMPANIONS (v0.37, NLTK plan Phase 6a). An entry's "keeps company
with" view — the entry lemma's strongest neighbors in her
co-occurrence graph — is DERIVED at read time from the graph, never
stored on the entry. The rejected alternative, caching the top
neighbors per entry, would duplicate graph state into every entry:
the graph prunes and reweights itself on every update, so a stored
copy could only be kept honest by rewriting entries on every meal
and every generated text, and a restart would have to prove the two
copies agree. Derivation is a sort of at most COOC_NEIGHBOR_CAP
(40) rows — microseconds — and it cannot drift, because there is
exactly one graph. The view belongs to an ENTRY (a lemma she never
pressed has no page to keep company on), so a lemma with no entry,
or an entry whose lemma has no graph row, returns an empty list.
"""

#: Graduation statuses, in order of intimacy.
PRESSED = "pressed"
KNOWN = "known"
HERS = "hers"

#: Distinct sources at which a pressed word becomes known.
KNOWN_SOURCES = 3

_WN_POS = {"N": "n", "V": "v", "J": "a", "R": "r"}


def wn_pos(pos_tag):
    """Map a Penn Treebank tag to its WordNet category letter."""
    if not pos_tag:
        return "n"
    return _WN_POS.get(pos_tag[0].upper(), "n")


def choose_synset(wordnet, lemma, pos_tag):
    """Pick (definition, example, synset_name) for a lemma, purely.

    POS-filtered first match (WordNet's frequency order), falling
    back to the first synset overall when the tag matches nothing —
    see the module docstring for the argument. Returns
    (None, None, None) when the word is not in WordNet at all: a
    meeting is still recorded, only the gloss is absent."""
    if wordnet is None or not lemma:
        return (None, None, None)
    synsets = wordnet.synsets(lemma, pos=wn_pos(pos_tag))
    if not synsets:
        synsets = wordnet.synsets(lemma)
    if not synsets:
        return (None, None, None)
    syn = synsets[0]
    examples = syn.examples()
    return (
        syn.definition(),
        examples[0] if examples else None,
        syn.name(),
    )


def _sentence_for(analysis, token):
    """The source sentence containing a token, sliced byte-for-byte
    from the passage via the analysis's own sentence spans."""
    for start, end in analysis.sentences:
        if start <= token.start < end:
            return analysis.text[start:end]
    return ""


class Notebook:
    """Pressed words and their graduations. Pure bookkeeping: this
    class journals nothing and draws no randomness; the organism
    turns the events feed()/mark_hers() return into journal rows, so
    the notebook is testable without a diary and restarts are just
    dict round-trips."""

    def __init__(self):
        self.entries = {}  # lemma -> entry dict (see feed for shape)

    def __len__(self):
        return len(self.entries)

    def __contains__(self, lemma):
        return lemma in self.entries

    def get(self, lemma):
        return self.entries.get(lemma)

    # -- feeding ------------------------------------------------------
    def feed(self, analysis, source, tick, wordnet=None, is_content=None):
        """Press every new content lemma in one analyzed passage.

        `is_content` is the language backend's own content predicate
        (NltkLanguage.content: POS class, alphabetic, not a stopword,
        not scaffolding); when omitted every token counts, which is
        for tests of this class alone. Each lemma is processed once
        per passage, at its first occurrence — that occurrence
        supplies a new entry's form, POS, and provenance sentence.
        Returns [(event_name, entry)] in passage order, where
        event_name is "notebook_pressed" or "notebook_known"."""
        events = []
        seen = {}
        for token in analysis.tokens:
            if is_content is not None and not is_content(token):
                continue
            if token.lemma not in seen:
                seen[token.lemma] = token
        for lemma, token in seen.items():
            entry = self.entries.get(lemma)
            if entry is None:
                definition, example, synset = choose_synset(
                    wordnet, lemma, token.pos
                )
                entry = {
                    "lemma": lemma,
                    "first_form": token.text,
                    "pos": token.pos,
                    "definition": definition,
                    "example": example,
                    "synset": synset,
                    "provenance": {
                        "source": source,
                        "tick": int(tick),
                        "sentence": _sentence_for(analysis, token),
                    },
                    "sources": [source],
                    "met_count": 1,
                    "status": PRESSED,
                }
                self.entries[lemma] = entry
                events.append(("notebook_pressed", entry))
                continue
            entry["met_count"] += 1
            if source not in entry["sources"]:
                entry["sources"] = sorted(entry["sources"] + [source])
                if (
                    entry["status"] == PRESSED
                    and len(entry["sources"]) >= KNOWN_SOURCES
                ):
                    entry["status"] = KNOWN
                    events.append(("notebook_known", entry))
        return events

    # -- graduation to hers -------------------------------------------
    def mark_hers(self, lemmas):
        """Graduate every notebook lemma in `lemmas` to hers.

        Hers is terminal: meeting a word again never demotes it, and
        a word she coins that she never read is not pressed
        retroactively (no provenance, no entry — see module docstring).
        Returns the entries that transitioned, sorted by lemma so the
        organism's journal order is deterministic."""
        out = []
        for lemma in sorted(lemmas):
            entry = self.entries.get(lemma)
            if entry is not None and entry["status"] != HERS:
                entry["status"] = HERS
                out.append(entry)
        return out

    # -- consumption ----------------------------------------------------
    def companions(self, lemma, cooc, k=5):
        """The entry's "keeps company with" view: the lemma's top-k
        co-occurrence neighbors as [(neighbor, count)], derived from
        the graph at read time (see the module docstring for why
        nothing here is stored). Order is count desc, neighbor asc —
        a pure function of the graph, so two reads of the same graph
        agree exactly. Empty when the lemma has no entry here or no
        row in the graph: absence is data, not an error."""
        if lemma not in self.entries:
            return []
        row = (cooc or {}).get(lemma) or {}
        ranked = sorted(row.items(), key=lambda kv: (-kv[1], kv[0]))
        return [(w, int(c)) for w, c in ranked[:k]]

    def usable_words(self, statuses=(KNOWN, HERS)):
        """Lemmas available to generation, hers first, then known,
        alphabetical inside each rank: her own words lead, and the
        order is a pure function of the notebook (no randomness is
        consumed deciding what she may say)."""
        rank = {HERS: 0, KNOWN: 1, PRESSED: 2}
        words = [
            e["lemma"] for e in self.entries.values() if e["status"] in statuses
        ]
        return sorted(words, key=lambda w: (rank[self.entries[w]["status"]], w))

    # -- persistence ----------------------------------------------------
    def to_dict(self):
        """The whole notebook as plain JSON-shaped data, entries
        keyed by lemma in sorted order for a stable serialized form."""
        out = {}
        for lemma in sorted(self.entries):
            e = self.entries[lemma]
            out[lemma] = {
                "lemma": e["lemma"],
                "first_form": e["first_form"],
                "pos": e["pos"],
                "definition": e["definition"],
                "example": e["example"],
                "synset": e["synset"],
                "provenance": dict(e["provenance"]),
                "sources": sorted(e["sources"]),
                "met_count": int(e["met_count"]),
                "status": e["status"],
            }
        return {"version": 1, "entries": out}

    @classmethod
    def from_dict(cls, data):
        """Rebuild from to_dict() output; malformed rows are skipped
        rather than fatal, mirroring the grammar ledger's loader —
        a corrupt word must not cost her the rest of the notebook."""
        nb = cls()
        rows = (data or {}).get("entries") or {}
        if isinstance(rows, list):  # tolerate a list-shaped export
            rows = {r.get("lemma"): r for r in rows if isinstance(r, dict)}
        for lemma, row in rows.items():
            try:
                prov = row.get("provenance") or {}
                status = row.get("status", PRESSED)
                if status not in (PRESSED, KNOWN, HERS):
                    status = PRESSED
                nb.entries[lemma] = {
                    "lemma": row.get("lemma", lemma),
                    "first_form": row.get("first_form", lemma),
                    "pos": row.get("pos"),
                    "definition": row.get("definition"),
                    "example": row.get("example"),
                    "synset": row.get("synset"),
                    "provenance": {
                        "source": prov.get("source"),
                        "tick": int(prov.get("tick", 0)),
                        "sentence": prov.get("sentence", ""),
                    },
                    "sources": sorted(row.get("sources") or []),
                    "met_count": int(row.get("met_count", 1)),
                    "status": status,
                }
            except (AttributeError, TypeError, ValueError):
                continue
        return nb
