"""Deterministic randomness: one seed, many streams, same life everywhere.

Aethel's decisions should be reproducible. The Python `random` module is
fine but its seeding conventions differ across versions and platforms in
ways we don't control; what we want is a tiny, fully specified PRNG whose
entire behavior is defined by 64-bit integer arithmetic — identical on
every machine, every OS, every Python.

SplitMix64 (Vigna, 2015) is exactly that: one 64-bit state, one golden-ratio
increment, three xorshift-multiply rounds. It passes BigCrush, has a period
of 2**64, and is the reference seeding generator for the whole xoshiro
family. Pure Python, no dependencies — the sandbox law (stdlib only) holds.

Design:
- One master seed per life (env AETHEL_SEED or --seed; default fixed, so a
  fresh Aethel is born deterministic).
- Named child streams ("organism", "town", "dreams", "forage") spawned by
  mixing the master seed with an FNV-1a hash of the name — Python's own
  hash() is per-process randomized and must never be used for this.
- Each stream's 64-bit state is persisted with her state, so a save/load
  resumes the exact sequence mid-stream. Restart == same life continues.

Golden vectors in tests/test_rng.py were cross-checked against the original
C reference implementation compiled with gcc.
"""

_MASK = (1 << 64) - 1
_GOLDEN = 0x9E3779B97F4A7C15
_MIX1 = 0xBF58476D1CE4E5B9
_MIX2 = 0x94D049BB133111EB

#: Born-seed for a fresh organism when none is supplied. Chosen once, fixed
#: forever: a fresh Aethel is born deterministic (override via AETHEL_SEED).
DEFAULT_SEED = 0xAE7E1001


def _mix64(z):
    """The splitmix finalizer, standalone — used to spawn stream seeds."""
    z &= _MASK
    z = ((z ^ (z >> 30)) * _MIX1) & _MASK
    z = ((z ^ (z >> 27)) * _MIX2) & _MASK
    return z ^ (z >> 31)


def fnv1a64(text):
    """FNV-1a 64-bit — deterministic string hashing, unlike hash()."""
    h = 0xCBF29CE484222325
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 0x100000001B3) & _MASK
    return h


class SplitMix64:
    """A self-contained deterministic PRNG. State is a single uint64.

    drop-in for the `random` calls Aethel uses: random(), randint(a, b)
    (inclusive, like random.randint), choice(seq), sample(pop, k),
    shuffle(list), and weighted_choice(options, weights).
    """

    __slots__ = ("state", "_master", "name")

    def __init__(self, seed, name=""):
        self.state = seed & _MASK
        self._master = seed & _MASK
        self.name = name

    # -- core ---------------------------------------------------------
    def next_uint64(self):
        self.state = (self.state + _GOLDEN) & _MASK
        return _mix64(self.state)

    def random(self):
        """float in [0.0, 1.0) from the top 53 bits (like random.random)."""
        return (self.next_uint64() >> 11) * (1.0 / (1 << 53))

    def randbelow(self, n):
        """Unbiased int in [0, n) via rejection sampling (Lemire-style)."""
        if n <= 0:
            raise ValueError("randbelow needs n > 0")
        # Reject the top `rem` values so every bucket has equal count.
        rem = (-n) % n  # == (2**64) % n without floats
        while True:
            x = self.next_uint64()
            if x >= rem:
                return x % n

    def randint(self, a, b):
        """Inclusive [a, b], matching random.randint semantics."""
        return a + self.randbelow(b - a + 1)

    # -- sequences ------------------------------------------------------
    def choice(self, seq):
        if not seq:
            raise IndexError("choice from empty sequence")
        return seq[self.randbelow(len(seq))]

    def shuffle(self, lst):
        """In-place Fisher–Yates."""
        for i in range(len(lst) - 1, 0, -1):
            j = self.randbelow(i + 1)
            lst[i], lst[j] = lst[j], lst[i]

    def sample(self, population, k):
        """k unique elements, like random.sample (order = draw order)."""
        n = len(population)
        if not 0 <= k <= n:
            raise ValueError("sample larger than population or negative")
        pool = list(population)
        out = []
        for i in range(k):
            j = i + self.randbelow(n - i)
            pool[i], pool[j] = pool[j], pool[i]
            out.append(pool[i])
        return out

    def weighted_choice(self, options, weights):
        """One option, probability proportional to weight. Weights > 0."""
        total = sum(weights)
        if total <= 0:
            raise ValueError("weights must sum to a positive value")
        r = self.random() * total
        acc = 0.0
        for opt, w in zip(options, weights):
            acc += w
            if r < acc:
                return opt
        return options[-1]  # float-rounding guard

    # -- streams ----------------------------------------------------------
    def spawn(self, name):
        """A child stream, deterministically derived. The same master seed
        and stream name always yield the same child sequence."""
        return SplitMix64(_mix64(self._master ^ fnv1a64(name)), name=name)

    # -- persistence ------------------------------------------------------
    def get_state(self):
        return self.state

    def set_state(self, state):
        self.state = state & _MASK


class Streams:
    """The organism's named streams, plus save/load of their live states.

    One hub per process, built from the master seed. Persisting
    `dump()` alongside her state makes restart bit-exact.
    """

    def __init__(self, seed):
        self.master = SplitMix64(seed, name="master")
        self._streams = {}

    def stream(self, name):
        s = self._streams.get(name)
        if s is None:
            s = self.master.spawn(name)
            self._streams[name] = s
        return s

    def dump(self):
        return {name: s.get_state() for name, s in self._streams.items()}

    def restore(self, states):
        for name, st in (states or {}).items():
            self.stream(name).set_state(st)
