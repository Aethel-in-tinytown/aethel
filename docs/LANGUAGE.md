# Optional English language backend

Heuristics remain the default and need only Python's standard library. NLTK is an
explicit choice for a life. It changes learning and recall, so the same seed can
produce different lives across backends. Council scoring and the ownership of
grammar rules are unchanged. No new UI panels are added.

## Install and provision

```sh
python3 -m pip install '.[nlp]'       # nltk==3.9.2
# For the web service, install '.[web,nlp]' (or '.[web,fast,nlp]').
python3 -m aethel_pkg.language_resources --download
python3 aethel_live.py --language-backend nltk
# The same selection works in the web simulation worker:
python3 aethel_live.py --serve --language-backend nltk
```

Provisioning defaults to `$AETHEL_HOME/nltk_data` (with the normal AETHEL_HOME
default). `AETHEL_NLTK_DATA` selects a shared, provisioned model directory. Set it
in the environment of both provisioning and launch, or provision with
`--data-dir /absolute/path`. The resource directory must not already exist; use a
new directory to replace an incomplete or incompatible installation.

The provisioning command alone downloads data. It verifies SHA-256 checksums
before extraction, stages the entire installation, and publishes it only after
all model files verify. It does not require the optional package itself. It
retains the original archives, resource readmes, and license notices. The lock in
`aethel_pkg/nlp_data/resources.json` pins the upstream revision and every extracted
file for `punkt_tab` (English only), `averaged_perceptron_tagger_eng`, and WordNet
3.0. Runtime checks the extracted model bytes on every startup, including when
models are already cached in the process. Pickled models are not used.

Provision an offline machine by copying the provisioned directory, or copy the
three named `.zip` files from its `archives/` directory and run:

```sh
python3 -m aethel_pkg.language_resources --from-dir /media/nltk-archives \
  --data-dir /srv/aethel-models
AETHEL_NLTK_DATA=/srv/aethel-models python3 aethel_live.py \
  --offline --language-backend nltk --ticks 10 --time-scale 100
```

Install the Python extra from a local wheelhouse when the machine has no package
network access. Runtime never downloads or trains models. `--offline` also turns
off network forage; it is independent of language selection. NLTK's global data
search path and `NLTK_DATA` do not select models for this pipeline.

## Resume, switch, and compatibility

Omitting `--language-backend` resumes the saved backend. Saves made before this
feature use heuristics. Merely installing NLTK does not activate it. Use an
explicit `--language-backend heuristic` or `--language-backend nltk` to switch a
life; save a backup first if you want to compare separate continuations.

Each saved state and API status includes `language`: `backend`,
`pipeline_revision`, `nltk_version`, and a `resources` map of artifact SHA-256
fingerprints. Missing packages, a different NLTK version, changed model files, or
a saved pipeline/fingerprint mismatch reject startup before any heartbeat. The
web worker reports the failure and the server exits without an initial snapshot.
There is no automatic fallback or implicit model migration. Even explicitly
selecting the same backend cannot bypass a version mismatch: restore the pinned
model/software version, or explicitly switch to the other backend.

Activation adds a `lemma_index` mapping canonical lemmas to surface-form counts.
It retains historical `concepts` counts, learned word provenance, beliefs, kept
passages, and journals. New NLTK acquisitions increment both the original surface
count and its contextual lemma's alias count. Old vocabulary has no original POS
context, so activation uses saved grammatical tags where available and noun
lemmatization otherwise. A single spelling may have multiple contextual lemmas.
Goal baselines are translated so accumulated growth and progress survive a
switch. Existing goal wording and historical counts are preserved. Co-occurrence
edges merge under canonical lemmas on activation; switching back to heuristics
clears that derived graph because canonical edges have no unique surface inverse.
A later NLTK activation rebuilds the index from then-current surface counts.

## Behavior and limits

- Learning admits alphabetic content words of at least two characters (nouns,
  verbs, adjectives, adverbs), while excluding the existing stopwords and page
  scaffolding in both surface and lemma forms. Some short everyday verbs, such as
  `run` and `eat`, are already stopwords and remain excluded.
- Contextual POS supplies new acquisition tags before suffix guesses. Existing
  provenance, known people, and exact domain vocabulary retain priority. POS
  never establishes that an unknown noun is a person, food, or concrete object;
  unknown nouns remain unclassified. Explicit unclassified acquisition records
  prevent later suffix guessing from overriding that context.
- Lesson examples and newly kept passages use sentence boundaries. Text and
  attribution stay in their original form. Smart quotes, unspaced Unicode dashes,
  and Unicode ellipses use equal-width punctuation substitutions for analysis;
  all returned offsets still refer to the original text. The existing 180/600 character caps
  and passage-selection decisions remain; a first sentence longer than 600
  characters uses the old capped prefix.
- Recall and open-question keywords use normalized whole tokens, including short
  words. Recall still requires two overlapping terms, excludes the current tick,
  keeps newest-first ordering for ties, and returns original text under its
  existing length cap. It does not expand synonyms or infer entities.
- Models load once per resource directory in the simulation process. Each meal
  is analyzed once for learning, grammar examples, and passages. Recall analysis
  uses a 512-entry LRU; texts above 16,000 characters are not cached.

English tagging and WordNet morphology are imperfect. For example, the fixture
phrase “Then the mice swam!” tags `swam` as a noun, while “She swam through the
gardens” correctly tags it as a verb and normalizes it to `swim`. Learned tags
keep their acquisition provenance, so later contexts do not silently rewrite
old classifications. Determinism is promised within the same backend, pipeline,
and pinned models, with the project's existing timestamp exclusions.

The package license, tagger MIT notice, WordNet license, Punkt readme and upstream
dataset licensing catalog ship under `nlp_data/licenses`. The upstream catalog
has no license attribute for Punkt models; that absence is preserved, not
replaced with a claim that all datasets have NLTK's package license. See the
[official NLTK data catalog](https://github.com/nltk/nltk_data/blob/550b6625bcef1f2abff2ff770a5a0d272c9c6b2a/index.xml)
and [dataset license notes](https://github.com/nltk/nltk_data/blob/550b6625bcef1f2abff2ff770a5a0d272c9c6b2a/DATASET-LICENSES.md).

## Local comparison

Run `AETHEL_NLTK_DATA=/path/to/data PYTHONHASHSEED=0 python
scripts/compare_language.py` with the NLTK environment. It uses isolated temporary
homes and one subprocess per backend. On Linux, Python 3.10, NLTK 3.9.2, seed
20261019, and 160 ticks on 2026-10-22:

| Measurement | Heuristic | NLTK |
| --- | ---: | ---: |
| Cold life construction including model loading | 0.010 s | 2.510 s |
| 160 ticks after models are loaded | 0.629 s | 1.702 s |
| Peak process RSS, including models | 26.51 MiB | 169.70 MiB |
| Three reading fixtures: surface words | 21 | 32 |
| Three reading fixtures: canonical words | 21 | 31 |
| Seeded life: surface / canonical words | 61 / 61 | 76 / 76 |
| Seeded life: meals | 69 | 62 |

These are single-run development observations, not throughput guarantees. The
seeded lives use the repository's deterministic canned reading fixtures, not live
web content. Different acquisition changes novelty, goals, and later choices,
which explains the different meal counts. The reading fixtures learn `red` and
`gem` only in NLTK mode, classify `building` as unknown instead of a verb, retain
Donald as a person and `course` as study, and exclude `subscribe`/`navigation`
from new knowledge. Both backends leave `quokka` unclassified. For recall, NLTK
finds “She swam through the gardens” for `swimming garden`; heuristics miss it.
Heuristics return “discussion … information” for `discuss inform`; NLTK rejects
that substring false positive.

Phrases, a source-backed vocabulary notebook, semantic recall, entity recognition,
and reading-tone annotations remain deferred. There is no sentiment effect,
runtime training, or council change in this release.
