# SPDX-License-Identifier: Apache-2.0

"""Workbench Desk: tools, grading, workspace safety and the family gates."""

import json
import os

import pytest
from workbench_gym.desk.environment import MAX_CALLS, DeskEnvironment
from workbench_gym.desk.families import load_families, parse_task_id
from workbench_gym.desk.models import DeskAction
from workbench_gym.desk.spec import (
    FORMAT_CREDIT,
    Check,
    CsvOut,
    JsonOut,
    TextOut,
    grade_texts,
    value_ok,
)

from tests.desk_gates import check_family

FAMILIES = load_families()
SOME_TASK = "fin4-L1"


@pytest.fixture
def env(tmp_path):
    environment = DeskEnvironment(families=FAMILIES, allow_seed=True, work_root=str(tmp_path))
    yield environment
    environment.close()


def act(tool: str, **args) -> DeskAction:
    return DeskAction(tool=tool, args=args)


def write_outputs(env: DeskEnvironment, files: dict[str, str]) -> None:
    for path, content in files.items():
        obs = env.step(act("write", path=path, content=content))
        assert not obs.error, obs.error


@pytest.mark.parametrize("family_id", sorted(FAMILIES))
def test_family_gates(family_id):
    assert check_family(FAMILIES[family_id], seeds=25) == []


@pytest.mark.parametrize("family_id", sorted(FAMILIES))
def test_oracle_scores_one_and_decoys_less_through_the_tools(env, family_id):
    family = FAMILIES[family_id]
    for level in family.levels:
        task_id = f"{family_id}-L{level}"
        env.reset(task_id=task_id, seed=3)
        task = env._require_episode()["task"]
        write_outputs(env, task.oracle)
        obs = env.step(act("submit"))
        assert obs.done is True and obs.reward == 1.0, obs.output

        env.reset(task_id=task_id, seed=3)
        task = env._require_episode()["task"]
        write_outputs(env, task.decoys[0])
        assert env.step(act("submit")).reward < 1.0


def test_reset_text_names_the_workspace_and_tools(env):
    obs = env.reset(task_id=SOME_TASK, seed=1)
    workdir = env._require_episode()["workdir"]
    assert "{root}" not in obs.output
    assert f"{workdir}/loans.csv" in obs.output
    assert '"tool": "bash"' in obs.output and obs.calls_left == MAX_CALLS


def test_bash_runs_in_the_workspace(env):
    env.reset(task_id=SOME_TASK, seed=1)
    obs = env.step(act("bash", command="ls && echo hi > note.txt && cat note.txt"))
    assert "loans.csv" in obs.output and "hi" in obs.output and not obs.error
    obs = env.step(act("bash", command="exit 3"))
    assert "status 3" in obs.error and obs.done is False


def test_aliases_and_unknown_tools(env):
    env.reset(task_id=SOME_TASK, seed=1)
    assert "loans.csv" in env.step(act("exec", cmd="ls")).output
    obs = env.step(DeskAction(tool="write_file", args={"file_path": "a.txt", "content": "x"}))
    assert not obs.error
    obs = env.step(act("view"))
    assert "unknown tool" in obs.error and obs.done is False
    assert env.step(act("evaluate")).done is True


def test_missing_output_scores_zero_and_wrong_values_get_format_credit(env):
    env.reset(task_id=SOME_TASK, seed=1)
    assert env.step(act("submit")).reward == 0.0
    env.reset(task_id=SOME_TASK, seed=1)
    task = env._require_episode()["task"]
    want = json.loads(task.oracle["output/balances.json"])
    wrong = {"balances": {k: v + 100 for k, v in want["balances"].items()}, "total": 1.0}
    write_outputs(env, {"output/balances.json": json.dumps(wrong)})
    assert env.step(act("submit")).reward == FORMAT_CREDIT


def test_writes_stay_inside_the_workspace(env):
    env.reset(task_id=SOME_TASK, seed=1)
    assert "inside" in env.step(act("write", path="../x", content="x")).error
    assert "inside" in env.step(act("write", path="/etc/x", content="x")).error
    env.step(act("bash", command="ln -s /etc/hostname link.txt"))
    assert env.step(act("write", path="link.txt", content="x")).error


def test_special_output_files_score_zero(env):
    env.reset(task_id=SOME_TASK, seed=1)
    env.step(act("bash", command="mkdir -p output && mkfifo output/balances.json"))
    assert env.step(act("submit")).reward == 0.0
    env.reset(task_id=SOME_TASK, seed=1)
    env.step(act("bash", command="mkdir -p output && ln -s /etc/hostname output/balances.json"))
    assert env.step(act("submit")).reward == 0.0


def test_call_limit_grades_the_outputs(env):
    env.reset(task_id=SOME_TASK, seed=1)
    task = env._require_episode()["task"]
    for _ in range(MAX_CALLS - 2):
        env.step(act("bash", command="true"))
    write_outputs(env, task.oracle)
    obs = env.step(act("bash", command="true"))
    assert obs.done is True and obs.reward == 1.0


def test_episode_files_are_removed_on_close(tmp_path):
    environment = DeskEnvironment(families=FAMILIES, work_root=str(tmp_path))
    environment.reset(task_id=SOME_TASK)
    assert os.listdir(tmp_path)
    environment.close()
    assert not os.listdir(tmp_path)


def test_client_seed_is_ignored_by_default(tmp_path):
    a = DeskEnvironment(families=FAMILIES, work_root=str(tmp_path))
    b = DeskEnvironment(families=FAMILIES, work_root=str(tmp_path))
    a.reset(task_id=SOME_TASK, seed=1)
    b.reset(task_id=SOME_TASK, seed=1)
    assert a._require_episode()["task"].files != b._require_episode()["task"].files
    a.close()
    b.close()


def test_task_ids():
    assert parse_task_id("fin4-L2") == ("fin4", 2)
    assert parse_task_id("sci10-L1") == ("sci10", 1)
    for bad in ("fin4", "fin4-L4", "FIN4-L1", "fin4-L1 "):
        with pytest.raises(ValueError):
            parse_task_id(bad)


def test_checks():
    assert value_ok(Check("num", tol=0.01), 1.005, 1.0)
    assert not value_ok(Check("num", tol=0.01), "1.0", 1.0)
    assert not value_ok(Check("num"), True, 1)
    assert value_ok(Check("int"), 4.0, 4) and not value_ok(Check("int"), 4.5, 4)
    assert value_ok(Check("set"), ["b", "a", 1.0], ["a", 1, "b"])
    assert not value_ok(Check("set"), ["a", "a"], ["a", "b"])
    assert value_ok(Check("list", tol=0.1), [1.05, "x"], [1, "x"])
    assert not value_ok(Check("list"), ["x", 1], [1, "x"])
    assert value_ok(Check("map", tol=0.01), {"A ": 1.0, "B": 2}, {"A": 1, "B": 2.0})
    assert not value_ok(Check("map"), {"A": 1}, {"A": 1, "B": 2})
    assert value_ok(Check("text"), " ok ", "ok") and value_ok(Check("bool"), True, True)


def test_csv_and_text_outputs():
    out = CsvOut(
        path="t.csv",
        header=("id", "n"),
        columns=(Check("text"), Check("num", tol=0.01)),
        rows=(("a", 1.0), ("b", 2.5)),
        key=0,
    )
    assert grade_texts([out], {"t.csv": "﻿id,n\nb,2.5\na,1.004\n"})[0] == 1.0
    assert grade_texts([out], {"t.csv": "id,n\na,1\nb,9\n"})[0] == FORMAT_CREDIT
    assert grade_texts([out], {"t.csv": "id,value\na,1\nb,2.5\n"})[0] == 0.0
    assert grade_texts([out], {"t.csv": "id,n\na,1\n"})[0] == 0.0
    text = TextOut(path="v.txt", check=Check("num", tol=0.5), want=12.0)
    assert grade_texts([text], {"v.txt": " 12.4\n"})[0] == 1.0
    assert grade_texts([text], {"v.txt": "thirteen"})[0] == 0.0
    both = [text, JsonOut(path="o.json", checks={"k": Check("int")}, want={"k": 2})]
    assert grade_texts(both, {"v.txt": "12", "o.json": '{"k": 3}'})[0] == FORMAT_CREDIT
    assert grade_texts(both, {"v.txt": "12"})[0] == 0.0
