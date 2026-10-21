# SPDX-License-Identifier: Apache-2.0

"""
sci4: Beer-Lambert calibration and sample concentrations (natural-science).

``standards.csv`` holds calibration standards, ``blanks.csv`` one blank reading
per plate and ``samples.csv`` the sample readings with their dilution factors.
Each reading has its plate's blank subtracted. A straight line (least squares,
absorbance against concentration) is fitted through the standards marked OK;
each sample's concentration is (corrected absorbance - intercept) / slope times
its dilution factor. Level 2 adds a standard marked BUBBLE (not used) and a
notes.md erratum that corrects the concentration of one standard.

Decoys: no blank subtraction, one shared blank for all plates, bubble standards
kept, the erratum ignored, and dropping the dilution factor.
"""

import csv
import io
import random
import re
from collections.abc import Mapping

from ..spec import Check, CsvOut, DeskFamily, DeskTask, must_match
from ._common import csv_text, half_up

OUT = "output/concentrations.csv"
HEADER = ["sample_id", "concentration_mg_l"]
ERRATUM = re.compile(r"^(STD-\d+): concentration is ([\d.]+) mg/L", re.M)


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def _close(answer: list[list], truth: list[list]) -> bool:
    """True when the grader would accept ``answer`` (same ids, values within its tolerance)."""
    return all(
        a[0] == t[0] and abs(float(a[1]) - float(t[1])) <= 0.011
        for a, t in zip(answer, truth, strict=True)
    )


def _fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    return slope, my - slope * mx


def _concentrations(
    standards: list[dict[str, str]],
    blanks: dict[str, float],
    samples: list[dict[str, str]],
    erratum: dict[str, float] | None = None,
    blank_mode: str = "plate",
    keep_bubbles: bool = False,
    use_dilution: bool = True,
) -> list[list]:
    shared = sum(blanks.values()) / len(blanks)

    def corrected(plate: str, absorbance: str) -> float:
        if blank_mode == "none":
            return float(absorbance)
        if blank_mode == "mean":
            return float(absorbance) - shared
        return float(absorbance) - blanks[plate]

    xs, ys = [], []
    for row in standards:
        if row["flag"] != "OK" and not keep_bubbles:
            continue
        conc = (erratum or {}).get(row["std_id"], float(row["conc_mg_l"]))
        xs.append(conc)
        ys.append(corrected(row["plate"], row["absorbance"]))
    slope, intercept = _fit(xs, ys)
    out = []
    for row in samples:
        conc = (corrected(row["plate"], row["absorbance"]) - intercept) / slope
        factor = float(row["dilution"]) if use_dilution else 1.0
        out.append([row["sample_id"], half_up(conc * factor, 2)])
    return out


class Sci4(DeskFamily):
    id = "sci4"
    domain = "natural-science"
    title = "Beer-Lambert calibration and sample concentrations"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        plates = ["P1", "P2"] if level == 1 else ["P1", "P2", "P3"]
        slope = rng.uniform(0.04, 0.12)
        intercept = rng.uniform(0.0, 0.05)
        concs = [1.0, 2.5, 5.0, 7.5, 10.0]
        blanks = {p: round(rng.uniform(0.02, 0.09), 4) for p in plates}
        standards = []
        for i, c in enumerate(concs):
            for p in plates:
                noise = rng.gauss(0, 0.002)
                reading = slope * c + intercept + blanks[p] + noise
                standards.append(
                    {
                        "std_id": f"STD-{i + 1:02d}",
                        "conc_mg_l": f"{c:.1f}",
                        "absorbance": f"{reading:.4f}",
                        "plate": p,
                        "flag": "OK",
                    }
                )
        erratum: dict[str, float] = {}
        if level == 2:
            victim = rng.choice([s for s in standards if s["conc_mg_l"] == "10.0"])
            erratum[victim["std_id"]] = round(
                float(victim["conc_mg_l"]) - rng.choice([0.5, 1.0]), 1
            )
            bubble = rng.choice([s for s in standards if s["std_id"] != victim["std_id"]])
            bubble["absorbance"] = f"{float(bubble['absorbance']) + 0.35:.4f}"
            bubble["flag"] = "BUBBLE"
        samples = []
        for i in range(rng.randint(8, 12)):
            p = rng.choice(plates)
            c = rng.uniform(0.5, 9.0)
            dil = rng.choice([1, 2, 5, 10]) if level == 2 else 1
            reading = slope * c * dil / dil + intercept + blanks[p] + rng.gauss(0, 0.002)
            samples.append(
                {
                    "sample_id": f"S-{i + 1:03d}",
                    "plate": p,
                    "absorbance": f"{reading:.4f}",
                    "dilution": str(dil),
                }
            )
        blank_rows = [{"plate": p, "absorbance": f"{blanks[p]:.4f}"} for p in plates]
        truth = _concentrations(standards, blanks, samples, erratum or None)
        decoys = [
            _concentrations(standards, blanks, samples, erratum or None, blank_mode="none"),
            _concentrations(standards, blanks, samples, erratum or None, blank_mode="mean"),
        ]
        if level == 2:
            decoys.append(
                _concentrations(standards, blanks, samples, erratum or None, use_dilution=False)
            )
            decoys.append(
                _concentrations(standards, blanks, samples, erratum or None, keep_bubbles=True)
            )
            decoys.append(_concentrations(standards, blanks, samples, None))
        if any(_close(d, truth) for d in decoys) or any(c[1] < 0 for c in truth):
            return None

        files = {
            "standards.csv": csv_text(
                standards, ["std_id", "conc_mg_l", "absorbance", "plate", "flag"]
            ),
            "blanks.csv": csv_text(blank_rows, ["plate", "absorbance"]),
            "samples.csv": csv_text(samples, ["sample_id", "plate", "absorbance", "dilution"]),
        }
        if level == 2:
            notes = "# Calibration notes\n" + "".join(
                f"{k}: concentration is {v:.1f} mg/L (the label says 10.0)\n"
                for k, v in erratum.items()
            )
            notes += "Standards flagged BUBBLE are not used.\n"
            files["notes.md"] = notes
        extra = (
            " {root}/notes.md lists corrections to the standards: where it gives a concentration, "
            "use that value. "
            "Standards whose flag is not OK are not used."
            if level == 2
            else ""
        )
        instruction = (
            "The lab needs the concentration of each sample in the day's plate run. "
            "{root}/standards.csv has the "
            "calibration standards (std_id, conc_mg_l, absorbance, plate, flag); {root}/blanks.csv "
            "has one blank "
            "absorbance per plate; {root}/samples.csv has the sample readings with their plate and "
            "dilution factor."
            + extra
            + "\n\nMethod: subtract the blank of its plate from every absorbance reading "
            "(standards and samples). "
            "Fit a straight line of corrected absorbance (y) against concentration in mg/L (x) "
            "through the "
            "standards by least squares. For each sample, concentration = (corrected absorbance - "
            "intercept) / "
            "slope, multiplied by its dilution factor.\n\n"
            "Output: a CSV at {root}/output/concentrations.csv with the exact header line "
            "sample_id,"
            "concentration_mg_l and one row per sample, in the order of samples.csv, "
            "concentrations in mg/L "
            "rounded to 2 decimal places. Create the output folder if needed."
        )
        return DeskTask(
            instruction=instruction,
            files=files,
            outputs=[
                CsvOut(
                    path=OUT,
                    header=tuple(HEADER),
                    columns=(Check("text"), Check("num", tol=0.011)),
                    rows=tuple((r[0], float(r[1])) for r in truth),
                    key=0,
                )
            ],
            oracle={OUT: csv_text(truth, HEADER)},
            decoys=[{OUT: csv_text(d, HEADER)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"concentrations\.csv", instruction)

        def text(name: str) -> str:
            raw = files[name]
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw

        standards = _rows(text("standards.csv"))
        blanks = {r["plate"]: float(r["absorbance"]) for r in _rows(text("blanks.csv"))}
        samples = _rows(text("samples.csv"))
        erratum = None
        if "notes.md" in files:
            erratum = {m.group(1): float(m.group(2)) for m in ERRATUM.finditer(text("notes.md"))}
        return {OUT: csv_text(_concentrations(standards, blanks, samples, erratum), HEADER)}


FAMILY = Sci4()
