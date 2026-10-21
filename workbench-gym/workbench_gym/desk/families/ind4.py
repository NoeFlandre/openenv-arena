# SPDX-License-Identifier: Apache-2.0

"""
ind4: merit-order dispatch of a generator fleet (industrial-physical-systems).

``generators.csv`` lists the fleet and ``demand.csv`` the hourly demand. Each hour
the cheapest available units run first until net demand is met; the clearing
price is the marginal cost of the last unit that runs. Level 2 adds ``outages.csv``
(a unit is unavailable for an hour range, inclusive) and ``wind.csv`` (wind output
is subtracted from demand, never below zero). All values are whole MW and whole
cost units, so the answer is exact.

Decoys: the cheapest unit's cost as the price, ignoring outages, ignoring wind,
and an average price over demand instead of over served energy.
"""

import csv
import io
import json
import random
from collections.abc import Mapping

from ..spec import Check, DeskFamily, DeskTask, JsonOut, must_match
from ._common import csv_text, half_up

OUT = "output/dispatch.json"


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def _dispatch(
    units: list[tuple[str, int, int]],
    demand: list[tuple[int, int]],
    outages: list[tuple[str, int, int]] | None = None,
    wind: dict[int, int] | None = None,
    first_price: bool = False,
    over_demand: bool = False,
) -> dict:
    total_cost = 0
    served_total = 0
    price_mwh = 0
    peak = 0
    unserved = 0
    for hour, mw in demand:
        net = max(0, mw - (wind or {}).get(hour, 0))
        available = sorted(
            (cost, name, cap)
            for name, cap, cost in units
            if not any(u == name and a <= hour <= b for u, a, b in (outages or []))
        )
        remaining = net
        price = 0
        for cost, _, cap in available:
            if remaining <= 0:
                break
            out = min(cap, remaining)
            total_cost += out * cost
            remaining -= out
            price = available[0][0] if first_price else cost
        served = net - remaining
        served_total += served
        price_mwh += price * served
        peak = max(peak, price)
        unserved += remaining
    base = sum(mw for _, mw in demand) if over_demand else served_total
    average = price_mwh / base if base else 0.0
    return {
        "total_cost": total_cost,
        "average_price": half_up(average, 2),
        "peak_price": peak,
        "unserved_mwh": unserved,
    }


class Ind4(DeskFamily):
    id = "ind4"
    domain = "industrial-physical-systems"
    title = "Merit-order dispatch of a generator fleet"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        costs = rng.sample(range(12, 140), 6)
        units = [(f"U{i + 1}", rng.randint(80, 320), costs[i]) for i in range(6)]
        units.append(("PEAK", rng.randint(40, 90), rng.randint(150, 220)))
        hours = 24
        demand = [
            (h, rng.randint(500, 1100) + (250 if 7 <= h <= 20 else 0)) for h in range(1, hours + 1)
        ]
        outages: list[tuple[str, int, int]] = []
        wind: dict[int, int] = {}
        if level == 2:
            for name, _, _ in rng.sample(units, 2):
                a = rng.randint(1, hours - 4)
                outages.append((name, a, a + rng.randint(2, 6)))
            wind = {h: rng.randint(0, 400) for h, _ in demand}

        truth = _dispatch(units, demand, outages or None, wind or None)
        decoys = [
            _dispatch(units, demand, outages or None, wind or None, first_price=True),
            _dispatch(units, demand, outages or None, wind or None, over_demand=True),
        ]
        if level == 2:
            decoys.append(_dispatch(units, demand, None, wind or None))
            decoys.append(_dispatch(units, demand, outages or None, None))
        if truth["unserved_mwh"] == 0 or any(d == truth for d in decoys):
            return None

        gen = csv_text(
            [{"unit": u, "capacity_mw": c, "marginal_cost_per_mwh": k} for u, c, k in units],
            ["unit", "capacity_mw", "marginal_cost_per_mwh"],
        )
        dem = csv_text([{"hour": h, "demand_mw": d} for h, d in demand], ["hour", "demand_mw"])
        files: dict[str, str | bytes] = {"generators.csv": gen, "demand.csv": dem}
        if level == 2:
            files["outages.csv"] = csv_text(
                [{"unit": u, "from_hour": a, "to_hour": b} for u, a, b in outages],
                ["unit", "from_hour", "to_hour"],
            )
            files["wind.csv"] = csv_text(
                [{"hour": h, "wind_mw": w} for h, w in wind.items()], ["hour", "wind_mw"]
            )
        extra = (
            " {root}/outages.csv lists unit outages: the unit cannot run in every hour from "
            "from_hour "
            "to to_hour, both included. {root}/wind.csv gives wind output per hour; subtract it "
            "from the "
            "demand of that hour (net demand never goes below zero)."
            if level == 2
            else ""
        )
        instruction = (
            "The control room needs the dispatch cost for the day. {root}/generators.csv lists "
            "each unit "
            "with capacity_mw and marginal_cost_per_mwh. {root}/demand.csv gives demand_mw for "
            "hours 1 to 24."
            + extra
            + "\n\nEach hour, run the cheapest available units first (merit order) until net "
            "demand "
            "is met. "
            "A unit runs at its full capacity or at what is left of the demand. The clearing price "
            "of an "
            "hour is the marginal cost of the last unit that runs; if no unit runs, the price is "
            "0. If the "
            "units cannot meet the demand, the rest is unserved.\n\n"
            "Output: a JSON object at {root}/output/dispatch.json with the keys:\n"
            "- total_cost: the sum over all hours and units of the MWh the unit produced times its "
            "marginal_cost_per_mwh (integer).\n"
            "- average_price: the clearing price weighted by the MWh served in each hour, divided "
            "by the "
            "total MWh served, rounded to 2 decimal places.\n"
            "- peak_price: the highest clearing price of any hour (integer).\n"
            "- unserved_mwh: the total MWh of demand that no unit could serve (integer).\n"
            "Create the output folder if needed."
        )
        checks = {
            "total_cost": Check("num", tol=0.5),
            "average_price": Check("num", tol=0.011),
            "peak_price": Check("num", tol=0.5),
            "unserved_mwh": Check("num", tol=0.5),
        }
        return DeskTask(
            instruction=instruction,
            files=files,
            outputs=[JsonOut(path=OUT, checks=checks, want=truth)],
            oracle={OUT: json.dumps(truth)},
            decoys=[{OUT: json.dumps(d)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"dispatch\.json", instruction)

        def text(name: str) -> str:
            raw = files[name]
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw

        units = [
            (r["unit"], int(r["capacity_mw"]), int(r["marginal_cost_per_mwh"]))
            for r in _rows(text("generators.csv"))
        ]
        demand = [(int(r["hour"]), int(r["demand_mw"])) for r in _rows(text("demand.csv"))]
        outages = None
        wind = None
        if "outages.csv" in files:
            outages = [
                (r["unit"], int(r["from_hour"]), int(r["to_hour"]))
                for r in _rows(text("outages.csv"))
            ]
        if "wind.csv" in files:
            wind = {int(r["hour"]): int(r["wind_mw"]) for r in _rows(text("wind.csv"))}
        return {OUT: json.dumps(_dispatch(units, demand, outages, wind))}


FAMILY = Ind4()
