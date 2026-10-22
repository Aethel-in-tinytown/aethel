"""Provide portable SplitMix64 randomness and named independent streams.

Stream names use FNV-1a rather than Python hash(), whose values vary between
processes. Save every stream state to resume the exact sequence after restart.
Golden vectors in tests pin the integer algorithm and sampling behavior."""

_MASK = (1 << 64) - 1
_GOLDEN = 0x9E3779B97F4A7C15
_MIX1 = 0xBF58476D1CE4E5B9
_MIX2 = 0x94D049BB133111EB


DEFAULT_SEED = 0xAE7E1001


def _mix64(z):
    """Apply the specified unsigned 64-bit mixing finalizer."""
    z &= _MASK
    z = ((z ^ (z >> 30)) * _MIX1) & _MASK
    z = ((z ^ (z >> 27)) * _MIX2) & _MASK
    return z ^ (z >> 31)


def fnv1a64(text):
    """Hash a stream name reproducibly across interpreter processes."""
    h = 0xCBF29CE484222325
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 0x100000001B3) & _MASK
    return h


class SplitMix64:
    """Generate deterministic draws from a single unsigned 64-bit state."""

    __slots__ = ("state", "_master", "name")

    def __init__(self, seed, name=""):
        self.state = seed & _MASK
        self._master = seed & _MASK
        self.name = name

    def next_uint64(self):
        self.state = (self.state + _GOLDEN) & _MASK
        return _mix64(self.state)

    def random(self):
        """Return a uniform float in [0, 1) from the generator’s top 53 bits."""
        return (self.next_uint64() >> 11) * (1.0 / (1 << 53))

    def randbelow(self, n):
        """Return an unbiased integer below n using rejection sampling."""
        if n <= 0:
            raise ValueError("randbelow needs n > 0")

        rem = (-n) % n
        while True:
            x = self.next_uint64()
            if x >= rem:
                return x % n

    def randint(self, a, b):
        """Draw an integer including both interval endpoints."""
        return a + self.randbelow(b - a + 1)

    def choice(self, seq):
        if not seq:
            raise IndexError("choice from empty sequence")
        return seq[self.randbelow(len(seq))]

    def shuffle(self, lst):
        """Permute the supplied list in place using Fisher–Yates draws."""
        for i in range(len(lst) - 1, 0, -1):
            j = self.randbelow(i + 1)
            lst[i], lst[j] = lst[j], lst[i]

    def sample(self, population, k):
        """Draw k distinct elements while preserving their draw order."""
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
        """Choose an option in proportion to its positive weight."""
        total = sum(weights)
        if total <= 0:
            raise ValueError("weights must sum to a positive value")
        r = self.random() * total
        acc = 0.0
        for opt, w in zip(options, weights):
            acc += w
            if r < acc:
                return opt
        return options[-1]

    def spawn(self, name):
        """Derive a reproducible child generator without consuming the parent stream."""
        return SplitMix64(_mix64(self._master ^ fnv1a64(name)), name=name)

    def get_state(self):
        return self.state

    def set_state(self, state):
        self.state = state & _MASK


class Streams:
    """Derive named generators and serialize every live generator state."""

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
