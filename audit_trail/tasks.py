# SPDX-License-Identifier: Apache-2.0

"""
Tasks for the Audit Trail environment.

Three families of logs: authentication (cybersecurity), ledger (finance) and
sensor readings (natural science). Each task builds one log from its seed. The
question states a rule, and the answer follows from that rule. The answer is
computed from the log when the task is built. No answer is stored.

Levels 0-2 are easy, 3-5 medium and 6-7 hard. Harder levels have longer logs,
more decoys and a larger threshold, so one grep shows less of the answer.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass

FAMILIES = ("auth", "ledger", "sensor")
TASKS_PER_FAMILY = 8

# A generator rejects a seed when its log does not meet the family's checks. It then tries
# seed + ATTEMPT_STEP, and so on up to MAX_ATTEMPTS. The accepted seed is recorded in the task.
MAX_ATTEMPTS = 50
ATTEMPT_STEP = 100

PROTOCOL = (
    'Reply {"grep": "<text>"} to search the log (up to 10 matching lines), '
    'or {"answer": "<value>"} to finish.'
)


@dataclass(frozen=True)
class Task:
    task_id: str
    family: str
    level: int
    seed: int


@dataclass(frozen=True)
class Built:
    lines: list[str]
    answer: str
    question: str
    seed: int


def _task_table() -> dict[str, Task]:
    table: dict[str, Task] = {}
    for family_index, family in enumerate(FAMILIES):
        for level in range(TASKS_PER_FAMILY):
            task_id = f"{family}-{level:02d}"
            table[task_id] = Task(task_id, family, level, 2000 + 10 * family_index + level)
    return table


TASKS = _task_table()


def _tier(level: int) -> int:
    return 0 if level < 3 else 1 if level < 6 else 2


def _clock(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _claim(used: set[int], second: int) -> int:
    """Return the first second at or after ``second`` that no other line uses."""
    while second in used:
        second += 1
    used.add(second)
    return second


def _ask(body: str, reply: str) -> str:
    return f"{body} Answer with {reply} only. {PROTOCOL}"


# ---------------------------------------------------------------- auth


AUTH_USERS = ["alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi", "ivan", "judy"]
AUTH_START = 12 * 3600
AUTH_END = 13 * 3600 - 1
AUTH_LINES = (42, 52, 62)
AUTH_NEAR_MISSES = (1, 2, 3)
AUTH_FAIL_ONLY = (1, 1, 2)
AUTH_LEGIT_SOURCES = 4


def _make_auth(level: int, rng: random.Random) -> Built | None:
    """One source has k failures and then a success. Near misses have k-1 failures, fail-only
    sources have no success, and legitimate sources have fewer than k failures in total."""
    tier = _tier(level)
    k = 5 + level // 3
    near, fail_only = AUTH_NEAR_MISSES[tier], AUTH_FAIL_ONLY[tier]
    used: set[int] = set()
    octets = rng.sample(range(1, 200), 1 + near + fail_only + AUTH_LEGIT_SOURCES)
    ips = [f"10.0.{octet}.{rng.randint(100, 199)}" for octet in octets]
    target, near_ips = ips[0], ips[1 : 1 + near]
    fail_ips = ips[1 + near : 1 + near + fail_only]
    legit_ips = ips[1 + near + fail_only :]

    events: list[tuple[int, str, str, str]] = []
    answer_user = rng.choice(AUTH_USERS)

    def when(low: int, high: int) -> int:
        return _claim(used, rng.randrange(low, high))

    def run_of_fails(source: str, count: int) -> list[int]:
        times = sorted(when(AUTH_START, AUTH_END - 900) for _ in range(count))
        events.extend((t, rng.choice(AUTH_USERS), source, "fail") for t in times)
        return times

    fails = run_of_fails(target, k)
    events.append((_claim(used, fails[-1] + rng.randint(30, 300)), answer_user, target, "ok"))

    for source in near_ips:
        fails = run_of_fails(source, k - 1)
        events.append(
            (_claim(used, fails[-1] + rng.randint(30, 300)), rng.choice(AUTH_USERS), source, "ok")
        )

    for source in fail_ips:
        run_of_fails(source, k + 3)

    for source in legit_ips:
        run_of_fails(source, rng.randint(0, min(k - 1, 2)))

    target_lines = AUTH_LINES[tier] + rng.randint(0, 4)
    while len(events) < target_lines:
        source = rng.choice(legit_ips)
        events.append((when(AUTH_START, AUTH_END), rng.choice(AUTH_USERS), source, "ok"))

    # The rule: an ok line counts when its source has at least k fail lines before it.
    qualifying: dict[str, list[tuple[int, str]]] = {}
    seen_fails: dict[str, int] = {}
    for second, name, source, result in sorted(events):
        if result == "fail":
            seen_fails[source] = seen_fails.get(source, 0) + 1
        elif seen_fails.get(source, 0) >= k:
            qualifying.setdefault(source, []).append((second, name))
    if set(qualifying) != {target}:
        return None
    answer = min(qualifying[target])[1]

    lines = [
        f"{_clock(second)} auth user={name} src={source} result={result}"
        for second, name, source, result in sorted(events)
    ]
    question = _ask(
        "Some source IPs tried to log in between 12:00 and 13:00. Consider only successful logins "
        f"(result=ok) that came after at least {k} failed logins (result=fail) from the same "
        "source IP. Which user name is on the earliest such successful login?",
        "the user name",
    )
    return Built(lines, answer, question, 0)


# ---------------------------------------------------------------- ledger


LEDGER_START = 10 * 3600
LEDGER_END = 11 * 3600 - 1
LEDGER_WINDOW = 90
LEDGER_LINES = (38, 48, 58)
LEDGER_DUPLICATES = (1, 2, 2)


@dataclass(frozen=True)
class Txn:
    second: int
    txn: str
    acct: str
    kind: str
    amount: str
    ref: str


def _ledger_duplicates(txns: list[Txn]) -> list[Txn]:
    """Each debit that has an earlier debit with the same account and amount, 1 to 90 s before,
    where that earlier debit has no reversal line whose ref is its txn id."""
    reversed_refs = {t.ref for t in txns if t.kind == "reversal"}
    debits = [t for t in txns if t.kind == "debit"]
    duplicates = []
    for later in debits:
        for earlier in debits:
            gap = later.second - earlier.second
            if (
                earlier.acct == later.acct
                and earlier.amount == later.amount
                and 1 <= gap <= LEDGER_WINDOW
                and earlier.txn not in reversed_refs
            ):
                duplicates.append(later)
                break
    return duplicates


def _make_ledger(level: int, rng: random.Random) -> Built | None:
    tier = _tier(level)
    used: set[int] = set()
    ids = iter(rng.sample(range(1000, 10000), 200))
    accts = [f"A-{n}" for n in rng.sample(range(10, 100), 60)]
    cents = iter(rng.sample(range(1000, 50000), 200))

    def amount() -> str:
        value = next(cents)
        return f"{value // 100}.{value % 100:02d}"

    def txn_id() -> str:
        return f"T{next(ids)}"

    def at(low: int, high: int) -> int:
        return _claim(used, rng.randrange(low, high))

    txns: list[Txn] = []

    # True duplicates: a debit repeated within the window, never reversed.
    for index in range(LEDGER_DUPLICATES[tier]):
        account, value = accts[index], amount()
        first = at(LEDGER_START, LEDGER_END - 900)
        txns.append(Txn(first, txn_id(), account, "debit", value, "-"))
        dup = _claim(used, first + rng.randint(1, LEDGER_WINDOW))
        txns.append(Txn(dup, txn_id(), account, "debit", value, "-"))

    decoy_base = 3 + LEDGER_DUPLICATES[tier]
    for index in range(1 + tier):
        other, third, fourth = (
            accts[decoy_base + 3 * index],
            accts[decoy_base + 1 + 3 * index],
            accts[decoy_base + 2 + 3 * index],
        )

        # Same amount on another account, within the window: not a duplicate.
        same_amount = amount()
        t1 = at(LEDGER_START, LEDGER_END - 900)
        txns.append(Txn(t1, txn_id(), other, "debit", same_amount, "-"))
        t2 = _claim(used, t1 + rng.randint(1, LEDGER_WINDOW))
        txns.append(Txn(t2, txn_id(), third, "debit", same_amount, "-"))

        # Same account and amount, but more than the window apart: not a duplicate.
        far_amount = amount()
        t3 = at(LEDGER_START, LEDGER_END - 1800)
        txns.append(Txn(t3, txn_id(), other, "debit", far_amount, "-"))
        t4 = _claim(used, t3 + rng.randint(120, 900))
        txns.append(Txn(t4, txn_id(), other, "debit", far_amount, "-"))

        # Same account and amount within the window, but the earlier debit was reversed.
        reversed_amount = amount()
        t5 = at(LEDGER_START, LEDGER_END - 1800)
        reversed_id = txn_id()
        txns.append(Txn(t5, reversed_id, third, "debit", reversed_amount, "-"))
        t6 = _claim(used, t5 + rng.randint(1, LEDGER_WINDOW))
        txns.append(Txn(t6, txn_id(), third, "debit", reversed_amount, "-"))
        t7 = _claim(used, t6 + rng.randint(1, 300))
        txns.append(Txn(t7, txn_id(), third, "reversal", reversed_amount, reversed_id))

        # A credit with the same amount as an earlier debit, within the window: not a duplicate.
        credit_amount = amount()
        t8 = at(LEDGER_START, LEDGER_END - 900)
        txns.append(Txn(t8, txn_id(), fourth, "debit", credit_amount, "-"))
        t9 = _claim(used, t8 + rng.randint(1, LEDGER_WINDOW))
        txns.append(Txn(t9, txn_id(), fourth, "credit", credit_amount, "-"))

    while len(txns) < LEDGER_LINES[tier] + rng.randint(0, 4):
        kind = rng.choice(["debit", "debit", "credit"])
        txns.append(
            Txn(at(LEDGER_START, LEDGER_END), txn_id(), rng.choice(accts[40:]), kind, amount(), "-")
        )

    duplicates = _ledger_duplicates(txns)
    if len(duplicates) != LEDGER_DUPLICATES[tier]:
        return None
    earliest = min(duplicates, key=lambda t: t.second)
    txns.sort(key=lambda t: t.second)
    lines = [
        f"{_clock(t.second)} txn={t.txn} acct={t.acct} type={t.kind} amount={t.amount} ref={t.ref}"
        for t in txns
    ]
    question = _ask(
        "A duplicate charge is a debit that has an earlier debit with the same acct and the same "
        f"amount, from 1 to {LEDGER_WINDOW} seconds before it, where that earlier debit has no "
        "reversal line anywhere in the log whose ref is its txn id. Which txn id is the earliest "
        "duplicate charge?",
        "the txn id",
    )
    return Built(lines, earliest.txn.lower(), question, 0)


# ---------------------------------------------------------------- sensor


STATIONS = ["delta", "harbor", "lake", "mesa", "pine", "quarry", "ridge", "summit"]
SENSOR_STATIONS = (3, 5, 6)
SENSOR_READINGS = (15, 11, 9)
SENSOR_LAST_MINUTE = 6 * 60 + 50  # each station ends near 06:50, after the alert
HEAT_START = 6 * 3600
THRESHOLD = 300  # tenths of a degree C, so 30.0 C is exact


def _make_sensor(level: int, rng: random.Random) -> Built | None:
    """Stations report every 10 minutes at their own offset, so no two readings share a minute.
    The answer is the station with the earliest onset (first reading from 06:00 at 30.0 C or more)
    whose next reading is also 30.0 C or more. Seeds are rejected unless the answer is hidden
    from a plain grep for hot readings."""
    tier = _tier(level)
    names = rng.sample(STATIONS, SENSOR_STATIONS[tier])
    offsets = rng.sample(range(10), len(names))
    count = SENSOR_READINGS[tier]
    first_minute = SENSOR_LAST_MINUTE - 10 * (count - 1)
    readings: list[tuple[int, str, int]] = []
    for name, offset in zip(names, offsets, strict=True):
        temp = rng.randint(270, 300)
        for index in range(count):
            temp = min(max(temp + rng.randint(-25, 25), 240), 340)
            minute = first_minute + 10 * index + offset
            readings.append((minute * 60, name, temp))
    readings.sort()

    hot = [r for r in readings if r[2] >= THRESHOLD]
    if len(hot) < 12 or sum(1 for r in hot if r[0] < HEAT_START) < 5:
        return None

    best: tuple[int, str] | None = None
    for name in names:
        series = [(second, temp) for second, station, temp in readings if station == name]
        onset = next(
            (
                i
                for i, (second, temp) in enumerate(series)
                if second >= HEAT_START and temp >= THRESHOLD
            ),
            None,
        )
        if onset is None or onset + 1 >= len(series) or series[onset + 1][1] < THRESHOLD:
            continue
        if best is None or series[onset][0] < best[0]:
            best = (series[onset][0], name)
    if best is None:
        return None
    # Six hot readings come before the answer, so it is not among the first hot readings in the log.
    if sum(1 for r in hot if r[0] < best[0]) < 6:
        return None

    lines = [
        f"{_clock(second)[:5]} station={station} temp_c={temp // 10}.{temp % 10}"
        for second, station, temp in readings
    ]
    question = _ask(
        "A heat alert started at 06:00. For each station, take its first reading at or after "
        "06:00 that is 30.0 C or more. Keep the stations whose next reading after that reading "
        "is also 30.0 C or more. Which kept station has the earliest such reading?",
        "the station name",
    )
    return Built(lines, best[1], question, 0)


# ---------------------------------------------------------------- public


_MAKERS: dict[str, Callable[[int, random.Random], Built | None]] = {
    "auth": _make_auth,
    "ledger": _make_ledger,
    "sensor": _make_sensor,
}


def build(task_id: str) -> Built:
    """Build the log, the answer, the question and the accepted seed for one task."""
    task = TASKS[task_id]
    for attempt in range(MAX_ATTEMPTS):
        seed = task.seed + ATTEMPT_STEP * attempt
        built = _MAKERS[task.family](task.level, random.Random(seed))
        if built is not None:
            return Built(built.lines, built.answer, built.question, seed)
    raise ValueError(f"no accepted log for {task_id} within {MAX_ATTEMPTS} seeds")
