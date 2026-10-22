# SPDX-License-Identifier: Apache-2.0

"""
Workbench Desk environment.

``reset(task_id=...)`` builds a fresh instance of a family and writes its input
files into a new workspace directory. The agent then has MAX_CALLS tool calls:

- ``bash`` runs a shell command in the workspace (as ``nobody``, 20 s limit).
- ``write`` writes ``content`` to ``path`` inside the workspace.
- ``submit`` grades the output files the instruction asks for and ends the episode.

Reward (see ``spec``): exact outputs earn 1.0. Other outputs receive partial
credit capped at 0.2, based on format and correct-value fractions. After the
last call the outputs are graded as they are. The instruction is sent once, at
reset.
"""

import os
import random
import secrets
import shutil
import tempfile
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

from .families import load_families, parse_task_id
from .models import DeskAction, DeskObservation
from .shell import MAX_OUTPUT_CHARS, cap_output, give_to_sandbox_user, run_shell
from .spec import grade_workdir

MAX_CALLS = 20
MAX_WRITE_CHARS = 64 * 1024
TOOL_ALIASES = {
    "bash": "bash",
    "exec": "bash",
    "shell": "bash",
    "run": "bash",
    "write": "write",
    "write_file": "write",
    "submit": "submit",
    "evaluate": "submit",
    "finish": "submit",
    "done": "submit",
}
COMMAND_KEYS = ("command", "cmd")
PATH_KEYS = ("path", "file_path", "filePath", "file")
CONTENT_KEYS = ("content", "text")


def _work_root() -> str:
    root = os.environ.get("WG_WORK_ROOT", "/root")
    if os.path.isdir(root) and os.access(root, os.W_OK):
        return root
    return tempfile.gettempdir()


def _arg(args: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = args.get(key)
        if isinstance(value, str):
            return value
    return ""


def tools_text(workdir: str) -> str:
    return (
        f"\n\nTools (one JSON object per reply): "
        f'{{"tool": "bash", "args": {{"command": "..."}}}} runs a shell command in {workdir} '
        f"(python3 with pandas, numpy and openpyxl is installed); "
        f'{{"tool": "write", "args": {{"path": "...", "content": "..."}}}} writes a file; '
        f'{{"tool": "submit", "args": {{}}}} checks your output files and ends the task. '
        f"You have {MAX_CALLS} calls. Command output is cut at {MAX_OUTPUT_CHARS} characters, "
        f"so print only what you need."
    )


class DeskEnvironment(Environment):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, families=None, allow_seed: bool = False, work_root: str | None = None):
        super().__init__()
        self._families = families if families is not None else load_families()
        # Clients cannot choose the instance: a chosen seed would let one session
        # rebuild another session's instance and read its answer.
        self._allow_seed = allow_seed
        self._work_root = work_root
        self._episode: dict | None = None
        self._state = State(episode_id=None, step_count=0)

    # ----- OpenEnv interface -------------------------------------------------

    def reset(self, seed=None, episode_id=None, task_id=None, **kwargs) -> DeskObservation:
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
        task = family.build(level, rng)

        root = self._work_root or _work_root()
        workdir = os.path.join(root, f"task-{uuid4().hex[:8]}")
        os.makedirs(workdir, mode=0o700)
        for name, content in task.files.items():
            target = os.path.join(workdir, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if isinstance(content, bytes):
                with open(target, "wb") as fh:
                    fh.write(content)
            else:
                with open(target, "w", encoding="utf-8") as fh:
                    fh.write(content)
        give_to_sandbox_user(workdir)

        self._episode = {
            "task_id": task_id,
            "task": task,
            "workdir": workdir,
            "calls": 0,
            "done": False,
        }
        self._state = State(episode_id=episode_id or str(uuid4()), step_count=0)
        text = task.text(workdir) + tools_text(workdir)
        return self._observation(text, reward=0.0)

    def step(self, action: DeskAction, timeout_s=None, **kwargs) -> DeskObservation:
        ep = self._require_episode()
        if ep["done"]:
            return self._observation("", error="the task is over", reward=0.0, done=True)
        ep["calls"] += 1
        self._state.step_count = ep["calls"]
        tool = TOOL_ALIASES.get(str(action.tool).strip().lower())
        args = action.args if isinstance(action.args, dict) else {}

        if tool == "submit":
            return self._finish()
        output, error = "", ""
        if tool == "bash":
            command = _arg(args, COMMAND_KEYS)
            if not command.strip():
                error = 'bash needs args.command, for example {"command": "ls -la"}'
            else:
                code, output = run_shell(command, ep["workdir"])
                if code != 0:
                    error = f"command exited with status {code}"
        elif tool == "write":
            output, error = self._write_file(_arg(args, PATH_KEYS), _arg(args, CONTENT_KEYS))
        else:
            error = f"unknown tool {action.tool!r}; use bash, write or submit"

        if ep["calls"] >= MAX_CALLS:
            return self._finish(prefix=output, note=f"[no calls left after {MAX_CALLS}]")
        return self._observation(output, error=error, reward=0.0)

    @property
    def state(self) -> State:
        return self._state

    def close(self) -> None:
        if self._episode is not None:
            shutil.rmtree(self._episode["workdir"], ignore_errors=True)
            self._episode = None

    # ----- helpers -------------------------------------------------------------

    def _write_file(self, file_path: str, content: str) -> tuple[str, str]:
        workdir = self._require_episode()["workdir"]
        if not file_path:
            return "", 'write needs args.path and args.content, for example {"path": "out.json"}'
        if len(content) > MAX_WRITE_CHARS:
            return "", f"content is over {MAX_WRITE_CHARS} characters; write it in parts with bash"
        target = file_path if os.path.isabs(file_path) else os.path.join(workdir, file_path)
        real_dir = os.path.realpath(workdir)
        real_target = os.path.realpath(target)
        if os.path.commonpath([real_dir, real_target]) != real_dir or real_target == real_dir:
            return "", f"path must be inside {workdir}"
        if os.path.islink(target):
            return "", "path must not be a symlink"
        os.makedirs(os.path.dirname(real_target), exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        try:
            fd = os.open(real_target, flags, 0o644)
        except OSError as exc:
            return "", f"cannot write {file_path}: {exc.strerror}"
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        give_to_sandbox_user(real_dir)
        return f"wrote {len(content)} characters to {real_target}", ""

    def _finish(self, prefix: str = "", note: str = "") -> DeskObservation:
        ep = self._require_episode()
        reward, verdict = grade_workdir(ep["task"].outputs, ep["workdir"])
        ep["done"] = True
        text = "\n".join(part for part in (prefix, note, f"graded: {verdict}") if part)
        return self._observation(cap_output(text), reward=reward, done=True)

    def _require_episode(self) -> dict:
        if self._episode is None:
            raise RuntimeError("call reset(task_id=...) first")
        return self._episode

    def _observation(
        self, output: str, error: str = "", reward: float = 0.0, done: bool = False
    ) -> DeskObservation:
        ep = self._episode or {}
        return DeskObservation(
            output=output,
            error=error,
            calls_left=max(MAX_CALLS - ep.get("calls", 0), 0),
            reward=reward,
            done=done,
        )
