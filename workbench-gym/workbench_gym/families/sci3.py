# SPDX-License-Identifier: Apache-2.0

"""
sci3: calibration slope with residual-span quarantine (natural science).

``standards.csv`` lists calibration runs in run order: concentration in ppb and
detector counts. The current SOP fits a line over all runs, quarantines each run
whose residual is more than a fraction of the residual span, then refits. The
superseded rev 2 quarantines by a fixed count threshold. A solver that skips the
quarantine, reads the superseded SOP, or reports the inverse slope gets a
different answer.
"""

import csv
import io
import random
from fractions import Fraction

from ..core.grading import Field
from .base import Built, Family, must_match

COUNTS = {1: 6, 2: 9, 3: 12}
THRESHOLDS = ("0.2", "0.25", "0.3")
CONC_POOL = list(range(0, 1001, 25))
OLD_LIMIT = 50
MAX_TRIES = 500

SOP_CURRENT = (
    "Calibration SOP, rev 3. status: current\n"
    "1. Fit counts = a + b x conc_ppb by least squares over all standards.\n"
    "2. Residual = counts - (a + b x conc_ppb) per standard, from step 1.\n"
    "3. Span = largest residual minus smallest residual.\n"
    "4. Quarantine a standard when |residual| > {thr} x span.\n"
    "5. Refit by least squares on the standards not quarantined.\n"
    "6. Report b as a reduced fraction, counts per ppb.\n"
)
SOP_OLD = (
    "Calibration SOP, rev 2. status: superseded by rev 3\n"
    "1. Fit counts = a + b x conc_ppb by least squares over all standards.\n"
    "2. Quarantine a standard when |residual| > 50 counts.\n"
    "3. Refit on the standards not quarantined. Report b.\n"
)
QUESTION = (
    "standards.csv lists calibration runs. Under the current calibration SOP, "
    "what is the refit slope in counts per ppb, as a reduced fraction p/q?"
)


def _fit(points):
    """Least squares with centred sums. Returns (intercept, slope) as Fractions."""
    n = len(points)
    mx = Fraction(sum(x for x, _ in points), n)
    my = Fraction(sum(y for _, y in points), n)
    sxx = sum((Fraction(x) - mx) ** 2 for x, _ in points)
    sxy = sum((Fraction(x) - mx) * (Fraction(y) - my) for x, y in points)
    slope = sxy / sxx
    return my - slope * mx, slope


def _slope_text(value):
    return {"slope": f"{value.numerator}/{value.denominator}"}


def _distinct(candidates, answer):
    out = []
    for cand in candidates:
        if cand != answer and cand not in out:
            out.append(cand)
    return out


class CalibrationFit(Family):
    id = "sci3"
    domain = "natural-science"
    title = "Calibration fit"

    def build(self, level: int, rng: random.Random) -> Built:
        n = COUNTS[level]
        thr_text = rng.choice(THRESHOLDS)
        thr = Fraction(thr_text)
        for _ in range(MAX_TRIES):
            concs = sorted(rng.sample(CONC_POOL, n))
            slope = rng.randint(12, 60)
            intercept = rng.randint(0, 300)
            runs = [[c, intercept + slope * c + rng.randint(-25, 25)] for c in concs]
            k = rng.randrange(1, n - 1)
            planted = concs[k]
            runs[k][1] += rng.choice((-1, 1)) * rng.randint(600, 1800)
            rng.shuffle(runs)
            pts = [(c, y) for c, y in runs]
            full_a, full_b = _fit(pts)
            res = [Fraction(y) - full_a - full_b * c for c, y in pts]
            span = max(res) - min(res)
            quarantined = [c for (c, _), r in zip(pts, res, strict=False) if abs(r) > thr * span]
            if quarantined != [planted]:
                continue
            kept = [(c, y) for c, y in pts if c != planted]
            _, kept_b = _fit(kept)
            answer = _slope_text(kept_b)

            candidates = [
                _slope_text(full_b),
                _slope_text(1 / kept_b),
                _slope_text(_fit([(y, c) for c, y in kept])[1]),
            ]
            old_kept = [(c, y) for (c, y), r in zip(pts, res, strict=False) if abs(r) <= OLD_LIMIT]
            if len(old_kept) >= 3 and len({c for c, _ in old_kept}) >= 2:
                candidates.append(_slope_text(_fit(old_kept)[1]))
            decoys = _distinct(candidates, answer)
            if len(decoys) < 3:
                continue

            lines = ["std,conc_ppb,counts"]
            lines += [f"STD-{i + 1:02d},{c},{y}" for i, (c, y) in enumerate(pts)]
            return Built(
                question=QUESTION,
                files={
                    "standards.csv": "\n".join(lines) + "\n",
                    "sop_rev3.txt": SOP_CURRENT.format(thr=thr_text),
                    "sop_rev2.txt": SOP_OLD,
                },
                fields={"slope": Field("fraction")},
                answer=answer,
                decoys=decoys,
            )
        raise RuntimeError("sci3: no valid instance found")

    def solve(self, files: dict[str, str], question: str) -> dict:
        sop = next(
            text
            for name, text in sorted(files.items())
            if name.startswith("sop") and "status: current" in text
        )
        thr = Fraction(must_match(r"\|residual\| > ([0-9.]+) x span", sop).group(1))
        runs = [
            (int(row["conc_ppb"]), int(row["counts"]))
            for row in csv.DictReader(io.StringIO(files["standards.csv"]))
        ]
        a, b = _solve_line(runs)
        res = [Fraction(y) - a - b * x for x, y in runs]
        span = max(res) - min(res)
        kept = [(x, y) for (x, y), r in zip(runs, res, strict=False) if abs(r) <= thr * span]
        _, slope = _solve_line(kept)
        return {"slope": f"{slope.numerator}/{slope.denominator}"}


def _solve_line(points):
    """Normal equations written from raw sums, a different route from the builder."""
    n = len(points)
    sx = sum(Fraction(x) for x, _ in points)
    sy = sum(Fraction(y) for _, y in points)
    sxx = sum(Fraction(x) * x for x, _ in points)
    sxy = sum(Fraction(x) * y for x, y in points)
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return (sy - slope * sx) / n, slope


FAMILY = CalibrationFit()
