# SPDX-License-Identifier: Apache-2.0

"""
ind5: vibration alerts from machine sensors (industrial-physical-systems).

``sensors.csv`` has one vibration reading per machine per 15 minutes, in no
particular order. ``machines.csv`` gives each machine's model and ``limits.csv``
the vibration limit of each model. An alert starts at the third consecutive
reading above its limit. Level 2 adds ``maintenance.csv`` (readings inside a
window are skipped completely) and dropouts (-1 means no reading, and breaks a
run). Readings are taken in time order per machine.

Decoys: counting maintenance readings, a dropout that does not break a run,
an alert at the second reading, and counting above-limit readings that are not
consecutive.
"""

import csv
import io
import json
import random
from collections.abc import Mapping

from ..spec import Check, DeskFamily, DeskTask, JsonOut, must_match
from ._common import csv_text

OUT = "output/vibration_alerts.json"
RUN = 3
MODELS = {"VX-200": 4.5, "VX-350": 6.0, "KR-12": 3.2}


def _alerts(
    sensors: list[dict[str, str]],
    machines: dict[str, str],
    limits: dict[str, float],
    maintenance: list[tuple[str, str, str]],
    dropout_breaks: bool = True,
    skip_maintenance: bool = True,
    run_length: int = RUN,
    consecutive: bool = True,
) -> dict:
    by_machine: dict[str, list[tuple[str, float]]] = {}
    for row in sensors:
        by_machine.setdefault(row["machine_id"], []).append(
            (row["timestamp"], float(row["vibration_mm_s"]))
        )
    first: dict[str, str] = {}
    for machine, readings in sorted(by_machine.items()):
        readings.sort()
        limit = limits[machines[machine]]
        run = 0
        for stamp, value in readings:
            if skip_maintenance and any(
                m == machine and a <= stamp <= b for m, a, b in maintenance
            ):
                continue
            if value < 0:
                if dropout_breaks and consecutive:
                    run = 0
                continue
            if value > limit:
                run += 1
                if run >= run_length and machine not in first:
                    first[machine] = stamp
            elif consecutive:
                run = 0
    alerting = set(first)
    return {
        "first_alert": {m: first[m] for m in sorted(first)},
        "machines_ok": sorted(m for m in machines if m not in alerting),
    }


class Ind5(DeskFamily):
    id = "ind5"
    domain = "industrial-physical-systems"
    title = "Vibration alerts from machine sensors"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        ids = [f"M{i:02d}" for i in range(1, 7)]
        models = {m: rng.choice(list(MODELS)) for m in ids}
        limits = dict(MODELS)
        rows: list[dict[str, str]] = []
        windows: list[tuple[str, str, str]] = []
        stamps = [
            f"2026-10-0{d}T{h:02d}:{m:02d}:00Z"
            for d in (2, 3, 4)
            for h in range(24)
            for m in (0, 15, 30, 45)
        ]
        for machine in ids:
            limit = limits[models[machine]]
            base = limit * rng.uniform(0.35, 0.6)
            if rng.random() < 0.5:
                first_block = rng.randint(30, len(stamps) - 30)
                blocks = [(first_block, first_block + rng.choice([1, 2, 3, 4, 5]))]
            else:
                # Two separate pairs: 4 readings above the limit, never three in a row.
                a = rng.randint(10, len(stamps) // 2 - 10)
                b = rng.randint(a + 4, len(stamps) - 10)
                blocks = [(a, a + 2), (b, b + 2)]
            for k, stamp in enumerate(stamps):
                value = base * rng.uniform(0.8, 1.2)
                if any(lo <= k < hi for lo, hi in blocks):
                    value = limit * rng.uniform(1.1, 1.4)
                if level == 2 and rng.random() < 0.01:
                    value = -1.0
                rows.append(
                    {"timestamp": stamp, "machine_id": machine, "vibration_mm_s": f"{value:.2f}"}
                )
        if level == 2:
            for machine in rng.sample(ids, 3):
                start = rng.randint(20, len(stamps) - 20)
                a, b = stamps[start], stamps[start + 6]
                windows.append((machine, a, b))
                limit = limits[models[machine]]
                for row in rows:
                    if row["machine_id"] == machine and a <= row["timestamp"] <= b:
                        row["vibration_mm_s"] = f"{limit * 1.8:.2f}"
        rng.shuffle(rows)
        machines = models

        truth = _alerts(rows, machines, limits, windows)
        if not truth["first_alert"] or not truth["machines_ok"]:
            return None
        decoys = [
            _alerts(rows, machines, limits, windows, run_length=2),
            _alerts(rows, machines, limits, windows, consecutive=False),
        ]
        if level == 2:
            decoys.append(_alerts(rows, machines, limits, windows, skip_maintenance=False))
            decoys.append(_alerts(rows, machines, limits, windows, dropout_breaks=False))
        if any(d == truth for d in decoys):
            return None

        files = {
            "sensors.csv": csv_text(rows, ["timestamp", "machine_id", "vibration_mm_s"]),
            "machines.csv": csv_text(
                [{"machine_id": m, "model": models[m]} for m in ids], ["machine_id", "model"]
            ),
            "limits.csv": csv_text(
                [{"model": k, "vibration_limit": v} for k, v in limits.items()],
                ["model", "vibration_limit"],
            ),
        }
        extra = ""
        if level == 2:
            files["maintenance.csv"] = csv_text(
                [{"machine_id": m, "start": a, "end": b} for m, a, b in windows],
                ["machine_id", "start", "end"],
            )
            files["notes.md"] = (
                "# Sensor notes\n"
                "- A reading of -1.00 means the sensor sent nothing at that time.\n"
                "- Sensors.csv is not sorted by time.\n"
            )
            extra = (
                " {root}/maintenance.csv lists maintenance windows (machine_id, start, end, both "
                "ends included); "
                "readings in a window are not vibration data and are skipped completely. "
                "{root}/notes.md explains "
                "the -1.00 dropout value."
            )
        instruction = (
            "Maintenance wants the first vibration alert of each machine this weekend. "
            "{root}/sensors.csv has one "
            "reading per machine every 15 minutes (timestamp in UTC, machine_id, vibration_mm_s); "
            "{root}/machines.csv "
            "gives each machine's model and {root}/limits.csv gives the vibration limit of each "
            "model." + extra + "\n\nRules, applied to each machine's readings in time order:\n"
            "1. A reading above the limit of the machine's model extends the current run; a "
            "reading at or below "
            "the limit ends it.\n"
            "2. The alert starts at the third consecutive reading above the limit: its timestamp "
            "is the alert.\n"
            "3. Each machine has at most one alert: the first one.\n\n"
            "Output: a JSON object at {root}/output/vibration_alerts.json with two keys. "
            "first_alert maps each "
            "machine_id that alerts to the timestamp of its alert. machines_ok is the sorted list "
            "of machine_ids "
            "that never alert. Create the output folder if needed."
        )
        return DeskTask(
            instruction=instruction,
            files=files,
            outputs=[
                JsonOut(
                    path=OUT,
                    checks={"first_alert": Check("map"), "machines_ok": Check("set")},
                    want=truth,
                )
            ],
            oracle={OUT: json.dumps(truth)},
            decoys=[{OUT: json.dumps(d)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"vibration_alerts\.json", instruction)

        def text(name: str) -> str:
            raw = files[name]
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw

        sensors = list(csv.DictReader(io.StringIO(text("sensors.csv"))))
        machines = {
            r["machine_id"]: r["model"] for r in csv.DictReader(io.StringIO(text("machines.csv")))
        }
        limits = {
            r["model"]: float(r["vibration_limit"])
            for r in csv.DictReader(io.StringIO(text("limits.csv")))
        }
        windows: list[tuple[str, str, str]] = []
        if "maintenance.csv" in files:
            windows = [
                (r["machine_id"], r["start"], r["end"])
                for r in csv.DictReader(io.StringIO(text("maintenance.csv")))
            ]
        return {OUT: json.dumps(_alerts(sensors, machines, limits, windows))}


FAMILY = Ind5()
