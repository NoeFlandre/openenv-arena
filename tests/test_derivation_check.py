# SPDX-License-Identifier: Apache-2.0

import random
import re

import pytest

from derivation_check.models import DerivationCheckAction
from derivation_check.server.derivation_check_environment import (
    MAX_MATCHES,
    MAX_STEPS,
    DerivationCheckEnvironment,
)
from derivation_check.tasks import CAPTION_LIMIT, TASKS, _make_caption, _make_math, build

MATH = re.compile(r"^step (\d{2}): (\d+) ([+*-]) (\d+) = (\d+)$")
CAPTION = re.compile(r'^cap (\d{2}) text="(.*)"$')


def _oracle_math(lines: list[str]) -> str:
    """The first step whose shown result is not the true result of its operation."""
    for line in lines:
        match = MATH.match(line)
        assert match, line
        step, a, op, b, shown = match.groups()
        a_n, b_n, shown_n = int(a), int(b), int(shown)
        true = a_n + b_n if op == "+" else a_n - b_n if op == "-" else a_n * b_n
        if shown_n != true:
            return step
    raise AssertionError("no wrong equation")


def _oracle_caption(lines: list[str]) -> str:
    """The first caption whose text is longer than the limit. The quotes are not counted."""
    for line in lines:
        match = CAPTION.match(line)
        assert match, line
        number, text = match.groups()
        if len(text) > CAPTION_LIMIT:
            return number
    raise AssertionError("no caption over the limit")


def _expected(task_id: str) -> str:
    built = build(task_id)
    if TASKS[task_id].family == "math":
        return _oracle_math(built.lines)
    return _oracle_caption(built.lines)


@pytest.mark.parametrize("task_id", list(TASKS))
def test_answer_matches_text_oracle(task_id: str) -> None:
    assert build(task_id).answer == _expected(task_id)


@pytest.mark.parametrize("task_id", list(TASKS))
def test_logs_are_deterministic(task_id: str) -> None:
    assert build(task_id) == build(task_id)


def test_seeds_are_unique() -> None:
    seeds = [task.seed for task in TASKS.values()]
    assert len(seeds) == len(set(seeds))


@pytest.mark.parametrize("task_id", list(TASKS))
def test_log_sizes_are_reasonable(task_id: str) -> None:
    assert 10 <= len(build(task_id).lines) <= 60


def test_caption_lengths_hold_the_limit_until_the_answer() -> None:
    for task_id in [t for t in TASKS if t.startswith("caption")]:
        lengths = []
        for line in build(task_id).lines:
            match = CAPTION.match(line)
            assert match is not None, line
            lengths.append(len(match.group(2)))
        answer = int(build(task_id).answer)
        assert all(length <= CAPTION_LIMIT for length in lengths[: answer - 1])
        assert lengths[answer - 1] > CAPTION_LIMIT


def test_correct_answer_scores_one() -> None:
    env = DerivationCheckEnvironment()
    env.reset(task_id="math-00")
    obs = env.step(DerivationCheckAction(answer=build("math-00").answer))
    assert obs.done is True
    assert obs.reward == 1.0


def test_wrong_answer_scores_zero() -> None:
    env = DerivationCheckEnvironment()
    env.reset(task_id="caption-00")
    obs = env.step(DerivationCheckAction(answer="99"))
    assert obs.done is True
    assert obs.reward == 0.0


def test_question_is_sent_once_at_reset() -> None:
    env = DerivationCheckEnvironment()
    reset_obs = env.reset(task_id="caption-01")
    assert reset_obs.question == build("caption-01").question
    first = env.step(DerivationCheckAction(grep=""))
    assert first.question == ""


@pytest.mark.parametrize("task_id", ["math-07", "caption-07"])
def test_grep_returns_capped_matches(task_id: str) -> None:
    env = DerivationCheckEnvironment()
    env.reset(task_id=task_id)
    obs = env.step(DerivationCheckAction(grep=""))
    assert obs.done is False
    assert len(obs.output.splitlines()) <= MAX_MATCHES + 1


def test_grep_empty_returns_first_ten_lines() -> None:
    env = DerivationCheckEnvironment()
    env.reset(task_id="math-03")
    obs = env.step(DerivationCheckAction(grep=""))
    assert obs.output.splitlines()[:MAX_MATCHES] == build("math-03").lines[:MAX_MATCHES]


def test_out_of_steps_scores_zero() -> None:
    env = DerivationCheckEnvironment()
    env.reset(task_id="math-01")
    obs = None
    for _ in range(MAX_STEPS):
        obs = env.step(DerivationCheckAction(grep="zzz-no-match"))
    assert obs is not None
    assert obs.done is True
    assert obs.reward == 0.0


def test_both_fields_do_not_end_episode() -> None:
    env = DerivationCheckEnvironment()
    env.reset(task_id="math-02")
    obs = env.step(DerivationCheckAction(grep="step", answer="01"))
    assert obs.done is False
    assert obs.reward == 0.0


def test_unknown_task_is_rejected() -> None:
    env = DerivationCheckEnvironment()
    with pytest.raises(ValueError):
        env.reset(task_id="nope-00")


def test_schema_matches_models() -> None:
    from fastapi.testclient import TestClient

    from derivation_check.models import DerivationCheckAction, DerivationCheckObservation
    from derivation_check.server.app import app

    schema = TestClient(app).get("/schema").json()
    assert schema["action"] == DerivationCheckAction.model_json_schema()
    assert schema["observation"] == DerivationCheckObservation.model_json_schema()


@pytest.mark.parametrize(
    "form", ["{n}", "{n:02d}", "{n:02d}.", "step {n:02d}", "Step {n}", "cap {n:02d}"]
)
def test_number_spellings_score_one(form: str) -> None:
    task_id = "caption-03"
    number = int(build(task_id).answer)
    env = DerivationCheckEnvironment()
    env.reset(task_id=task_id)
    obs = env.step(DerivationCheckAction(answer=form.format(n=number)))
    assert obs.reward == 1.0, form


def test_other_numbers_score_zero() -> None:
    task_id = "caption-03"
    number = int(build(task_id).answer)
    env = DerivationCheckEnvironment()
    env.reset(task_id=task_id)
    obs = env.step(DerivationCheckAction(answer=f"step {number + 1:02d}"))
    assert obs.reward == 0.0


@pytest.mark.parametrize("seed", range(300))
def test_generated_math_lines_are_valid(seed: int) -> None:
    built = _make_math(seed % 8, random.Random(seed))
    for line in built.lines:
        match = MATH.match(line)
        assert match is not None, line
        assert int(match.group(5)) >= 0, line
    assert _oracle_math(built.lines) == built.answer


@pytest.mark.parametrize("seed", range(300))
def test_generated_caption_answers_match_oracle(seed: int) -> None:
    built = _make_caption(seed % 8, random.Random(seed))
    assert _oracle_caption(built.lines) == built.answer
