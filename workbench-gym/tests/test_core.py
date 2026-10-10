# SPDX-License-Identifier: Apache-2.0

"""Framework tests: grading rule, file store, py sandbox and the episode protocol."""

import pytest
from workbench_gym.core.grading import Field, canon, field_ok, score_answer
from workbench_gym.core.protocol import MAX_CALLS, parse_task_id
from workbench_gym.core.sandbox import run_python
from workbench_gym.core.store import Store
from workbench_gym.families import load_families
from workbench_gym.models import WorkbenchAction
from workbench_gym.server.environment import WorkbenchEnvironment

FIELDS = {"n": Field("int"), "who": Field("text"), "ids": Field("set"), "ratio": Field("fraction")}
WANT = {"n": 3, "who": "auth", "ids": ["a", "b"], "ratio": "1/2"}


def test_reward_rule():
    assert score_answer(dict(WANT), FIELDS, WANT) == 1.0
    assert (
        score_answer({"n": 3, "who": "auth", "ids": ["b", "a"], "ratio": "2/4"}, FIELDS, WANT)
        == 1.0
    )
    assert score_answer({}, FIELDS, WANT) == 0.0
    assert score_answer(None, FIELDS, WANT) == 0.0
    assert score_answer({"n": 9, "who": "x", "ids": [], "ratio": "0"}, FIELDS, WANT) == 0.0
    partial = score_answer({"n": 3, "who": "x", "ids": [], "ratio": "0"}, FIELDS, WANT)
    assert 0.0 < partial < 0.5


def test_partial_never_reaches_a_solve():
    fields = {f"f{i}": Field("int") for i in range(20)}
    want = {f"f{i}": i for i in range(20)}
    almost = {f"f{i}": i for i in range(19)}
    assert score_answer(almost, fields, want) < 0.5


def test_answer_size_cap():
    big = {"who": "x" * 400}
    assert score_answer(big, {"who": Field("text")}, {"who": "x" * 400}) == 0.0


def test_number_tolerance_and_int_rules():
    assert field_ok(Field("number", abs_tol=0.5), 10.4, 10)
    assert not field_ok(Field("number", abs_tol=0.5), 10.6, 10)
    assert field_ok(Field("number", rel_tol=0.01), 101, 100)
    assert field_ok(Field("int"), 4.0, 4)
    assert not field_ok(Field("int"), True, 1)
    assert not field_ok(Field("int"), "4", 4)


def test_object_canonical_form():
    assert canon({"b": [2, 1], "a": 1.0}) == {"a": 1, "b": [1, 2]}


def test_store_paths_and_caps():
    store = Store({"logs/a.log": "x\n" * 50, "README.md": "hi"})
    ok, out = store.ls("")
    assert ok and "logs/" in out and "README.md" in out
    assert store.read("../etc/passwd", 0, 1)[0] is False
    assert store.read("/README.md", 0, 1)[0] is False
    ok, out = store.read("logs/a.log", 0, 999)
    assert ok and out.count("\n") <= 12 + 1 and len(out) <= 400
    ok, out = store.grep("", "x")
    assert ok and out.count("\n") <= 5
    assert store.grep("", "")[0] is False


def test_py_runs_and_is_capped():
    assert run_python(["print(2 + 3)"], {}) == "5"
    assert "CPU limit" in run_python(["while True: pass"], {})
    assert len(run_python(["print('a' * 5000)"], {})) <= 400
    assert "capped" in run_python(["x"] * 21, {})


def test_py_cannot_write_instance_files():
    out = run_python(
        ["open('data.txt','w').write('z')", "print('written')"],
        {"data.txt": "a"},
    )
    assert "written" not in out


def test_task_id_parsing():
    assert parse_task_id("sw1-L2") == ("sw1", 2)
    with pytest.raises(ValueError):
        parse_task_id("sw1-L4")
    with pytest.raises(ValueError):
        parse_task_id("../etc")


def test_episode_protocol_end_to_end():
    env = WorkbenchEnvironment(families=load_families(), allow_seed=True)
    obs = env.reset(task_id="med2-L1", seed=11)
    assert obs.done is False and obs.calls_left == MAX_CALLS
    answer = env._require_episode()["built"].answer
    obs = env.step(WorkbenchAction(tool="ls", args={}))
    assert obs.calls_left == MAX_CALLS - 1 and obs.done is False
    obs = env.step(WorkbenchAction(tool="submit", args={"answer": answer}))
    assert obs.done is True and obs.reward == 1.0
    obs = env.step(WorkbenchAction(tool="ls", args={}))
    assert obs.done is True and obs.reward == 0.0


def test_episode_ends_at_call_cap_with_zero():
    env = WorkbenchEnvironment(families=load_families(), allow_seed=True)
    env.reset(task_id="med2-L1", seed=3)
    obs = None
    for _ in range(MAX_CALLS):
        obs = env.step(WorkbenchAction(tool="ls", args={}))
    assert obs.done is True and obs.reward == 0.0


def test_finish_style_submit_scores_zero():
    env = WorkbenchEnvironment(families=load_families(), allow_seed=True)
    env.reset(task_id="med2-L3", seed=5)
    obs = env.step(WorkbenchAction(tool="submit", args={"answer": None}))
    assert obs.done is True and obs.reward == 0.0


def test_extra_action_keys_are_ignored():
    action = WorkbenchAction.model_validate({"tool": "ls", "args": {}, "finish": True})
    assert action.tool == "ls"


def test_client_seed_is_ignored_by_default():
    a = WorkbenchEnvironment(families=load_families())
    b = WorkbenchEnvironment(families=load_families())
    a.reset(task_id="med2-L2", seed=1)
    b.reset(task_id="med2-L2", seed=1)
    assert a._require_episode()["built"].files != b._require_episode()["built"].files
