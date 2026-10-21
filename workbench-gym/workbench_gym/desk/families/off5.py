# SPDX-License-Identifier: Apache-2.0

"""
off5: two-week payroll from timesheets (office-white-collar).

``timesheets.csv`` has one row per employee, date, hours (quarter-hour steps)
and code: REG (worked), PTO (paid time off) or HOL (holiday work). ``employees.csv``
gives the hourly rate and whether the employee is overtime-eligible. Weeks run
Monday to Sunday. REG hours beyond 40 in a week are overtime (paid at 1.5 times
the rate for eligible employees; for others they are paid at the straight rate).
PTO is paid at the rate; HOL at twice the rate; neither counts toward the 40.
Level 2 adds a mid-period rate change in notes.md, duplicated rows and rows
outside the pay period.

Decoys: no overtime premium, holiday paid at one time, and (level 2) duplicates
and out-of-period rows counted.
"""

import csv
import datetime as dt
import io
import json
import random
import re
from collections.abc import Mapping
from fractions import Fraction

from ..spec import Check, DeskFamily, DeskTask, JsonOut, must_match
from ._common import csv_text

OUT = "output/payroll.json"
PERIOD = (dt.date(2026, 9, 28), dt.date(2026, 10, 11))
CHANGE = re.compile(r"From (\d{4}-\d{2}-\d{2}), (E\d+)'s hourly rate is ([\d.]+)")
TS_HEADER = ["employee_id", "date", "hours", "code"]
EMP_HEADER = ["employee_id", "name", "hourly_rate", "overtime_eligible"]


def _half_up(value: Fraction) -> Fraction:
    """Round a non-negative amount half up to the cent."""
    return Fraction(int(value * 100 + Fraction(1, 2)), 100)


def _payroll(
    sheets: list[dict[str, str]],
    employees: dict[str, dict],
    changes: dict[str, tuple[str, str]],
    dedupe: bool = True,
    in_period_only: bool = True,
    ot_premium: bool = True,
    hol_multiplier: Fraction = Fraction(2),
) -> dict:
    seen: set[tuple] = set()
    weeks: dict[tuple[str, dt.date], list[tuple[dt.date, int, str, str]]] = {}
    gross: dict[str, Fraction] = {e: Fraction(0) for e in employees}
    ot_hours: dict[str, Fraction] = {e: Fraction(0) for e in employees}
    for row in sheets:
        key = (row["employee_id"], row["date"], row["code"], row["hours"])
        if dedupe:
            if key in seen:
                continue
            seen.add(key)
        day = dt.date.fromisoformat(row["date"])
        if in_period_only and not (PERIOD[0] <= day <= PERIOD[1]):
            continue
        quarters = round(Fraction(row["hours"]) * 4)
        emp = row["employee_id"]
        rate = Fraction(employees[emp]["rate"])
        if emp in changes and row["date"] >= changes[emp][0]:
            rate = Fraction(changes[emp][1])
        if row["code"] == "REG":
            week_start = day - dt.timedelta(days=day.weekday())
            weeks.setdefault((emp, week_start), []).append((day, quarters, row["code"], str(rate)))
        elif row["code"] == "PTO":
            gross[emp] += Fraction(quarters, 4) * rate
        elif row["code"] == "HOL":
            gross[emp] += Fraction(quarters, 4) * rate * hol_multiplier
    for (emp, _), entries in weeks.items():
        entries.sort()
        cumulative = 0
        for _, quarters, _, rate_text in entries:
            rate = Fraction(rate_text)
            straight = min(quarters, max(0, 160 - cumulative))
            extra = quarters - straight
            cumulative += quarters
            gross[emp] += Fraction(straight, 4) * rate
            if employees[emp]["eligible"] and ot_premium:
                gross[emp] += Fraction(extra, 4) * rate * Fraction(3, 2)
                ot_hours[emp] += Fraction(extra, 4)
            else:
                gross[emp] += Fraction(extra, 4) * rate
    amounts = {e: _half_up(v) for e, v in gross.items()}
    total = sum(amounts.values(), Fraction(0))
    return {
        "gross_pay": {e: float(amounts[e]) for e in sorted(amounts)},
        "overtime_hours": {e: float(ot_hours[e]) for e in sorted(ot_hours)},
        "total": float(total),
    }


class Off5(DeskFamily):
    id = "off5"
    domain = "office-white-collar"
    title = "Two-week payroll from timesheets"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        ids = [f"E{100 + i}" for i in range(1, 6)]
        employees = {}
        for e in ids:
            employees[e] = {
                "name": rng.choice(
                    ["Ana Ruiz", "Bo Chen", "Carla Diaz", "Dev Patel", "Eli Stern", "Fumi Ota"]
                ),
                "rate": f"{rng.randint(22, 48)}.{rng.choice(['00', '25', '50'])}",
                "eligible": rng.random() < 0.7,
            }
        start = PERIOD[0]
        sheets: list[dict[str, str]] = []
        for e in ids:
            for d in range(14):
                day = start + dt.timedelta(days=d)
                if day.weekday() >= 5 and rng.random() < 0.7:
                    continue
                code = "REG"
                roll = rng.random()
                if roll < 0.08:
                    code = "PTO"
                elif roll < 0.12:
                    code = "HOL"
                hours = rng.choice(["7.5", "8", "8.25", "9", "9.5", "10", "6.75"])
                sheets.append(
                    {"employee_id": e, "date": day.isoformat(), "hours": hours, "code": code}
                )
        if not any(r["code"] == "HOL" for r in sheets):
            sheets[0]["code"] = "HOL"
        changes: dict[str, tuple[str, str]] = {}
        notes = ""
        if level == 2:
            e = ids[1]
            when = "2026-10-05"
            new_rate = f"{float(employees[e]['rate']) + rng.choice([1.5, 2.0, 3.25]):.2f}"
            changes[e] = (when, new_rate)
            notes = f"# Pay notes\n- From {when}, {e}'s hourly rate is {new_rate}\n"
            dupes = rng.sample(sheets, k=8)
            sheets.extend(dict(d) for d in dupes)
            sheets.append(
                {"employee_id": ids[2], "date": "2026-09-27", "hours": "8", "code": "REG"}
            )
            sheets.append(
                {"employee_id": ids[3], "date": "2026-10-12", "hours": "8", "code": "REG"}
            )
        rng.shuffle(sheets)
        emp_for_calc = {
            e: {"rate": v["rate"], "eligible": v["eligible"]} for e, v in employees.items()
        }
        truth = _payroll(sheets, emp_for_calc, changes)
        if not any(v > 0 for v in truth["overtime_hours"].values()):
            return None
        decoys = [
            _payroll(sheets, emp_for_calc, changes, ot_premium=False),
            _payroll(sheets, emp_for_calc, changes, hol_multiplier=Fraction(1)),
        ]
        if level == 2:
            decoys.append(_payroll(sheets, emp_for_calc, changes, dedupe=False))
            decoys.append(_payroll(sheets, emp_for_calc, changes, in_period_only=False))
            decoys.append(_payroll(sheets, emp_for_calc, {}))
        if any(d == truth for d in decoys):
            return None

        emp_rows = [
            {
                "employee_id": e,
                "name": v["name"],
                "hourly_rate": v["rate"],
                "overtime_eligible": "Y" if v["eligible"] else "N",
            }
            for e, v in employees.items()
        ]
        files = {
            "timesheets.csv": csv_text(sheets, TS_HEADER),
            "employees.csv": csv_text(emp_rows, EMP_HEADER),
        }
        if level == 2:
            files["notes.md"] = notes
        extra = (
            " {root}/notes.md has a rate change: the new rate applies to hours worked on and after "
            "its date."
            if level == 2
            else ""
        )
        instruction = (
            "Payroll closes the fortnight from 28 September to 11 October 2026. "
            "{root}/timesheets.csv has one row per "
            "employee and day (employee_id, date, hours, code) with code REG (worked hours), PTO "
            "(paid time off) or "
            "HOL (holiday hours). {root}/employees.csv gives the hourly_rate and whether the "
            "employee is "
            "overtime_eligible (Y or N)." + extra + "\n\nRules:\n"
            "1. Only rows dated 28 September to 11 October 2026 count.\n"
            "2. Weeks run Monday to Sunday. Within a week, REG hours beyond 40 are overtime: take "
            "the REG rows in "
            "date order and count hours; hours after the 40th count as overtime. PTO and HOL hours "
            "do not count "
            "toward the 40.\n"
            "3. Pay: straight REG hours are paid at the hourly rate. For overtime-eligible "
            "employees, overtime "
            "hours are paid at 1.5 times the rate; for other employees they are paid at the "
            "straight rate. PTO "
            "hours are paid at the rate. HOL hours are paid at twice the rate.\n"
            "4. An employee's gross_pay is the sum of their pay, rounded half up to the cent. "
            "Employees without "
            "rows get 0.00.\n\n"
            "Output: a JSON object at {root}/output/payroll.json with the keys gross_pay "
            "(employee_id to amount), "
            "overtime_hours (employee_id to total overtime hours in the period, 0 for non-eligible "
            "employees) and "
            "total (the sum of all gross_pay amounts). Amounts are numbers with at most 2 decimal "
            "places. Create the "
            "output folder if needed."
        )
        checks = {
            "gross_pay": Check("map", tol=0.005),
            "overtime_hours": Check("map", tol=0.005),
            "total": Check("num", tol=0.011),
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
        must_match(r"payroll\.json", instruction)

        def text(name: str) -> str:
            raw = files[name]
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw

        sheets = list(csv.DictReader(io.StringIO(text("timesheets.csv"))))
        employees = {
            r["employee_id"]: {"rate": r["hourly_rate"], "eligible": r["overtime_eligible"] == "Y"}
            for r in csv.DictReader(io.StringIO(text("employees.csv")))
        }
        changes: dict[str, tuple[str, str]] = {}
        if "notes.md" in files:
            for m in CHANGE.finditer(text("notes.md")):
                changes[m.group(2)] = (m.group(1), m.group(3))
        return {OUT: json.dumps(_payroll(sheets, employees, changes))}


FAMILY = Off5()
