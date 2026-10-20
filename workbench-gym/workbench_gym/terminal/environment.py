# SPDX-License-Identifier: Apache-2.0

"""
Terminal Workbench: Workbench Gym tasks behind the tbench2_env interface.

``reset(task_id=...)`` builds a fresh instance of a family and writes its files
into a new working directory. The agent then uses at most MAX_ACTIONS actions:

- ``exec``: run a shell command in the working directory (as ``nobody``).
- ``write_file``: write ``content`` to ``file_path`` inside the working directory.
- ``evaluate``: grade ``answer.json`` and end the episode.

Reward is binary: 1.0 when ``answer.json`` holds every answer field correctly,
0.0 otherwise. After the last allowed action the answer file is evaluated.
Like tbench2_env, every observation repeats the instruction.
"""

import json
import os
import random
import secrets
import shutil
import stat
import tempfile
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment

from ..core.grading import score_answer
from ..core.protocol import describe_kind, parse_task_id
from ..families import load_families
from .models import Tbench2Action, Tbench2Observation, Tbench2State
from .shell import cap_output, give_to_sandbox_user, run_shell

MAX_ACTIONS = 32
ANSWER_FILE = "answer.json"
MAX_ANSWER_BYTES = 64 * 1024
SESSION_ID = "tb2-session"
UNSUPPORTED = {"write", "view", "wait", "kill"}


def _work_root() -> str:
    root = os.environ.get("WG_WORK_ROOT", "/app")
    if os.path.isdir(root) and os.access(root, os.W_OK):
        return root
    return tempfile.gettempdir()


def instruction_text(question: str, fields: dict, workdir: str) -> str:
    field_list = "; ".join(f"{name} ({describe_kind(spec)})" for name, spec in fields.items())
    return (
        f"{question}\n"
        f"Your input files are in {workdir}, the working directory for exec.\n"
        f"Write your answer as one JSON object to {workdir}/{ANSWER_FILE} with these fields: "
        f"{field_list}.\n"
        'Then send {"action_type": "evaluate"}. The reward is 1 only if every field is right.\n'
        f"Actions: exec (a shell command), write_file (file_path, content), evaluate. "
        f"You have {MAX_ACTIONS} actions."
    )


class TerminalWorkbenchEnvironment(Environment):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, families=None, allow_seed: bool = False, work_root: str | None = None):
        super().__init__()
        self._families = families if families is not None else load_families()
        # Clients cannot choose the instance (see server.environment for why).
        self._allow_seed = allow_seed
        self._work_root = work_root
        self._episode: dict | None = None
        self._state = Tbench2State(episode_id=None, step_count=0)

    # ----- OpenEnv interface -------------------------------------------------

    def reset(self, seed=None, episode_id=None, task_id=None, **kwargs) -> Tbench2Observation:
        if not isinstance(task_id, str):
            raise ValueError("reset needs task_id")
        family_id, level = parse_task_id(task_id)
        family = self._families.get(family_id)
        if family is None or level not in family.levels:
            raise ValueError(f"unknown task_id: {task_id!r}")
        self.close()
        if seed is not None and self._allow_seed:
            rng = random.Random(seed)
        else:
            rng = random.Random(secrets.randbits(64))
        built = family.build(level, rng)

        root = self._work_root or _work_root()
        workdir = os.path.join(root, f"ep-{uuid4().hex[:12]}")
        os.makedirs(workdir, mode=0o700)
        for name, content in built.files.items():
            target = os.path.join(workdir, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content)
        give_to_sandbox_user(workdir)

        self._episode = {
            "task_id": task_id,
            "built": built,
            "workdir": workdir,
            "instruction": instruction_text(built.question, built.fields, workdir),
            "actions": 0,
            "done": False,
        }
        self._state = Tbench2State(
            episode_id=episode_id or str(uuid4()),
            step_count=0,
            task_id=task_id,
            task_path=workdir,
            session_id=SESSION_ID,
            terminal_ready=True,
        )
        return self._observation(output="", action_type="reset")

    def step(self, action: Tbench2Action, timeout_s=None, **kwargs) -> Tbench2Observation:
        ep = self._require_episode()
        if ep["done"]:
            return self._observation(
                output="",
                error="the episode is over",
                success=False,
                action_type=action.action_type,
                reward=0.0,
                done=True,
            )
        ep["actions"] += 1
        self._state.step_count = ep["actions"]
        self._state.last_action_type = action.action_type
        self._state.last_command = action.command

        kind = action.action_type
        if kind == "evaluate":
            return self._finish(self._grade(), "answer.json was evaluated", kind)
        if kind == "close":
            return self._finish(0.0, "Closed TB2 environment.", kind)

        output, error = "", ""
        if kind == "exec":
            if not action.command.strip():
                error = "exec needs a command"
            else:
                code, output = run_shell(action.command, ep["workdir"])
                if code != 0:
                    error = f"command exited with status {code}"
        elif kind == "write_file":
            output, error = self._write_file(action.file_path, action.content)
        elif kind in UNSUPPORTED:
            error = f"{kind} is not available here; use exec, write_file or evaluate"
        else:
            error = f"Unsupported action_type: {kind}"
        self._state.last_output = output

        if ep["actions"] >= MAX_ACTIONS:
            note = f"\n[action limit of {MAX_ACTIONS} reached; answer.json was evaluated]"
            return self._finish(self._grade(), cap_output(output + note), kind)
        return self._observation(output=output, error=error, success=not error, action_type=kind)

    @property
    def state(self) -> Tbench2State:
        return self._state

    def close(self) -> None:
        if self._episode is not None:
            shutil.rmtree(self._episode["workdir"], ignore_errors=True)
            self._episode = None

    # ----- helpers -------------------------------------------------------------

    def _write_file(self, file_path: str, content: str) -> tuple[str, str]:
        workdir = self._require_episode()["workdir"]
        if not file_path:
            return "", "write_file needs file_path"
        target = file_path if os.path.isabs(file_path) else os.path.join(workdir, file_path)
        real_dir = os.path.realpath(workdir)
        real_target = os.path.realpath(target)
        if os.path.commonpath([real_dir, real_target]) != real_dir or real_target == real_dir:
            return "", f"file_path must be inside {workdir}"
        if os.path.islink(target):
            return "", "file_path must not be a symlink"
        os.makedirs(os.path.dirname(real_target), exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        try:
            fd = os.open(real_target, flags, 0o644)
        except OSError as exc:
            return "", f"cannot write {file_path}: {exc.strerror}"
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        give_to_sandbox_user(os.path.dirname(real_target))
        return f"Wrote content to {file_path}", ""

    def _grade(self) -> float:
        ep = self._require_episode()
        path = os.path.join(ep["workdir"], ANSWER_FILE)
        try:
            info = os.lstat(path)
        except OSError:
            return 0.0
        # Only a small regular file: a symlink or a pipe could make the server
        # read something else or block forever.
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ANSWER_BYTES:
            return 0.0
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "r", encoding="utf-8", errors="replace") as fh:
                answer = json.loads(fh.read(MAX_ANSWER_BYTES))
        except (OSError, ValueError):
            return 0.0
        built = ep["built"]
        return 1.0 if score_answer(answer, built.fields, built.answer) == 1.0 else 0.0

    def _finish(self, reward: float, output: str, kind: str) -> Tbench2Observation:
        ep = self._require_episode()
        ep["done"] = True
        return self._observation(output=output, action_type=kind, reward=reward, done=True)

    def _require_episode(self) -> dict:
        if self._episode is None:
            raise RuntimeError("call reset(task_id=...) first")
        return self._episode

    def _observation(
        self,
        output: str,
        action_type: str,
        error: str = "",
        success: bool = True,
        reward: float | None = None,
        done: bool = False,
    ) -> Tbench2Observation:
        ep = self._episode or {}
        return Tbench2Observation(
            instruction=ep.get("instruction", ""),
            output=output,
            success=success,
            error=error,
            task_id=ep.get("task_id", ""),
            task_path=ep.get("workdir", ""),
            session_id=SESSION_ID,
            action_type=action_type,
            info={"actions_left": max(MAX_ACTIONS - ep.get("actions", 0), 0)},
            reward=reward,
            done=done,
        )
