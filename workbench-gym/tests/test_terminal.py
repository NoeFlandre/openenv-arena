# SPDX-License-Identifier: Apache-2.0

"""Terminal Workbench: the tbench2_env interface over the Workbench families."""

import json
import os

import pytest
from workbench_gym.families import load_families
from workbench_gym.terminal.environment import MAX_ACTIONS, TerminalWorkbenchEnvironment
from workbench_gym.terminal.models import Tbench2Action, Tbench2Observation

FAMILIES = load_families()

# Field names and defaults of OpenEnv's tbench2_env (pinned revision 86a180e).
TB2_ACTION_DEFAULTS = {
    "action_type": "exec",
    "command": "",
    "session_id": None,
    "block": True,
    "wait_seconds": None,
    "file_path": "",
    "content": "",
}
TB2_OBSERVATION_FIELDS = {
    "instruction",
    "output",
    "success",
    "error",
    "task_id",
    "task_path",
    "session_id",
    "action_type",
    "info",
    "done",
    "reward",
    "metadata",
}


@pytest.fixture
def env(tmp_path):
    environment = TerminalWorkbenchEnvironment(
        families=FAMILIES, allow_seed=True, work_root=str(tmp_path)
    )
    yield environment
    environment.close()


def act(**kwargs) -> Tbench2Action:
    return Tbench2Action(**kwargs)


def test_interface_matches_tbench2():
    action = Tbench2Action()
    for name, default in TB2_ACTION_DEFAULTS.items():
        assert getattr(action, name) == default
    assert set(Tbench2Observation.model_fields) == TB2_OBSERVATION_FIELDS
    assert Tbench2Action.__doc__ == "Action for interacting with a TB2 task session."


@pytest.mark.parametrize("family_id", sorted(FAMILIES))
def test_reference_answer_scores_one_and_decoys_zero(env, family_id):
    task_id = f"{family_id}-L1"
    env.reset(task_id=task_id, seed=0)
    built = env._require_episode()["built"]
    answer = FAMILIES[family_id].solve(dict(built.files), built.question)
    env.step(act(action_type="write_file", file_path="answer.json", content=json.dumps(answer)))
    obs = env.step(act(action_type="evaluate"))
    assert obs.done is True and obs.reward == 1.0

    env.reset(task_id=task_id, seed=0)
    env.step(
        act(
            action_type="write_file",
            file_path="answer.json",
            content=json.dumps(env._require_episode()["built"].decoys[0]),
        )
    )
    assert env.step(act(action_type="evaluate")).reward == 0.0


def test_shell_can_write_the_answer(env):
    env.reset(task_id="med2-L1", seed=4)
    built = env._require_episode()["built"]
    answer = FAMILIES["med2"].solve(dict(built.files), built.question)
    command = f"printf '%s' '{json.dumps(answer)}' > answer.json"
    assert env.step(act(action_type="exec", command=command)).success
    assert env.step(act(action_type="evaluate")).reward == 1.0


def test_missing_or_malformed_answer_scores_zero(env):
    env.reset(task_id="sec2-L2", seed=1)
    assert env.step(act(action_type="evaluate")).reward == 0.0
    env.reset(task_id="sec2-L2", seed=1)
    env.step(act(action_type="write_file", file_path="answer.json", content="not json"))
    assert env.step(act(action_type="evaluate")).reward == 0.0


def test_writes_stay_inside_the_workspace(env):
    env.reset(task_id="sec2-L2", seed=1)
    assert "inside" in env.step(act(action_type="write_file", file_path="../x", content="x")).error
    assert (
        "inside" in env.step(act(action_type="write_file", file_path="/etc/x", content="x")).error
    )
    env.step(act(action_type="exec", command="ln -s /etc/hostname link.txt"))
    assert env.step(act(action_type="write_file", file_path="link.txt", content="x")).error


def test_special_answer_files_score_zero_without_blocking(env):
    env.reset(task_id="sec2-L2", seed=1)
    env.step(act(action_type="exec", command="mkfifo answer.json"))
    assert env.step(act(action_type="evaluate")).reward == 0.0
    env.reset(task_id="sec2-L2", seed=1)
    env.step(act(action_type="exec", command="ln -s /etc/hostname answer.json"))
    assert env.step(act(action_type="evaluate")).reward == 0.0


def test_action_limit_evaluates_the_answer(env):
    env.reset(task_id="med1-L1", seed=2)
    obs = None
    for _ in range(MAX_ACTIONS):
        obs = env.step(act(action_type="exec", command="true"))
    assert obs.done is True and obs.reward == 0.0


def test_instruction_repeats_and_unsupported_actions_error(env):
    first = env.reset(task_id="med1-L1", seed=2)
    obs = env.step(act(action_type="view"))
    assert obs.instruction == first.instruction and obs.success is False
    assert obs.done is False


def test_episode_files_are_removed_on_close(tmp_path):
    environment = TerminalWorkbenchEnvironment(families=FAMILIES, work_root=str(tmp_path))
    environment.reset(task_id="med1-L1")
    assert os.listdir(tmp_path)
    environment.close()
    assert not os.listdir(tmp_path)


def test_client_seed_is_ignored_by_default(tmp_path):
    a = TerminalWorkbenchEnvironment(families=FAMILIES, work_root=str(tmp_path))
    b = TerminalWorkbenchEnvironment(families=FAMILIES, work_root=str(tmp_path))
    a.reset(task_id="med2-L2", seed=1)
    b.reset(task_id="med2-L2", seed=1)
    assert a._require_episode()["built"].files != b._require_episode()["built"].files
    a.close()
    b.close()
