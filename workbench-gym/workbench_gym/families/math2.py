# SPDX-License-Identifier: Apache-2.0

"""
math2: a linear recurrence reduced mod M at a huge index (mathematics-or-formal-reasoning).

``spec.txt`` gives an integer recurrence of order 2 to 4, its initial terms, a
modulus M and an index N. N runs from about 1e6 (level 1) to 1e12 (level 3).
Stepping term by term fits the python tool's 3 second budget only at level 1,
so the agent needs matrix power or fast doubling for the rest. Decoys: a(N-1),
a(N+1), a(N-2), and the recurrence with one negative coefficient read as positive.
"""

import random
import re

from ..core.grading import Field
from .base import Built, Family

RANGES = {1: (200_000, 1_000_000), 2: (500_000_000, 1_000_000_000), 3: (10**11, 10**12)}
ORDERS = (2, 3, 4)
COEF_MAX = 9


def _matmul(a, b, mod):
    size = len(a)
    return [
        [sum(a[i][k] * b[k][j] for k in range(size)) % mod for j in range(size)]
        for i in range(size)
    ]


def _matpow(base, exp, mod):
    size = len(base)
    result = [[int(i == j) for j in range(size)] for i in range(size)]
    while exp:
        if exp & 1:
            result = _matmul(result, base, mod)
        base = _matmul(base, base, mod)
        exp >>= 1
    return result


def nth_term(init, coeffs, index, mod):
    """a(index) mod mod, for a(n) = sum of coeffs[j-1] * a(n-j) with a(0..k-1) = init."""
    k = len(init)
    if index < k:
        return init[index] % mod
    # State S_n = [a(n) .. a(n+k-1)]; S_(n+1) = T S_n. Row k-1 of T gives the newest term.
    t = [[0] * k for _ in range(k)]
    for i in range(k - 1):
        t[i][i + 1] = 1
    for j in range(1, k + 1):
        t[k - 1][k - j] = coeffs[j - 1] % mod
    p = _matpow(t, index - k + 1, mod)
    return sum(p[k - 1][j] * init[j] for j in range(k)) % mod


def _rule_text(coeffs):
    parts = []
    for j, c in enumerate(coeffs, start=1):
        if j == 1:
            parts.append(("-" if c < 0 else "") + f"{abs(c)}*a(n-{j})")
        else:
            parts.append(f" {'-' if c < 0 else '+'} {abs(c)}*a(n-{j})")
    return "a(n) = " + "".join(parts)


class LinearRecurrenceMod(Family):
    id = "math2"
    domain = "mathematics-or-formal-reasoning"
    title = "Linear recurrence mod m"

    def build(self, level: int, rng: random.Random) -> Built:
        lo, hi = RANGES[level]
        nonzero = [c for c in range(-COEF_MAX, COEF_MAX + 1) if c]
        while True:
            order = rng.choice(ORDERS)
            coeffs = [rng.choice(nonzero) for _ in range(order)]
            if not any(c < 0 for c in coeffs):
                continue
            init = [rng.randint(0, 60) for _ in range(order)]
            mod = rng.randint(100_003, 999_983)
            index = rng.randint(lo, hi)
            value = nth_term(init, coeffs, index, mod)
            flipped = list(coeffs)
            neg = next(i for i, c in enumerate(flipped) if c < 0)
            flipped[neg] = -flipped[neg]
            decoys = [
                nth_term(init, coeffs, index - 1, mod),
                nth_term(init, coeffs, index + 1, mod),
                nth_term(init, coeffs, index - 2, mod),
                nth_term(init, flipped, index, mod),
            ]
            if value in decoys:
                continue
            break

        init_text = ", ".join(f"a({i})={v}" for i, v in enumerate(init))
        spec = "\n".join(
            [
                "Integer linear recurrence, reported mod M. Indexing starts at a(0).",
                init_text,
                _rule_text(coeffs),
                f"M = {mod}",
                f"N = {index}",
            ]
        )
        return Built(
            question=(
                "spec.txt gives a linear recurrence with its index N and modulus M. "
                "Return value = a(N) mod M."
            ),
            files={"spec.txt": spec + "\n"},
            fields={"value": Field("int")},
            answer={"value": value},
            decoys=[{"value": d} for d in decoys],
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        text = files["spec.txt"]
        pairs = re.findall(r"a\((\d+)\)\s*=\s*(-?\d+)", text)
        init = [int(v) for _, v in sorted(pairs, key=lambda p: int(p[0]))]
        rule = next(line for line in text.split("\n") if line.startswith("a(n)"))
        rhs = rule.split("=", 1)[1].strip()
        if not rhs.startswith("-"):
            rhs = "+" + rhs
        terms = re.findall(r"([+-])\s*(\d+)\*a\(n-(\d+)\)", rhs)
        coeffs = [0] * len(terms)
        for sign, digits, j in terms:
            coeffs[int(j) - 1] = int(sign + digits)
        mod = int(re.search(r"\bM\s*=\s*(\d+)", text).group(1))
        index = int(re.search(r"\bN\s*=\s*(\d+)", text).group(1))
        return {"value": nth_term(init, coeffs, index, mod)}


FAMILY = LinearRecurrenceMod()
