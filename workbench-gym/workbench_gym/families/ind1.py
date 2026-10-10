# SPDX-License-Identifier: Apache-2.0

"""
ind1: blackout schedule (industrial physical systems).

One line runs jobs one at a time, without pause, in due order. ``jobs.csv``
lists the jobs and ``blackouts.txt`` the power-off windows, ``rules.txt`` the
run rules. The trap: a power-off window is half-open, so a job that finishes
at the instant power goes off is complete and does not have to wait. A
solver that treats the window as closed delays that job and every job after.
The window that starts a job's end is built into every instance.
"""

import random

from ..core.grading import Field
from .base import Built, Family

JOBS = {1: 4, 2: 5, 3: 6}
QUESTION = (
    "jobs.csv lists the jobs for one line and blackouts.txt the power-off windows. Follow "
    "rules.txt. Give makespan: the minute the last job finishes."
)
RULES = (
    "\n".join(
        [
            "Shift starts at minute 0. The line runs one job at a time.",
            "Run order: earlier due first. Equal due goes to the lower job number.",
            "A job runs for its minutes without pause.",
            "Power is off for start <= minute < end, as listed in blackouts.txt.",
            "A job cannot run while power is off, so it waits until power is back.",
            "A job that finishes at the minute power goes off is complete.",
            "Makespan is the minute the last job finishes.",
        ]
    )
    + "\n"
)


def _earliest(t: int, minutes: int, windows: list[tuple[int, int]], inclusive: bool = False) -> int:
    """First start at or after t where the job clears every power-off window."""
    moved = True
    while moved:
        moved = False
        for start, end in windows:
            finish = t + minutes
            hit = t < end and (finish > start or (inclusive and finish == start))
            if hit:
                t = end
                moved = True
    return t


def _makespan(durations: list[int], windows: list[tuple[int, int]], mode: str = "correct") -> int:
    t = 0
    for minutes in durations:
        if mode == "ignore":
            t += minutes
        elif mode == "preempt":
            cur, rem = t, minutes
            while rem > 0:
                inside = [e for s, e in windows if s <= cur < e]
                if inside:
                    cur = inside[0]
                    continue
                ahead = [s for s, _ in windows if s > cur]
                run = rem if not ahead else min(rem, min(ahead) - cur)
                cur += run
                rem -= run
            t = cur
        else:
            t = _earliest(t, minutes, windows, inclusive=(mode == "inclusive")) + minutes
    return t


def _instance(n: int, rng: random.Random):
    numbers = sorted(rng.sample(range(1, 40), n))
    jobs = [{"id": i, "minutes": rng.randint(12, 75), "due": rng.randint(30, 300)} for i in numbers]
    order = sorted(jobs, key=lambda j: (j["due"], j["id"]))
    kt = rng.randrange(0, n - 3)
    kb = rng.randrange(kt + 2, n - 1)
    windows: list[tuple[int, int]] = []
    t = 0
    for k, job in enumerate(order):
        start = _earliest(t, job["minutes"], windows)
        end = start + job["minutes"]
        if k == kt:
            # Trap: power goes off at the exact minute this job finishes.
            windows.append((end, end + rng.randint(20, 60)))
        if k == kb:
            gap = rng.randint(1, order[k + 1]["minutes"] - 1)
            begin = end + gap
            windows.append((begin, begin + rng.randint(15, 45)))
        t = end
    durations = [j["minutes"] for j in order]
    if _makespan(durations, windows) != t:
        return None
    decoys: list[int] = []
    candidates = [
        _makespan(durations, windows, "inclusive"),
        sum(durations),
        _makespan(durations, windows, "preempt"),
        _makespan([j["minutes"] for j in sorted(jobs, key=lambda j: j["id"])], windows),
    ]
    for value in candidates:
        if value != t and value not in decoys:
            decoys.append(value)
    if len(decoys) < 3:
        return None
    return {"jobs": jobs, "windows": windows, "makespan": t, "decoys": decoys}


class BlackoutSchedule(Family):
    id = "ind1"
    domain = "industrial-physical-systems"
    title = "Blackout schedule"

    def build(self, level: int, rng: random.Random) -> Built:
        n = JOBS[level]
        inst = None
        for _ in range(500):
            inst = _instance(n, rng)
            if inst is not None:
                break
        if inst is None:
            raise AssertionError("no valid instance")
        jobs, windows = inst["jobs"], inst["windows"]
        files = {
            "jobs.csv": "job,minutes,due\n"
            + "".join(f"J{j['id']},{j['minutes']},{j['due']}\n" for j in jobs),
            "blackouts.txt": "# power-off windows, minutes from shift start (start end)\n"
            + "".join(f"{s} {e}\n" for s, e in windows),
            "rules.txt": RULES,
        }
        return Built(
            question=QUESTION,
            files=files,
            fields={"makespan": Field("int")},
            answer={"makespan": inst["makespan"]},
            decoys=[{"makespan": value} for value in inst["decoys"]],
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        jobs = []
        for raw in files["jobs.csv"].split("\n")[1:]:
            if not raw.strip():
                continue
            name, minutes, due = raw.split(",")
            jobs.append((int(due), int(name.strip()[1:]), int(minutes)))
        windows = []
        for raw in files["blackouts.txt"].split("\n"):
            if raw.strip() and not raw.startswith("#"):
                start, end = raw.split()
                windows.append((int(start), int(end)))
        t = 0
        for _due, _id, minutes in sorted(jobs):
            t = _earliest(t, minutes, windows) + minutes
        return {"makespan": t}


FAMILY = BlackoutSchedule()
