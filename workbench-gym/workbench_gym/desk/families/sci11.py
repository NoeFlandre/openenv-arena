# SPDX-License-Identifier: Apache-2.0

"""
sci11: Hanes-Woolf enzyme kinetics (natural-science).

``assays.csv`` holds substrate series per plate with a flag per well (OK, BUBBLE or
OUTLIER); ``blanks.csv`` holds one blank velocity per plate. The steps subtract the blank,
drop flagged wells and fit one Hanes-Woolf line over all wells: Vmax = 1 / slope and
Km = intercept / slope. Level 2 adds ``notes.md`` (a plate's substrate values are 10 times
too high) and ``blanks_rerun.csv`` (replaces one blank).

Decoys: no blank subtraction, Lineweaver-Burk, Km and Vmax swapped; from level 2 also
flagged wells kept, the erratum ignored and the stale blank used.
"""

import json
import math
import random
from collections.abc import Mapping

from ..spec import Check, DeskFamily, DeskTask, JsonOut, must_match
from ._common import read_csv

OUT = "output/kinetics.json"
CHECKS = {"Vmax": Check("num", rel=0.01), "Km": Check("num", rel=0.01)}
DIFF = 0.03  # a decoy must move Vmax or Km by more than 3% of the answer
SHARED = (
    "You are helping the enzymology group finish the kinetics section of an assay report. "
    "{root}/assays.csv has one row per well, with the columns well, plate, substrate_mM "
    "(substrate concentration in mM), velocity_uM_min (measured initial velocity in uM/min, "
    "before blank correction) and flag (OK, BUBBLE or OUTLIER). {root}/blanks.csv gives the "
    "blank velocity of each plate in uM/min, one row per plate (columns plate, "
    "blank_velocity_uM_min).\n\n"
)
FIT_1 = (
    "Fit one Hanes-Woolf line over all plates together, in this order: (1) subtract the blank "
    "of its plate from the velocity of every well; (2) drop every well whose flag is BUBBLE or "
    "OUTLIER; (3) with v the corrected velocity and S the substrate_mM value, run an "
    "ordinary least-squares line fit (numpy.polyfit with degree 1, or equivalent) of "
    "y = [S] / v against x = [S]. "
)
FIT_2 = (
    "{root}/blanks_rerun.csv has the same two columns for the plates that were read again; "
    "where it has a row for a plate, its blank replaces that plate's blank from blanks.csv. "
    "{root}/notes.md lists a correction to the substrate values.\n\n"
    "Fit one Hanes-Woolf line over all plates together, in this order: (1) apply the correction "
    "in notes.md to substrate_mM; (2) subtract the blank of its plate from the velocity of every "
    "well; (3) drop every well whose flag is BUBBLE or OUTLIER; (4) with v the corrected velocity "
    "and S the corrected substrate_mM, run an ordinary least-squares line fit (numpy.polyfit "
    "with degree 1, or equivalent) of y = [S] / v against x = [S]. "
)
END = (
    "If the fitted slope is m and the intercept is b, then Vmax = 1 / m (uM/min) and Km = b / m "
    "(mM).\n\nWrite {root}/output/kinetics.json (create the output folder if needed): a JSON "
    'object with the keys "Vmax" and "Km", each rounded to 4 decimal places, for example '
    '{"Vmax": 12.3456, "Km": 0.7890}.'
)
INSTRUCTION = {1: SHARED + FIT_1 + END, 2: SHARED + FIT_2 + END}


def _text(content: str | bytes) -> str:
    return content.decode("utf-8") if isinstance(content, bytes) else content


def _blank_csv(blanks: Mapping[str, float]) -> str:
    return "plate,blank_velocity_uM_min\n" + "".join(f"{p},{v:.3f}\n" for p, v in blanks.items())


def _notes(erratum_plate: str) -> str:
    return (
        "# Bench notes, enzyme assay run\n\n"
        f"- Erratum: on plate {erratum_plate} the substrate_mM values in assays.csv are 10 times "
        "too high (stock dilution error). Divide that plate's substrate_mM values by 10 "
        "before the fit.\n- Reader temperature was 25 C for every plate.\n"
    )


def _ols(x: list[float], y: list[float]) -> tuple[float, float]:
    """Ordinary least squares for y = m x + b: returns (m, b)."""
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    m = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / sxx
    return m, my - m * mx


def _estimate(files: Mapping[str, str | bytes], variant: str = "") -> tuple[float, float]:
    """(Vmax, Km) from the input files as the instruction describes; a decoy changes one step."""
    blanks = {r["plate"]: float(r["blank_velocity_uM_min"]) for r in read_csv(files["blanks.csv"])}
    if "blanks_rerun.csv" in files and variant != "stale":
        for r in read_csv(files["blanks_rerun.csv"]):
            blanks[r["plate"]] = float(r["blank_velocity_uM_min"])
    erratum = None
    if "notes.md" in files and variant != "noerratum":
        m = must_match(r"plate (\S+) .*?(\d+) times too high", _text(files["notes.md"]))
        erratum = (m.group(1), float(m.group(2)))
    kept = {"OK"}
    if variant == "bubble":
        kept.add("BUBBLE")
    if variant == "outlier":
        kept.add("OUTLIER")
    x, y = [], []
    for w in read_csv(files["assays.csv"]):
        if w["flag"] not in kept:
            continue
        s = float(w["substrate_mM"])
        if erratum and w["plate"] == erratum[0]:
            s /= erratum[1]
        v = float(w["velocity_uM_min"]) - (0.0 if variant == "noblank" else blanks[w["plate"]])
        x.append(1 / s if variant == "lb" else s)
        y.append(1 / v if variant == "lb" else s / v)
    m, b = _ols(x, y)
    if variant == "lb":
        return 1 / b, m / b
    return 1 / m, b / m


def _answer_json(vmax: float, km: float) -> str:
    return json.dumps({"Vmax": round(vmax, 4), "Km": round(km, 4)})


def _moved(answer: tuple[float, float], cand: tuple[float, float]) -> bool:
    """True when a candidate moves Vmax or Km by over DIFF of the answer, or is not finite."""
    pairs = zip(answer, cand, strict=True)
    return any(not math.isfinite(c) or abs(c - a) > DIFF * abs(a) for a, c in pairs)


class Sci11(DeskFamily):
    id = "sci11"
    domain = "natural-science"
    title = "Hanes-Woolf enzyme kinetics"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        trap = level == 2
        n_plates = rng.randint(4, 6) if trap else rng.randint(3, 4)
        plates = [f"P{i:02d}" for i in range(1, n_plates + 1)]
        vmax = round(rng.uniform(8, 40), 1)
        km = round(rng.uniform(0.4, 4.0), 2)
        s0 = round(rng.uniform(0.05, 0.2), 3)
        concs = [round(s0 * 2**k, 3) for k in range(rng.randint(6, 8))]
        reps = rng.randint(2, 3)
        true_blank = {p: round(rng.uniform(0.05, 0.6), 3) for p in plates}
        recs: list[dict] = [
            {"well": f"{'ABC'[r]}{k + 1}", "plate": p, "s": s, "mult": 1.0, "flag": "OK"}
            for p in plates
            for r in range(reps)
            for k, s in enumerate(concs)
        ]
        blanks, rerun, extra, erratum = dict(true_blank), {}, {}, None
        if trap:
            err_plate, rerun_plate = rng.sample(plates, 2)
            erratum = (err_plate, 10.0)
            offset = rng.choice((-1, 1)) * rng.uniform(0.12, 0.3)
            blanks[rerun_plate] = round(max(0.02, true_blank[rerun_plate] + offset), 3)
            rerun = {rerun_plate: true_blank[rerun_plate]}
            extra = {"blanks_rerun.csv": _blank_csv(rerun), "notes.md": _notes(err_plate)}
            picks = rng.sample(recs, rng.randint(2, 6))
            for rec in picks[: len(picks) // 2]:
                rec.update(flag="BUBBLE", mult=rng.uniform(0.2, 0.5))
            for rec in picks[len(picks) // 2 :]:
                rec.update(flag="OUTLIER", mult=rng.uniform(1.6, 2.2))
        lines = []
        for rec in recs:
            p = rec["plate"]
            s_file = rec["s"] * 10 if erratum and p == erratum[0] else rec["s"]
            vt = vmax * rec["s"] / (km + rec["s"])
            v = true_blank[p] + rec["mult"] * vt + rng.gauss(0, 0.03 * vt + 0.04)
            lines.append(f"{rec['well']},{p},{s_file:.3f},{v:.3f},{rec['flag']}")
        header = "well,plate,substrate_mM,velocity_uM_min,flag\n"
        files: dict[str, str | bytes] = {
            "assays.csv": header + "\n".join(lines) + "\n",
            "blanks.csv": _blank_csv(blanks),
            **extra,
        }
        variants = ["noblank", "lb"]
        if trap:
            variants += ["bubble", "outlier", "noerratum", "stale"]
        effective = {**blanks, **rerun}
        ok = [
            float(w["velocity_uM_min"]) - effective[w["plate"]]
            for w in read_csv(files["assays.csv"])
            if w["flag"] == "OK"
        ]
        try:
            vmax_hat, km_hat = _estimate(files)
            cands = [_estimate(files, v) for v in variants]
        except ZeroDivisionError:
            return None
        if vmax_hat <= 0 or km_hat <= 0 or min(ok) < 0.02:
            return None
        answer = (round(vmax_hat, 4), round(km_hat, 4))
        cands.append((km_hat, vmax_hat))  # Km and Vmax swapped
        if not all(_moved(answer, c) for c in cands):
            return None
        return DeskTask(
            instruction=INSTRUCTION[level],
            files=files,
            outputs=[JsonOut(path=OUT, checks=CHECKS, want={"Vmax": answer[0], "Km": answer[1]})],
            oracle={OUT: _answer_json(*answer)},
            decoys=[{OUT: _answer_json(*c)} for c in cands],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"kinetics\.json", instruction)
        vmax, km = _estimate(files)
        return {OUT: _answer_json(vmax, km)}


FAMILY = Sci11()
