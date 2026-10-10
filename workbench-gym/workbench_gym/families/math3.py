# SPDX-License-Identifier: Apache-2.0

"""
math3: first wrong step in an algebra chain (mathematics-or-formal-reasoning).

``worksheet.txt`` is a chain of polynomial steps. Each line applies one operation
to the previous line's right side and claims the result equals the new right
side for all x. One instance in ``NO_ERROR_ONE_IN`` has no error. Otherwise the
first wrong line has one realistic slip: a sign-only error (one coefficient has
the wrong sign), a dropped term, or a wrong exponent. Later lines build on the
wrong right side, so only the first false claim is the answer.

Most correct right sides carry an inner minus sign (``x^2 - 3x + 1``), so a rule
that answers with the first right side that has a minus sign lands on a correct
line. Lines carry random three-digit labels, not positions, so the answer is a
label. Line counts start at 16, so no fixed position (first or last line) is the
answer for more than about 10% of instances. Decoys: the line position,
the neighbouring label, a later error's label, and zero.
"""

import random
import re

from ..core.grading import Field
from .base import Built, Family

LINE_COUNT = {1: 16, 2: 18, 3: 20}
START_CHOICES = (1, 2)
NO_ERROR_ONE_IN = 20
MAX_COEF = 12
# A correct step whose right side has no inner minus sign is re-rolled this often.
RE_ROLL_PLAIN = 0.9
ERRORS = ("sign", "drop", "exponent")
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


def _inner_minus(poly):
    """True when a minus sign follows the first term, as in ``x^2 - 3x + 1``."""
    return "-" in _fmt(poly)[1:]


def _random_start(rng):
    deg = rng.choice(START_CHOICES)
    poly = {d: rng.randint(-5, 5) for d in range(deg)}
    poly[deg] = rng.choice([c for c in range(-5, 6) if c])
    return _clean(poly)


def _random_op(current, rng):
    """Return (operator, factor text, result) for one correct step.

    The result is never the zero polynomial and keeps every coefficient within
    MAX_COEF. Most results have an inner minus sign.
    """
    while True:
        if max(current) < 3 and rng.random() < 0.5:
            c = rng.choice([-4, -3, -2, -1, 1, 2, 3, 4])
            factor = {1: 1, 0: c}
            op, factor_text, result = "*", _fmt(factor), _mul(current, factor)
        else:
            sign = rng.choice([1, -1])
            term = {rng.choice([0, 1, 2]): rng.randint(1, 6)}
            op = "+" if sign > 0 else "-"
            factor_text, result = _fmt(term), _add(current, term, sign)
        if not result or max(abs(c) for c in result.values()) > MAX_COEF:
            continue
        if not _inner_minus(result) and rng.random() < RE_ROLL_PLAIN:
            continue
        return op, factor_text, result


def _fits(poly):
    return bool(poly) and max(abs(c) for c in poly.values()) <= MAX_COEF


def _wrong_rhs(true_rhs, rng):
    """Return (slip kind, wrong right side) for one realistic copying slip.

    A wrong exponent may land on a degree that already has a term, so the two
    combine, as they would when a copied power is merged into like terms.
    """
    kinds = list(ERRORS)
    rng.shuffle(kinds)
    for kind in kinds:
        options = []
        for deg in sorted(true_rhs):
            if kind == "sign":
                options.append(_clean({**true_rhs, deg: -true_rhs[deg]}))
            elif kind == "drop" and len(true_rhs) > 1:
                options.append(_clean({d: c for d, c in true_rhs.items() if d != deg}))
            elif kind == "exponent":
                for new in range(4):
                    if new != deg:
                        moved = {d: c for d, c in true_rhs.items() if d != deg}
                        moved[new] = moved.get(new, 0) + true_rhs[deg]
                        options.append(_clean(moved))
        options = [poly for poly in options if _fits(poly)]
        if options:
            return kind, rng.choice(options)
    raise AssertionError("no slip available for this right side")


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
            written = _wrong_rhs(true_rhs, rng)[1] if k in wrong else true_rhs
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
