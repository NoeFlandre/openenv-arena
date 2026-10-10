# SPDX-License-Identifier: Apache-2.0

"""
math3: first wrong step in an algebra chain (mathematics-or-formal-reasoning).

``worksheet.txt`` is a chain of polynomial steps. Each line applies one operation
to the previous line's right side and claims the result equals the new right
side for all x. Some instances hide a sign-only error: one coefficient of a
right side has the wrong sign, so its magnitudes look right. Lines carry random
three-digit labels, not positions, so the answer is a label. Later lines build on
the wrong right side, so only the first false claim is the answer. Decoys: the
line position, the neighbouring label, a later error's label, and zero.
"""

import random
import re

from ..core.grading import Field
from .base import Built, Family

LINE_COUNT = {1: 4, 2: 6, 3: 8}
START_CHOICES = (1, 2)
NO_ERROR_ONE_IN = 20
LINE = re.compile(r"^s(\d+): \((.*?)\)([*+-])\((.*?)\) = (.*)$")


def _clean(poly):
    return {d: c for d, c in poly.items() if c != 0}


def _mul(p, q):
    out = {}
    for d1, c1 in p.items():
        for d2, c2 in q.items():
            out[d1 + d2] = out.get(d1 + d2, 0) + c1 * c2
    return _clean(out)


def _add(p, q, sign=1):
    out = dict(p)
    for d, c in q.items():
        out[d] = out.get(d, 0) + sign * c
    return _clean(out)


def _fmt(poly):
    terms = []
    for d in sorted(poly, reverse=True):
        c = poly[d]
        mag = abs(c)
        if d == 0:
            core = str(mag)
        else:
            core = ("" if mag == 1 else str(mag)) + "x" + (f"^{d}" if d > 1 else "")
        if not terms:
            sign = "-" if c < 0 else ""
        else:
            sign = " - " if c < 0 else " + "
        terms.append(sign + core)
    return "".join(terms)


def _parse(text):
    body = text.replace(" ", "")
    if body[:1] not in ("+", "-"):
        body = "+" + body
    out = {}
    for sign, term in re.findall(r"([+-])([^+-]+)", body):
        m = re.fullmatch(r"(\d*)(x?)(?:\^(\d+))?", term)
        if not m:
            raise ValueError(f"cannot parse term {term!r}")
        digits, x, power = m.groups()
        if x:
            deg = int(power) if power else 1
            coef = int(digits) if digits else 1
        else:
            deg = 0
            coef = int(digits)
        out[deg] = out.get(deg, 0) + (-coef if sign == "-" else coef)
    return _clean(out)


def _random_start(rng):
    deg = rng.choice(START_CHOICES)
    poly = {d: rng.randint(-5, 5) for d in range(deg)}
    poly[deg] = rng.choice([c for c in range(-5, 6) if c])
    return _clean(poly)


def _random_op(current, rng):
    """Return (operator, factor text, result). The result is never the zero polynomial."""
    while True:
        if max(current) < 3 and rng.random() < 0.5:
            c = rng.choice([-4, -3, -2, -1, 1, 2, 3, 4])
            factor = {1: 1, 0: c}
            result = _mul(current, factor)
            if result:
                return "*", _fmt(factor), result
            continue
        sign = rng.choice([1, -1])
        term = {rng.choice([0, 1, 2]): rng.randint(1, 6)}
        result = _add(current, term, sign)
        if result:
            return ("+" if sign > 0 else "-"), _fmt(term), result


def _flip_sign(poly, rng):
    deg = rng.choice(sorted(poly))
    out = dict(poly)
    out[deg] = -out[deg]
    return out


class SignChainCheck(Family):
    id = "math3"
    domain = "mathematics-or-formal-reasoning"
    title = "First wrong step"

    def build(self, level: int, rng: random.Random) -> Built:
        n = LINE_COUNT[level]
        labels = rng.sample(range(100, 1000), n)
        wrong: list[int] = []
        if rng.randrange(NO_ERROR_ONE_IN) != 0:
            first = rng.randrange(n)
            wrong.append(first)
            if first < n - 1 and rng.random() < 0.5:
                wrong.append(rng.randrange(first + 1, n))

        current = _random_start(rng)
        rendered: list[str] = []
        for k in range(n):
            op, factor_text, true_rhs = _random_op(current, rng)
            written = _flip_sign(true_rhs, rng) if k in wrong else true_rhs
            rendered.append(f"s{labels[k]}: ({_fmt(current)}){op}({factor_text}) = {_fmt(written)}")
            current = written

        if wrong:
            first = wrong[0]
            answer = labels[first]
            neighbour = labels[first - 1] if first > 0 else labels[first + 1]
            later = labels[wrong[1]] if len(wrong) > 1 else labels[(first + 1) % n]
            decoys = [
                {"step": first + 1},
                {"step": neighbour},
                {"step": later},
                {"step": 0},
            ]
        else:
            answer = 0
            decoys = [
                {"step": labels[0]},
                {"step": labels[-1]},
                {"step": labels[n // 2]},
                {"step": 1},
            ]

        text = "# each line: LHS = RHS for all x; one operation on the previous RHS\n"
        text += "\n".join(rendered) + "\n"
        return Built(
            question=(
                "worksheet.txt is an algebra chain. Each line applies one step to the previous "
                "line's right side and claims equality for all x. Give step: the label of the "
                "first false claim, or 0 if every claim holds."
            ),
            files={"worksheet.txt": text},
            fields={"step": Field("int")},
            answer={"step": answer},
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        for line in files["worksheet.txt"].split("\n"):
            m = LINE.match(line.strip())
            if not m:
                continue
            label, left, op, factor, rhs = m.groups()
            base = _parse(left)
            arg = _parse(factor)
            if op == "*":
                lhs = _mul(base, arg)
            elif op == "+":
                lhs = _add(base, arg, 1)
            else:
                lhs = _add(base, arg, -1)
            if lhs != _parse(rhs):
                return {"step": int(label)}
        return {"step": 0}


FAMILY = SignChainCheck()
