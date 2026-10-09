# SPDX-License-Identifier: Apache-2.0

import re

import pytest

from audit_trail.models import AuditTrailAction
from audit_trail.server.audit_trail_environment import (
    MAX_MATCHES,
    MAX_STEPS,
    AuditTrailEnvironment,
)
from audit_trail.tasks import TASKS, build

AUTH = re.compile(r"^(\d{2}:\d{2}:\d{2}) auth user=(\S+) src=(\S+) result=(ok|fail)$")
LEDGER = re.compile(
    r"^(\d{2}:\d{2}:\d{2}) txn=(\S+) acct=(\S+) type=(debit|credit|reversal) "
    r"amount=(\S+) ref=(\S+)$"
)
SENSOR = re.compile(r"^(\d{2}:\d{2}) station=(\S+) temp_c=(\S+)$")


def _seconds(clock: str) -> int:
    hours, minutes, *rest = (int(part) for part in clock.split(":"))
    return hours * 3600 + minutes * 60 + (rest[0] if rest else 0)


def _oracle_auth(lines: list[str], question: str) -> str:
    """Read the threshold from the question. Apply the rule to the text only."""
    threshold = re.search(r"at least (\d+) failed", question)
    assert threshold is not None
    k = int(threshold.group(1))
    fails: dict[str, int] = {}
    for line in lines:
        match = AUTH.match(line)
        assert match, line
        _, user, source, result = match.groups()
        if result == "fail":
            fails[source] = fails.get(source, 0) + 1
        elif fails.get(source, 0) >= k:
            return user
    raise AssertionError("no qualifying login")


def _oracle_ledger(lines: list[str]) -> str:
    rows = []
    for line in lines:
        match = LEDGER.match(line)
        assert match, line
        rows.append(match.groups())
    reversed_refs = {ref for _, _, _, kind, _, ref in rows if kind == "reversal"}
    answers = []
    for second_s, txn, acct, kind, amount, _ in rows:
        if kind != "debit":
            continue
        for earlier_s, earlier_txn, earlier_acct, earlier_kind, earlier_amount, _ in rows:
            gap = _seconds(second_s) - _seconds(earlier_s)
            if (
                earlier_kind == "debit"
                and earlier_acct == acct
                and earlier_amount == amount
                and 0 < gap <= 90
                and earlier_txn not in reversed_refs
            ):
                answers.append(txn)
                break
    assert len(answers) == 1, answers
    return answers[0].lower()


def _oracle_sensor(lines: list[str]) -> str:
    rows = []
    for line in lines:
        match = SENSOR.match(line)
        assert match, line
        rows.append((_seconds(match.group(1)), match.group(2), float(match.group(3))))
    rows.sort()
    candidates = []
    for station in {name for _, name, _ in rows}:
        series = [(when, temp) for when, name, temp in rows if name == station]
        onset = [i for i, (when, temp) in enumerate(series) if when >= 6 * 3600 and temp >= 30.0]
        if not onset or onset[0] + 1 >= len(series):
            continue
        first = onset[0]
        if series[first + 1][1] >= 30.0:
            candidates.append((series[first][0], station))
    assert candidates, "no qualifying station"
    return min(candidates)[1]


def _expected(task_id: str) -> str:
    built = build(task_id)
    family = TASKS[task_id].family
    if family == "auth":
        return _oracle_auth(built.lines, built.question)
    if family == "ledger":
        return _oracle_ledger(built.lines)
    return _oracle_sensor(built.lines)


@pytest.mark.parametrize("task_id", list(TASKS))
def test_answer_matches_text_oracle(task_id: str) -> None:
    assert build(task_id).answer == _expected(task_id)


@pytest.mark.parametrize("task_id", list(TASKS))
def test_logs_are_deterministic(task_id: str) -> None:
    assert build(task_id) == build(task_id)


def test_base_seeds_are_unique() -> None:
    seeds = [task.seed for task in TASKS.values()]
    assert len(seeds) == len(set(seeds))


@pytest.mark.parametrize("task_id", list(TASKS))
def test_accepted_seed_is_a_retry_of_the_base_seed(task_id: str) -> None:
    base = TASKS[task_id].seed
    accepted = build(task_id).seed
    assert accepted >= base
    assert (accepted - base) % 100 == 0


@pytest.mark.parametrize("task_id", [t for t in TASKS if t.startswith(("auth", "ledger"))])
def test_times_are_distinct(task_id: str) -> None:
    seconds = [_seconds(line[:8]) for line in build(task_id).lines]
    assert len(seconds) == len(set(seconds))


@pytest.mark.parametrize("task_id", [t for t in TASKS if t.startswith("sensor")])
def test_sensor_minutes_are_distinct(task_id: str) -> None:
    minutes = [line[:5] for line in build(task_id).lines]
    assert len(minutes) == len(set(minutes))


@pytest.mark.parametrize("task_id", list(TASKS))
def test_log_sizes_are_reasonable(task_id: str) -> None:
    lines = build(task_id).lines
    assert 10 <= len(lines) <= 100


def test_correct_answer_scores_one() -> None:
    env = AuditTrailEnvironment()
    env.reset(task_id="sensor-00")
    obs = env.step(AuditTrailAction(answer=build("sensor-00").answer.upper()))
    assert obs.done is True
    assert obs.reward == 1.0


def test_wrong_answer_scores_zero() -> None:
    env = AuditTrailEnvironment()
    env.reset(task_id="auth-00")
    obs = env.step(AuditTrailAction(answer="no-such-user"))
    assert obs.done is True
    assert obs.reward == 0.0


def test_question_is_sent_once_at_reset() -> None:
    env = AuditTrailEnvironment()
    reset_obs = env.reset(task_id="ledger-00")
    assert reset_obs.question == build("ledger-00").question
    first = env.step(AuditTrailAction(grep=""))
    assert first.question == ""
    second = env.step(AuditTrailAction(grep=""))
    assert second.question == ""


@pytest.mark.parametrize("task_id", ["auth-07", "ledger-07", "sensor-07"])
def test_grep_returns_capped_matches(task_id: str) -> None:
    env = AuditTrailEnvironment()
    env.reset(task_id=task_id)
    obs = env.step(AuditTrailAction(grep=""))
    assert obs.done is False
    assert len(obs.output.splitlines()) <= MAX_MATCHES + 1


def test_out_of_steps_scores_zero() -> None:
    env = AuditTrailEnvironment()
    env.reset(task_id="sensor-01")
    obs = None
    for _ in range(MAX_STEPS):
        obs = env.step(AuditTrailAction(grep="zzz-no-match"))
    assert obs is not None
    assert obs.done is True
    assert obs.reward == 0.0


def test_both_fields_do_not_end_episode() -> None:
    env = AuditTrailEnvironment()
    env.reset(task_id="auth-01")
    obs = env.step(AuditTrailAction(grep="auth", answer="alice"))
    assert obs.done is False
    assert obs.reward == 0.0


def test_unknown_task_is_rejected() -> None:
    env = AuditTrailEnvironment()
    with pytest.raises(ValueError):
        env.reset(task_id="nope-00")
