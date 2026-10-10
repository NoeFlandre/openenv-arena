# SPDX-License-Identifier: Apache-2.0

"""
sci1: dilution erratum (natural-science).

``protocol.txt`` gives a two-step serial dilution: stock into a step 1 mix, then
step 1 mix into tube F. ``notebook.txt`` holds ADDENDUM entries, each revising
one quantity. The latest addendum for a quantity governs. The trap: the protocol
values are stale, and an earlier addendum can be superseded by a later one.
"""

import random
import re
from fractions import Fraction

from ..core.grading import Field
from .base import Built, Family

ADDENDA = {1: 1, 2: 2, 3: 3}
KEYS = ("stock", "a1", "v1", "a2", "v2")
CHOICES = {
    "stock": [5.0, 8.0, 10.0, 12.5, 16.0, 20.0, 25.0, 40.0, 50.0, 80.0],
    "a1": [10, 20, 25, 40, 50, 80, 100, 120, 150, 200, 250],
    "v1": [500, 1000, 1500, 2000, 2500, 5000],
    "a2": [20, 25, 40, 50, 75, 100, 150, 200, 250, 300],
    "v2": [500, 1000, 1500, 2000, 2500, 5000],
}
TEXT = {
    "stock": "stock re-titrated, now {:.1f} mM.",
    "a1": "step 1 aliquot is {} uL.",
    "v1": "step 1 final volume is {} uL.",
    "a2": "step 2 aliquot is {} uL.",
    "v2": "step 2 final volume is {} uL.",
}
PATTERNS = {
    "stock": r"stock re-titrated, now ([\d.]+) mM",
    "a1": r"step 1 aliquot is ([\d.]+) uL",
    "v1": r"step 1 final volume is ([\d.]+) uL",
    "a2": r"step 2 aliquot is ([\d.]+) uL",
    "v2": r"step 2 final volume is ([\d.]+) uL",
}


def _far(new, old) -> bool:
    return max(new / old, old / new) >= 1.25


def _dilution(state) -> Fraction:
    return (
        Fraction(state["stock"])
        * Fraction(state["a1"], state["v1"])
        * Fraction(state["a2"], state["v2"])
    )


def _apart(value: Fraction, other: Fraction) -> bool:
    return abs(value - other) > Fraction(2, 100) * abs(other)


def _pair(pattern: str, text: str) -> tuple[Fraction, Fraction]:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"missing: {pattern}")
    return Fraction(match.group(1)), Fraction(match.group(2))


class DilutionErratum(Family):
    id = "sci1"
    domain = "natural-science"
    title = "Dilution erratum"

    def build(self, level: int, rng: random.Random) -> Built:
        count = ADDENDA[level]
        for _ in range(3000):
            proto = {key: rng.choice(CHOICES[key]) for key in KEYS}
            cur = dict(proto)
            states = [dict(proto)]
            notes = []
            for j in range(count):
                key = rng.choice(KEYS)
                options = [v for v in CHOICES[key] if _far(v, cur[key])]
                cur[key] = rng.choice(options)
                states.append(dict(cur))
                notes.append((key, cur[key], f"2026-04-{3 + 3 * j:02d}"))
            want = _dilution(cur)
            candidates = [
                _dilution(proto),
                _dilution(states[-2]),
                Fraction(cur["stock"]) * Fraction(cur["a1"]) / Fraction(cur["v1"]),
                Fraction(cur["stock"]) * Fraction(cur["a2"]) / Fraction(cur["v2"]),
            ]
            decoys: list[Fraction] = []
            for value in candidates:
                if _apart(value, want) and all(_apart(value, d) for d in decoys):
                    decoys.append(value)
            if len(decoys) < 3:
                continue
            protocol = (
                "SOP-12 serial dilution of compound X (protocol v2)\n"
                f"Stock: {proto['stock']:.1f} mM in DMSO.\n"
                f"Step 1: transfer {proto['a1']} uL stock into {proto['v1']} uL buffer.\n"
                f"Step 2: transfer {proto['a2']} uL of the step 1 mix "
                f"into {proto['v2']} uL buffer.\n"
                "Tube F = step 2 mix.\n"
            )
            lines = [
                "NB p.41 (Ana), 2026-04-02",
                "Dilution series made per SOP-12. Tube F made 14:10.",
            ]
            for key, value, date in notes:
                lines.append(f"ADDENDUM {date}: " + TEXT[key].format(value))
            lines.append("Read-out 2026-04-10 OK.")
            return Built(
                question=(
                    "Compound X was diluted in two steps into tube F. "
                    "What is its final concentration in tube F, in mM?"
                ),
                files={"protocol.txt": protocol, "notebook.txt": "\n".join(lines) + "\n"},
                fields={"conc_mM": Field("number", rel_tol=0.01)},
                answer={"conc_mM": float(want)},
                decoys=[{"conc_mM": float(d)} for d in decoys],
            )
        raise AssertionError(f"sci1 level {level}: no instance found")

    def solve(self, files: dict[str, str], question: str) -> dict:
        protocol = files["protocol.txt"]
        match = re.search(r"Stock:\s*([\d.]+) mM", protocol)
        if match is None:
            raise ValueError("missing stock")
        state = {"stock": Fraction(match.group(1))}
        state["a1"], state["v1"] = _pair(
            r"Step 1: transfer ([\d.]+) uL stock into ([\d.]+) uL", protocol
        )
        state["a2"], state["v2"] = _pair(
            r"Step 2: transfer ([\d.]+) uL of the step 1 mix into ([\d.]+) uL", protocol
        )
        for line in files["notebook.txt"].splitlines():
            if not line.startswith("ADDENDUM"):
                continue
            for key, pattern in PATTERNS.items():
                found = re.search(pattern, line)
                if found:
                    state[key] = Fraction(found.group(1))
        return {"conc_mM": float(_dilution(state))}


FAMILY = DilutionErratum()
