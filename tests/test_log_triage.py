# SPDX-License-Identifier: Apache-2.0

import re

import pytest

from log_triage.models import LogTriageAction
from log_triage.server.log_triage_environment import (
    MAX_MATCHES,
    MAX_STEPS,
    TASKS,
    LogTriageEnvironment,
    make_log,
)

LINE = re.compile(r"^(\d{2}:\d{2}:\d{2}) (\S+)\s+(?:status=(\d+)|release=\S+ service=(\S+))")


def _expected_answer(lines: list[str]) -> str:
    """Return the service of the earliest 5xx line after 12:20:00, read from the text."""
    failures = []
    for line in lines:
        match = LINE.match(line)
        if match and match.group(3) and int(match.group(3)) >= 500 and match.group(1) > "12:20:00":
            failures.append((match.group(1), match.group(2)))
    return min(failures)[1]


@pytest.mark.parametrize("task_id", list(TASKS))
def test_answer_is_first_5xx_after_deploy(task_id: str) -> None:
    lines, answer = make_log(TASKS[task_id])
    assert answer == _expected_answer(lines)


def test_logs_are_deterministic() -> None:
    assert make_log(1000) == make_log(1000)


def test_correct_answer_scores_one() -> None:
    env = LogTriageEnvironment()
    env.reset(task_id="log-00")
    obs = env.step(LogTriageAction(answer=make_log(TASKS["log-00"])[1].upper()))
    assert obs.done is True
    assert obs.reward == 1.0


def test_wrong_answer_scores_zero() -> None:
    env = LogTriageEnvironment()
    env.reset(task_id="log-00")
    obs = env.step(LogTriageAction(answer="no-such-service"))
    assert obs.done is True
    assert obs.reward == 0.0


def test_grep_returns_capped_matches() -> None:
    env = LogTriageEnvironment()
    env.reset(task_id="log-01")
    obs = env.step(LogTriageAction(grep=""))
    assert obs.done is False
    assert len(obs.output.splitlines()) <= MAX_MATCHES + 1


def test_running_out_of_steps_ends_with_zero() -> None:
    env = LogTriageEnvironment()
    env.reset(task_id="log-02")
    obs = None
    for _ in range(MAX_STEPS):
        obs = env.step(LogTriageAction(grep="no-match-text"))
    assert obs is not None
    assert obs.done is True
    assert obs.reward == 0.0


def test_invalid_action_does_not_end_episode() -> None:
    env = LogTriageEnvironment()
    env.reset(task_id="log-03")
    obs = env.step(LogTriageAction())
    assert obs.done is False
    assert obs.reward == 0.0


def test_unknown_task_is_rejected() -> None:
    with pytest.raises(ValueError):
        LogTriageEnvironment().reset(task_id="nope")


def test_rewards_stay_in_range() -> None:
    env = LogTriageEnvironment()
    for task_id in TASKS:
        env.reset(task_id=task_id)
        obs = env.step(LogTriageAction(answer="auth"))
        assert obs.reward is not None
        assert 0.0 <= obs.reward <= 1.0
