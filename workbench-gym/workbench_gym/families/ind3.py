# SPDX-License-Identifier: Apache-2.0

"""
ind3: telemetry erratum (industrial-physical-systems).

``telemetry.csv`` holds 6-hourly T3 readings and 12-hourly T2 rows, which do not
count. ``maintenance.log`` lists VOID windows for T3: a reading is voided from
the window start up to, not including, the window end. The trap: the rig log
voids readings that look valid in the telemetry. Boundary off-by-ones and the
mean of the voided readings are the decoys.
"""

import datetime
import math
import random
import re
from fractions import Fraction

from ..core.grading import Field
from .base import Built, Family

N_T3 = 40
VOIDS = {1: 1, 2: 2, 3: 3}
T0 = datetime.datetime(2026, 3, 1)
REASONS = ("probe swap", "heater fault", "logger reset", "bad zero", "cable repair")


def _stamp(index: int) -> str:
    return (T0 + datetime.timedelta(hours=6 * index)).strftime("%Y-%m-%d %H:%M")


def _fmt(x: Fraction) -> str:
    cents = math.floor(x * 100 + Fraction(1, 2))
    return f"{cents // 100}.{cents % 100:02d}"


def _is_tie(x: Fraction) -> bool:
    scaled = x * 100
    return scaled - math.floor(scaled) == Fraction(1, 2)


def _mean(tenths: list[int]) -> str:
    return _fmt(Fraction(sum(tenths), 10 * len(tenths)))


def _windows(count: int, rng: random.Random) -> list[tuple[int, int]]:
    while True:
        starts = sorted(rng.sample(range(N_T3 - 8), count))
        wins = [(s, s + rng.randint(2, 6)) for s in starts]
        if all(wins[k][1] < wins[k + 1][0] for k in range(count - 1)):
            return wins


class TelemetryErratum(Family):
    id = "ind3"
    domain = "industrial-physical-systems"
    title = "Telemetry erratum"

    def build(self, level: int, rng: random.Random) -> Built:
        count = VOIDS[level]
        for _ in range(2000):
            t3 = [rng.randrange(400, 561) for _ in range(N_T3)]
            t2 = [rng.randrange(300, 401) for _ in range(N_T3 // 2)]
            wins = _windows(count, rng)
            voided = {k for s, e in wins for k in range(s, e)}
            kept = [t3[k] for k in range(N_T3) if k not in voided]
            if len(kept) < 6:
                continue
            exact = Fraction(sum(kept), 10 * len(kept))
            if _is_tie(exact):
                continue
            answer = _fmt(exact)
            end_incl = voided | {e for _, e in wins if e < N_T3}
            start_excl = {k for s, e in wins for k in range(s + 1, e)}
            candidates = [
                _mean(t3),
                _mean([t3[k] for k in range(N_T3) if k not in end_incl]),
                _mean([t3[k] for k in range(N_T3) if k not in start_excl]),
                _mean([t3[k] for k in sorted(voided)]),
            ]
            decoys: list[str] = []
            for value in candidates:
                if value != answer and value not in decoys:
                    decoys.append(value)
            if len(decoys) < 3:
                continue
            rows = [(k, "T3", t3[k]) for k in range(N_T3)]
            rows += [(2 * j, "T2", t2[j]) for j in range(N_T3 // 2)]
            rows.sort(key=lambda r: (r[0], r[1]))
            csv_lines = ["timestamp,sensor,temp_C"]
            csv_lines += [f"{_stamp(k)},{sensor},{v // 10}.{v % 10}" for k, sensor, v in rows]
            events = []
            for (s, e), reason in zip(wins, [rng.choice(REASONS) for _ in wins]):
                events.append((s, f"VOID T3 from {_stamp(s)} to {_stamp(e)}, end excluded: {reason}"))
            note = rng.randrange(N_T3)
            events.append((note, f"NOTE {_stamp(note)} T2 zero check passed, no action"))
            events.sort()
            log_lines = ["Telemetry rig R-7 maintenance log, oldest first"]
            log_lines += [text for _, text in events]
            return Built(
                question=(
                    "Using valid readings only, what is the mean temp_C of sensor T3 over the "
                    "whole log? Give two decimal places, as text."
                ),
                files={
                    "telemetry.csv": "\n".join(csv_lines) + "\n",
                    "maintenance.log": "\n".join(log_lines) + "\n",
                },
                fields={"mean": Field("text")},
                answer={"mean": answer},
                decoys=[{"mean": value} for value in decoys],
            )
        raise AssertionError(f"ind3 level {level}: no instance found")

    def solve(self, files: dict[str, str], question: str) -> dict:
        voids = []
        for line in files["maintenance.log"].splitlines():
            match = re.match(r"VOID T3 from (.+?) to (.+?), end excluded", line)
            if match:
                voids.append((match.group(1), match.group(2)))
        kept = []
        for line in files["telemetry.csv"].strip().split("\n")[1:]:
            stamp, sensor, value = line.split(",")
            if sensor != "T3":
                continue
            if any(start <= stamp < end for start, end in voids):
                continue
            kept.append(Fraction(value))
        return {"mean": _fmt(sum(kept) / len(kept))}


FAMILY = TelemetryErratum()
