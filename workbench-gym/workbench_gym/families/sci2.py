# SPDX-License-Identifier: Apache-2.0

"""
sci2: purity and yield (natural-science).

``sample.txt`` gives the weighed mass, the purity (w/w of the weighed sample)
and the molar masses. ``steps.txt`` gives each step's molar ratio (mol out per
mol in) and yield. The trap: purity applies to the weighed sample, so only the
purity share of the mass is starting material. Ignoring it overstates the
product; reading purity as the impurity share is a second wrong answer.
"""

import random
import re
from fractions import Fraction

from ..core.grading import Field
from .base import Built, Family

STEP_COUNT = {1: 2, 2: 3, 3: 4}
RATIOS = (Fraction(1), Fraction(2), Fraction(1, 2), Fraction(3, 2))


def _product(mass, purity, mw_a, mw_f, steps):
    """Grams of product F: purity-corrected moles of A, through each step, times MW(F)."""
    moles = mass * purity / mw_a
    for ratio, yld in steps:
        moles *= ratio * yld
    return moles * mw_f


def _dec(value: int, places: int) -> str:
    whole, frac = divmod(value, 10 ** places)
    return f"{whole}.{frac:0{places}d}"


def _grab(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"missing: {pattern}")
    return match.group(1)


class PurityYield(Family):
    id = "sci2"
    domain = "natural-science"
    title = "Purity and yield"

    def build(self, level: int, rng: random.Random) -> Built:
        n = STEP_COUNT[level]
        for _ in range(3000):
            mass_c = rng.randrange(50, 1201)
            purity_t = rng.randrange(850, 971)
            mw_a_c = rng.randrange(9000, 40001)
            mw_f_c = rng.randrange(9000, 60001)
            ratios = [rng.choice(RATIOS) for _ in range(n)]
            yields_t = [rng.randrange(550, 951) for _ in range(n)]
            mass = Fraction(mass_c, 100)
            purity = Fraction(purity_t, 1000)
            mw_a = Fraction(mw_a_c, 100)
            mw_f = Fraction(mw_f_c, 100)
            steps = [(r, Fraction(y, 1000)) for r, y in zip(ratios, yields_t)]
            want = _product(mass, purity, mw_a, mw_f, steps)
            candidates = [
                _product(mass, Fraction(1), mw_a, mw_f, steps),
                _product(mass, 1 - purity, mw_a, mw_f, steps),
                _product(mass, purity, mw_a, mw_f, steps[:-1] + [(ratios[-1], Fraction(1))]),
                _product(mass, purity, mw_a, mw_a, steps),
            ]
            decoys: list[Fraction] = []
            for value in candidates:
                if abs(value - want) > Fraction(2, 100) * want and all(
                    abs(value - d) > Fraction(2, 100) * d for d in decoys
                ):
                    decoys.append(value)
            if len(decoys) < 3:
                continue
            sample = (
                "Starting material A, lot 24-117 (as supplied, CoA dated 2026-01-09)\n"
                f"Weighed sample: {_dec(mass_c, 2)} g\n"
                f"Purity: {_dec(purity_t, 1)} % w/w of the weighed sample.\n"
                f"MW(A): {_dec(mw_a_c, 2)} g/mol\n"
                f"MW(F): {_dec(mw_f_c, 2)} g/mol\n"
            )
            route = [f"Route: A to F in {n} steps. Ratio = mol out per mol in."]
            for k, (ratio, y) in enumerate(zip(ratios, yields_t), start=1):
                route.append(f"Step {k}: ratio {_dec(int(ratio * 10), 1)}, yield {_dec(y, 1)} %")
            return Built(
                question="Starting from the weighed sample, how many grams of product F does the route deliver?",
                files={"sample.txt": sample, "steps.txt": "\n".join(route) + "\n"},
                fields={"grams": Field("number", rel_tol=0.01)},
                answer={"grams": float(want)},
                decoys=[{"grams": float(d)} for d in decoys],
            )
        raise AssertionError(f"sci2 level {level}: no instance found")

    def solve(self, files: dict[str, str], question: str) -> dict:
        sample = files["sample.txt"]
        mass = Fraction(_grab(r"Weighed sample:\s*([\d.]+) g", sample))
        purity = Fraction(_grab(r"Purity:\s*([\d.]+) %", sample)) / 100
        mw_a = Fraction(_grab(r"MW\(A\):\s*([\d.]+) g/mol", sample))
        mw_f = Fraction(_grab(r"MW\(F\):\s*([\d.]+) g/mol", sample))
        steps = [
            (Fraction(ratio), Fraction(y) / 100)
            for ratio, y in re.findall(r"Step \d+: ratio ([\d.]+), yield ([\d.]+) %", files["steps.txt"])
        ]
        return {"grams": float(_product(mass, purity, mw_a, mw_f, steps))}


FAMILY = PurityYield()
