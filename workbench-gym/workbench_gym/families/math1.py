# SPDX-License-Identifier: Apache-2.0

"""
math1: digit count (mathematics).

``blocks.txt`` lists serial blocks as zero-padded codes. ``rules.txt`` sets the
code width, the number of zero digits a serial needs, and says leading zeros
count as digits. Block B-07 holds every serial from its first to its last, both
included. The answer is how many serials in B-07 qualify.

Decoys: an exclusive last serial, an exclusive first serial, leading zeros not
counted (integer reading), and a zero-count off by one. At 9 and 12 digits brute
force does not finish, so the solver needs a digit DP.
"""

import random
import re

from ..core.grading import Field
from .base import Built, Family

WIDTH = {1: 6, 2: 9, 3: 12}
WORDS = {1: "one", 2: "two", 3: "three"}
NUMBERS = {word: n for n, word in WORDS.items()}
BLOCK = "B-07"


def _grab(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"missing: {pattern}")
    return match.group(1)


def _step(zeros: int, lead: bool, digit: int, rule: str) -> tuple[int, bool]:
    """Zero count and leading-zone flag after one more digit."""
    if rule == "padded":
        return zeros + (digit == 0), False
    if lead and digit == 0:
        return zeros, True  # a leading zero is not a digit of the integer
    if lead:
        return zeros, False
    return zeros + (digit == 0), False


def _count_le(text: str, want: int, rule: str) -> int:
    """Codes from 0 up to and including ``text`` with exactly ``want`` zeros."""
    width = len(text)
    memo: dict[tuple[int, int, bool], int] = {}

    def rest(left: int, zeros: int, lead: bool) -> int:
        if zeros > want:
            return 0
        if left == 0:
            return int(zeros == want)
        key = (left, zeros, lead)
        if key not in memo:
            memo[key] = sum(rest(left - 1, *_step(zeros, lead, d, rule)) for d in range(10))
        return memo[key]

    total = 0
    zeros, lead = 0, rule == "stripped"
    for i, ch in enumerate(text):
        digit = int(ch)
        for d in range(digit):
            total += rest(width - i - 1, *_step(zeros, lead, d, rule))
        zeros, lead = _step(zeros, lead, digit, rule)
        if zeros > want:
            return total
    return total + int(zeros == want)


def _valid(text: str, want: int, rule: str) -> int:
    zeros, lead = 0, rule == "stripped"
    for ch in text:
        zeros, lead = _step(zeros, lead, int(ch), rule)
    return int(zeros == want)


def _count(first: str, last: str, want: int, rule: str) -> int:
    """Qualifying codes in the closed range [first, last]."""
    return _count_le(last, want, rule) - _count_le(first, want, rule) + _valid(first, want, rule)


def _code(width: int, zeros_wanted: int, rng: random.Random) -> str:
    """A code with exactly ``zeros_wanted`` zeros and a nonzero leading digit."""
    zero_at = set(rng.sample(range(1, width), zeros_wanted))
    return "".join("0" if i in zero_at else str(rng.randint(1, 9)) for i in range(width))


class DigitCount(Family):
    id = "math1"
    domain = "mathematics-or-formal-reasoning"
    title = "Digit count"

    def build(self, level: int, rng: random.Random) -> Built:
        for _ in range(200):
            built = self._attempt(level, rng)
            if built is not None:
                return built
        raise AssertionError(f"math1 level {level}: no instance found")

    def _attempt(self, level: int, rng: random.Random) -> Built | None:
        width = WIDTH[level]
        want = rng.randint(1, 3)
        first_n = rng.randrange(1, 10 ** (width - 1))
        first = str(first_n).zfill(width)
        last = _code(width, want, rng)
        answer = _count(first, last, want, "padded")
        if answer <= 0 or int(last) < first_n:
            return None

        decoys: list[dict] = []
        candidates = [
            _count(first, last, want, "padded") - _valid(last, want, "padded"),
            answer - _valid(first, want, "padded"),
            _count(first, last, want, "stripped"),
            _count(first, last, want + 1, "padded"),
        ]
        for value in candidates:
            cand = {"count": value}
            if value != answer and cand not in decoys:
                decoys.append(cand)
        if len(decoys) < 3:
            return None

        others = []
        for name in ("B-06", "B-08"):
            a = str(rng.randrange(10**width)).zfill(width)
            b = str(rng.randrange(10**width)).zfill(width)
            others.append((name, min(a, b), max(a, b)))
        lines = ["Serial blocks, lot 2026-B (first and last serial)"]
        lines.append(f"{others[0][0]}: first {others[0][1]}, last {others[0][2]}")
        lines.append(f"{BLOCK}: first {first}, last {last}")
        lines.append(f"{others[1][0]}: first {others[1][1]}, last {others[1][2]}")
        digits_word = "digit" if want == 1 else "digits"
        rules = (
            "Inspection rule SR-3\n"
            f"1. Serials are {width}-digit codes, padded with leading zeros.\n"
            "2. Every digit counts, leading zeros included.\n"
            f"3. A serial qualifies when it has exactly {WORDS[want]} zero {digits_word}.\n"
            "4. A block holds every serial from its first to its last, both included.\n"
        )
        return Built(
            question=f"How many serials in block {BLOCK} qualify under rule SR-3?",
            files={"blocks.txt": "\n".join(lines) + "\n", "rules.txt": rules},
            fields={"count": Field("int")},
            answer={"count": answer},
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        rules = files["rules.txt"]
        want = NUMBERS[_grab(r"exactly (\w+) zero digits?", rules)]
        block = _grab(r"block (B-\d+)", question)
        blocks = files["blocks.txt"]
        first = _grab(rf"{block}: first (\d+), last \d+", blocks)
        last = _grab(rf"{block}: first \d+, last (\d+)", blocks)
        return {"count": _count(first, last, want, "padded")}


FAMILY = DigitCount()
