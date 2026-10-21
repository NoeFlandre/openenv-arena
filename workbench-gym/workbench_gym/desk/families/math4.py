# SPDX-License-Identifier: Apache-2.0

"""
math4: project critical path and float (mathematics-or-formal-reasoning).

``tasks.csv`` lists the tasks of a project with durations in whole days and their
predecessors (semicolon-separated ids). Level 2 adds a lag_days column: the days
that must pass between a predecessor's finish and the task's start. Forward pass:
earliest start = max over predecessors of (earliest finish + lag). Backward pass:
latest finish = min over successors of (latest start - lag), or the project end.
Total float = latest start - earliest start. The critical path is the chain of
zero-float tasks from start to finish; the generator keeps only projects where
that chain is unique.

Decoys: taking the minimum over predecessors, ignoring lags, and computing float
against the project end instead of the successors.
"""

import csv
import io
import json
import random
from collections.abc import Mapping

from ..spec import Check, DeskFamily, DeskTask, JsonOut, must_match
from ._common import csv_text

OUT = "output/schedule.json"


def _schedule(
    tasks: dict[str, dict],
    use_lags: bool = True,
    min_pred: bool = False,
    float_to_end: bool = False,
) -> dict:
    order = _topological(tasks)
    es: dict[str, int] = {}
    ef: dict[str, int] = {}
    for t in order:
        info = tasks[t]
        starts = [ef[p] + (info["lag"][p] if use_lags else 0) for p in info["preds"]]
        es[t] = (min(starts) if min_pred else max(starts)) if starts else 0
        ef[t] = es[t] + info["dur"]
    end = max(ef.values())
    lf: dict[str, int] = {}
    ls: dict[str, int] = {}
    for t in reversed(order):
        succs = [s for s in order if t in tasks[s]["preds"]]
        if float_to_end or not succs:
            lf[t] = end
        else:
            lf[t] = min(ls[s] - (tasks[s]["lag"][t] if use_lags else 0) for s in succs)
        ls[t] = lf[t] - tasks[t]["dur"]
    flt = {t: ls[t] - es[t] for t in order}
    critical = _unique_path(tasks, order, es, ef, end, use_lags)
    return {
        "project_duration_days": end,
        "critical_path": critical,
        "float_days": {t: flt[t] for t in sorted(order)},
    }


def _topological(tasks: dict[str, dict]) -> list[str]:
    order: list[str] = []
    done: set[str] = set()
    while len(order) < len(tasks):
        for t in sorted(tasks):
            if t not in done and all(p in done for p in tasks[t]["preds"]):
                order.append(t)
                done.add(t)
    return order


def _unique_path(tasks, order, es, ef, end, use_lags) -> list[str]:
    """The zero-float chain; empty when more than one chain is critical."""
    ways: dict[str, int] = {}
    back: dict[str, str | None] = {}
    for t in order:
        options = []
        for p in tasks[t]["preds"]:
            lag = tasks[t]["lag"][p] if use_lags else 0
            if ef[p] + lag == es[t] and ways.get(p, 0) > 0:
                options.append(p)
        if not tasks[t]["preds"] and es[t] == 0:
            ways[t] = 1
            back[t] = None
        elif options and sum(ways[p] for p in options) > 0:
            ways[t] = sum(ways[p] for p in options)
            back[t] = options[0]
        else:
            ways[t] = 0
            back[t] = None
    finals = [t for t in order if ef[t] == end and ways.get(t, 0) > 0]
    if sum(ways[t] for t in finals) != 1:
        return []
    path = [finals[0]]
    while True:
        prev = back[path[-1]]
        if prev is None:
            break
        path.append(prev)
    return list(reversed(path))


class Math4(DeskFamily):
    id = "math4"
    domain = "mathematics-or-formal-reasoning"
    title = "Project critical path and float"
    levels = (1, 2)

    def build(self, level: int, rng: random.Random) -> DeskTask:
        while True:
            task = self._try(level, rng)
            if task is not None:
                return task

    def _try(self, level: int, rng: random.Random) -> DeskTask | None:
        n = rng.randint(14, 18) if level == 1 else rng.randint(22, 28)
        ids = [f"T{i:02d}" for i in range(1, n + 1)]
        tasks: dict[str, dict] = {}
        for i, t in enumerate(ids):
            pool = ids[:i]
            k = 0 if i == 0 else rng.choice([1, 1, 2, 2, 3])
            preds = sorted(rng.sample(pool, min(k, len(pool)))) if pool else []
            lag = {
                p: (rng.randint(1, 3) if level == 2 and rng.random() < 0.3 else 0) for p in preds
            }
            tasks[t] = {"dur": rng.randint(1, 12), "preds": preds, "lag": lag}
        truth = _schedule(tasks)
        if not truth["critical_path"] or len(truth["critical_path"]) < 3:
            return None
        decoys = [_schedule(tasks, min_pred=True), _schedule(tasks, float_to_end=True)]
        if level == 2:
            decoys.append(_schedule(tasks, use_lags=False))
        if any(d == truth for d in decoys):
            return None

        rows = []
        for t in ids:
            info = tasks[t]
            pred_text = ";".join(info["preds"])
            lag_text = ";".join(str(info["lag"][p]) for p in info["preds"]) if level == 2 else None
            row = {"task_id": t, "duration_days": info["dur"], "predecessors": pred_text}
            if level == 2:
                row["lag_days"] = lag_text
            rows.append(row)
        header = ["task_id", "duration_days", "predecessors"] + (["lag_days"] if level == 2 else [])
        files = {"tasks.csv": csv_text(rows, header)}
        lag_rule = (
            " lag_days lists one lag per predecessor, in the same order as predecessors (the days "
            "that must "
            "pass after the predecessor finishes before this task may start); 0 means no lag."
            if level == 2
            else ""
        )
        instruction = (
            "Planning needs the critical path of a project before the steering meeting. "
            "{root}/tasks.csv lists "
            "every task with task_id, duration_days (whole days) and predecessors (ids separated "
            "by semicolons; "
            "empty means the task can start on day 0)." + lag_rule + "\n\n"
            "Schedule the tasks: a task starts when all its predecessors have finished (plus their "
            "lags). "
            "Earliest start (ES) and earliest finish (EF = ES + duration) come from the forward "
            "pass, counting "
            "days from 0. The project duration is the largest EF. Latest finish (LF) comes from "
            "the backward "
            "pass: a task with no successors has LF equal to the project duration; otherwise LF is "
            "the smallest "
            "over its successors of (latest start of the successor minus the lag). Latest start LS "
            "= LF minus "
            "duration. The total float of a task = LS minus ES. The critical path is the chain of "
            "tasks with "
            "float 0 from the start to the finish, in order.\n\n"
            "Output: a JSON object at {root}/output/schedule.json with the keys "
            "project_duration_days (integer), "
            "critical_path (list of task ids in order) and float_days (object mapping every task "
            "id to its total "
            "float in days). The critical path is unique in every instance. Create the output "
            "folder if needed."
        )
        return DeskTask(
            instruction=instruction,
            files=files,
            outputs=[
                JsonOut(
                    path=OUT,
                    checks={
                        "project_duration_days": Check("int"),
                        "critical_path": Check("list"),
                        "float_days": Check("map"),
                    },
                    want=truth,
                )
            ],
            oracle={OUT: json.dumps(truth)},
            decoys=[{OUT: json.dumps(d)} for d in decoys],
        )

    def solve(
        self, files: Mapping[str, str | bytes], instruction: str
    ) -> Mapping[str, str | bytes]:
        must_match(r"schedule\.json", instruction)
        raw = files["tasks.csv"]
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        tasks: dict[str, dict] = {}
        for row in csv.DictReader(io.StringIO(text)):
            preds = [p for p in row["predecessors"].split(";") if p]
            lags = row.get("lag_days")
            lag_values = [int(x) for x in lags.split(";")] if lags else [0] * len(preds)
            tasks[row["task_id"]] = {
                "dur": int(row["duration_days"]),
                "preds": preds,
                "lag": dict(zip(preds, lag_values, strict=True)),
            }
        return {OUT: json.dumps(_schedule(tasks))}


FAMILY = Math4()
