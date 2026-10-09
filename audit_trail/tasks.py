# SPDX-License-Identifier: Apache-2.0

"""
Tasks for the Audit Trail environment.

Three families of logs: authentication (cybersecurity), ledger (finance) and
sensor readings (natural science). Each task builds one log from its seed. The
question states a rule, and the answer follows from that rule. The answer is
computed from the log when the task is built. No answer is stored.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass

FAMILIES = ("auth", "ledger", "sensor")
TASKS_PER_FAMILY = 8

# A generator rejects a seed when the rule does not give exactly one answer. It then tries
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
AUTH_START = 8 * 3600
AUTH_END = 10 * 3600


def _auth_fail_threshold(level: int) -> int:
    return 5 if level < 3 else 6 if level < 6 else 7


def _make_auth(level: int, rng: random.Random) -> Built:
    k = _auth_fail_threshold(level)
    attackers = 1 if level < 3 else 2 if level < 6 else 3
    near_misses = 1 + level // 2
    floods = 1 + level // 3
    legit = 2 + level // 3
    used: set[int] = set()
    events: list[tuple[int, str, str, str]] = []

    octets = rng.sample(range(1, 200), attackers + near_misses + floods + legit)
    ips = [f"10.0.{octet}.{rng.randint(100, 199)}" for octet in octets]
    attacker_ips = ips[:attackers]
    near_ips = ips[attackers : attackers + near_misses]
    flood_ips = ips[attackers + near_misses : attackers + near_misses + floods]
    legit_ips = ips[attackers + near_misses + floods :]

    def user() -> str:
        return rng.choice(AUTH_USERS)

    def when(low: int, high: int) -> int:
        return _claim(used, rng.randrange(low, high))

    for ip in attacker_ips:
        fails = sorted(when(AUTH_START, AUTH_END - 900) for _ in range(k + rng.randint(0, 1)))
        events += [(second, user(), ip, "fail") for second in fails]
        events.append((_claim(used, fails[-1] + rng.randint(1, 120)), user(), ip, "ok"))

    for ip in near_ips:
        fails = sorted(when(AUTH_START, AUTH_END - 900) for _ in range(k - 1))
        events += [(second, user(), ip, "fail") for second in fails]
        events.append((_claim(used, fails[-1] + rng.randint(1, 120)), user(), ip, "ok"))

    for ip in flood_ips:
        events += [(when(AUTH_START, AUTH_END), user(), ip, "fail") for _ in range(k + 2)]

    for ip in legit_ips:
        events += [
            (when(AUTH_START, AUTH_END), user(), ip, "fail") for _ in range(rng.randint(1, 2))
        ]
        events.append((when(AUTH_START, AUTH_END), user(), ip, "ok"))

    # Rule: an ok line counts when its source has at least k fail lines before it.
    # The answer is the user of the earliest counting ok line.
    fails_by_source: dict[str, int] = {}
    answer = ""
    for _, name, source, result in sorted(events):
        if result == "fail":
            fails_by_source[source] = fails_by_source.get(source, 0) + 1
        elif fails_by_source.get(source, 0) >= k:
            answer = name
            break
    if not answer:
        raise ValueError("no qualifying login")

    lines = [
        f"{_clock(second)} auth user={name} src={source} result={result}"
        for second, name, source, result in sorted(events)
    ]
    question = _ask(
        "Some source IPs tried to log in. Consider only successful logins (result=ok) that came "
        f"after at least {k} failed logins (result=fail) from the same source IP. Which user name "
        "is on the earliest such successful login?",
        "the user name",
    )
    return Built(lines, answer, question, 0)


# ---------------------------------------------------------------- ledger


LEDGER_START = 9 * 3600
LEDGER_END = 11 * 3600
LEDGER_WINDOW = 90


@dataclass(frozen=True)
class Txn:
    second: int
    txn: str
    acct: str
    kind: str
    amount: str
    ref: str


def _ledger_txns(level: int, rng: random.Random) -> list[Txn]:
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

    # The true duplicate: a debit repeated within the window, never reversed.
    account, value = accts[0], amount()
    first = at(LEDGER_START, LEDGER_END - 300)
    txns.append(Txn(first, txn_id(), account, "debit", value, "-"))
    txns.append(
        Txn(
            _claim(used, first + rng.randint(1, LEDGER_WINDOW)),
            txn_id(),
            account,
            "debit",
            value,
            "-",
        )
    )

    for index in range(1 + level // 3):
        other, third, fourth = accts[1 + 3 * index], accts[2 + 3 * index], accts[3 + 3 * index]

        # Same amount on another account, within the window.
        same_amount = amount()
        t1 = at(LEDGER_START, LEDGER_END - 300)
        txns.append(Txn(t1, txn_id(), other, "debit", same_amount, "-"))
        t2 = _claim(used, t1 + rng.randint(1, LEDGER_WINDOW))
        txns.append(Txn(t2, txn_id(), third, "debit", same_amount, "-"))

        # Same account and amount, but more than the window apart.
        far_amount = amount()
        t3 = at(LEDGER_START, LEDGER_END - 900)
        txns.append(Txn(t3, txn_id(), other, "debit", far_amount, "-"))
        t4 = _claim(used, t3 + rng.randint(120, 600))
        txns.append(Txn(t4, txn_id(), other, "debit", far_amount, "-"))

        # Same account and amount within the window, but the earlier debit was reversed.
        reversed_amount = amount()
        t5 = at(LEDGER_START, LEDGER_END - 900)
        reversed_id = txn_id()
        txns.append(Txn(t5, reversed_id, third, "debit", reversed_amount, "-"))
        t6 = _claim(used, t5 + rng.randint(1, LEDGER_WINDOW))
        txns.append(Txn(t6, txn_id(), third, "debit", reversed_amount, "-"))
        t7 = _claim(used, t6 + rng.randint(1, 300))
        txns.append(Txn(t7, txn_id(), third, "reversal", reversed_amount, reversed_id))

        # A credit with the same amount as an earlier debit, within the window: not a duplicate.
        credit_amount = amount()
        t8 = at(LEDGER_START, LEDGER_END - 300)
        txns.append(Txn(t8, txn_id(), fourth, "debit", credit_amount, "-"))
        t9 = _claim(used, t8 + rng.randint(1, LEDGER_WINDOW))
        txns.append(Txn(t9, txn_id(), fourth, "credit", credit_amount, "-"))

    for _ in range(20 + 4 * level):
        kind = rng.choice(["debit", "credit"])
        txns.append(
            Txn(at(LEDGER_START, LEDGER_END), txn_id(), rng.choice(accts[40:]), kind, amount(), "-")
        )

    return sorted(txns, key=lambda t: t.second)


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
    txns = _ledger_txns(level, rng)
    duplicates = _ledger_duplicates(txns)
    if len(duplicates) != 1:
        return None
    lines = [
        f"{_clock(t.second)} txn={t.txn} acct={t.acct} type={t.kind} amount={t.amount} ref={t.ref}"
        for t in txns
    ]
    question = _ask(
        "A duplicate charge is a debit that has an earlier debit with the same acct and the same "
        f"amount, from 1 to {LEDGER_WINDOW} seconds before it, where that earlier debit has no "
        "reversal line anywhere in the log whose ref is its txn id. Which txn id is the duplicate "
        "debit?",
        "the txn id",
    )
    return Built(lines, duplicates[0].txn.lower(), question, 0)


# ---------------------------------------------------------------- sensor


STATIONS = ["delta", "harbor", "lake", "mesa", "pine", "quarry", "ridge", "summit"]
SENSOR_START = 4 * 3600
SENSOR_END = 8 * 3600
HEAT_START = 6 * 3600
THRESHOLD = 300  # tenths of a degree C, so 30.0 C is exact


def _sensor_readings(level: int, rng: random.Random) -> list[tuple[int, str, int]]:
    stations = rng.sample(STATIONS, 3 if level < 3 else 5 if level < 6 else 6)
    minutes = iter(rng.sample(range((SENSOR_END - SENSOR_START) // 60), 200))
    readings: list[tuple[int, str, int]] = []
    for station in stations:
        temp = rng.randint(260, 300)
        for _ in range(rng.randint(4, 7)):
            temp = min(max(temp + rng.randint(-20, 20), 240), 330)
            readings.append((SENSOR_START + 60 * next(minutes), station, temp))
    return sorted(readings)


def _sensor_answer(readings: list[tuple[int, str, int]]) -> str | None:
    """Among stations whose first reading at or after 06:00 that is 30.0 C or more is followed by
    another reading of 30.0 C or more, the station with the earliest such first reading."""
    best: tuple[int, str] | None = None
    for station in STATIONS:
        series = [(second, temp) for second, name, temp in readings if name == station]
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
            best = (series[onset][0], station)
    return best[1] if best else None


def _make_sensor(level: int, rng: random.Random) -> Built | None:
    readings = _sensor_readings(level, rng)
    answer = _sensor_answer(readings)
    if answer is None:
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
    return Built(lines, answer, question, 0)


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
    raise ValueError(f"no unique answer for {task_id} within {MAX_ATTEMPTS} seeds")
