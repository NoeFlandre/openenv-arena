# SPDX-License-Identifier: Apache-2.0

"""
ind2: tank overflow under an 80% interlock (industrial-physical-systems).

``rules.txt`` holds the capacity, starting level, drain rate and interlock rule.
``valve_steps.csv`` holds the inflow schedule: AUTO valves, or OVR (manual
override) valves. The IL80 interlock trips when the level reaches 80% of
capacity, in any step, and latches. A trip closes AUTO inflow for the rest of
the run; OVR inflow is not affected. The trap: a solver that ignores the
interlock reports an overflow the plant never reaches. ``archive/rules_rev2.txt``
is a superseded 90% rule that also closes OVR valves.
"""

import math
import random
import re
from fractions import Fraction

from ..core.grading import Field
from .base import Built, Family

STEP_COUNT = {1: 3, 2: 5, 3: 7}
TRIP = Fraction(4, 5)


def _simulate(cap, level0, drain, steps, trip=TRIP, interlock=True, close_ovr=False):
    """Exact piecewise-linear run. Returns (overflow time or None, lowest level)."""
    cap = Fraction(cap)
    drain = Fraction(drain)
    level = Fraction(level0)
    trip_level = trip * cap
    tripped = False
    low = level
    for start, end, inflow, valve in steps:
        t = Fraction(start)
        stop = Fraction(end)
        while t < stop:
            if interlock and not tripped and level >= trip_level:
                tripped = True
            if not interlock or (valve == "OVR" and not close_ovr):
                open_ = True
            else:
                open_ = not tripped
            rate = (Fraction(inflow) if open_ else Fraction(0)) - drain
            nxt, kind = stop, "end"
            if rate > 0:
                if interlock and not tripped:
                    t_trip = t + (trip_level - level) / rate
                    if t_trip < nxt:
                        nxt, kind = t_trip, "trip"
                t_full = t + (cap - level) / rate
                if t_full <= nxt:
                    return t_full, low
            level += rate * (nxt - t)
            low = min(low, level)
            t = nxt
            if kind == "trip":
                tripped = True
    return None, low


def _first_overflow(cap, level0, drain, steps, **kwargs):
    when, _ = _simulate(cap, level0, drain, steps, **kwargs)
    return -1 if when is None else math.ceil(when)


def _grab(pattern, text):
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"missing: {pattern}")
    return match.group(1)


def _draw(count, rng):
    cap = rng.randrange(60, 121) * 100
    level0 = rng.randrange(5, 31) * 100
    drain = rng.randint(2, 5)
    steps = []
    t = 0
    for k in range(count):
        last = k == count - 1
        span = rng.randrange(10, 26) * 60 if last else rng.randrange(3, 16) * 60
        inflow = rng.randint(drain + 4, 16) if last else rng.randint(0, 14)
        valve = "OVR" if last or rng.random() < 0.25 else "AUTO"
        steps.append((t, t + span, inflow, valve))
        t += span
    return cap, level0, drain, steps


class TankOverflow(Family):
    id = "ind2"
    domain = "industrial-physical-systems"
    title = "Tank overflow"

    def build(self, level: int, rng: random.Random) -> Built:
        for _ in range(5000):
            cap, level0, drain, steps = _draw(STEP_COUNT[level], rng)
            when, low = _simulate(cap, level0, drain, steps)
            if when is None or low < 0:
                continue
            want = math.ceil(when)
            naive = _first_overflow(cap, level0, drain, steps, interlock=False)
            if naive == want:
                continue
            floored = math.floor(when)
            stale = _first_overflow(cap, level0, drain, steps, trip=Fraction(9, 10), close_ovr=True)
            close_all = _first_overflow(cap, level0, drain, steps, close_ovr=True)
            decoys: list[int] = []
            for value in (naive, floored, stale, close_all, -1):
                if value != want and value not in decoys:
                    decoys.append(value)
            if len(decoys) < 3:
                continue
            rules = (
                "TANK T-204 OPERATING RULES, rev 3 (current)\n"
                f"Capacity: {cap} L (100 %).\n"
                f"Level at t=0: {level0} L.\n"
                f"Drain pump P-2 runs the whole run: {drain} L/s out.\n"
                "Inflow valves: AUTO follow valve_steps.csv. OVR = manual override.\n"
                f"IL80 interlock trips when the level reaches {int(TRIP * 100)}% of capacity, "
                "in any step, and latches.\n"
                "A trip closes all AUTO inflow for the rest of the run. OVR valves stay as commanded.\n"
                "Overflow: first moment the level reaches capacity while inflow is open.\n"
                "Report the overflow time in whole seconds, rounded up; -1 if there is none.\n"
            )
            csv_lines = ["step,from_s,to_s,inflow_lps,valve"]
            csv_lines += [f"{k},{a},{b},{q},{v}" for k, (a, b, q, v) in enumerate(steps, start=1)]
            csv_text = "\n".join(csv_lines) + "\n"
            stale_rules = (
                "TANK T-204 OPERATING RULES, rev 2 (superseded 2026-02-11)\n"
                "IL90 interlock trips at 90% and closes all inflow valves, OVR included.\n"
            )
            if any(str(want) in text for text in (rules, csv_text, stale_rules)):
                continue
            return Built(
                question=(
                    "The tank fills through a valve schedule while a drain pump empties it. "
                    "At what second does it first overflow, or -1 if it never does?"
                ),
                files={
                    "rules.txt": rules,
                    "valve_steps.csv": csv_text,
                    "archive/rules_rev2.txt": stale_rules,
                },
                fields={"overflow_s": Field("int")},
                answer={"overflow_s": want},
                decoys=[{"overflow_s": value} for value in decoys],
            )
        raise AssertionError(f"ind2 level {level}: no instance found")

    def solve(self, files: dict[str, str], question: str) -> dict:
        rules = files["rules.txt"]
        cap = int(_grab(r"Capacity:\s*(\d+)\s*L", rules))
        level0 = int(_grab(r"Level at t=0:\s*(\d+)\s*L", rules))
        drain = int(_grab(r"Drain pump P-2 runs the whole run:\s*(\d+)\s*L/s", rules))
        trip_pct = int(_grab(r"IL80 interlock trips when the level reaches (\d+)%", rules))
        steps = []
        for row in files["valve_steps.csv"].strip().split("\n")[1:]:
            _, start, end, inflow, valve = row.split(",")
            steps.append((int(start), int(end), int(inflow), valve))
        return {"overflow_s": _first_overflow(cap, level0, drain, steps, trip=Fraction(trip_pct, 100))}


FAMILY = TankOverflow()
