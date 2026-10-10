# SPDX-License-Identifier: Apache-2.0

"""
Workbench Gym environment.

``reset(task_id=...)`` picks a family and level and builds a fresh instance
(each reset draws new randomness; ``seed`` is honored only with allow_seed=True). The policy then
uses at most MAX_CALLS tool calls: ls, read, grep and py read the instance,
and submit ends the episode with the reward from core.grading.
"""

import random
import secrets
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

from ..core.grading import score_answer
from ..core.protocol import MAX_CALLS, parse_task_id, reset_text
from ..core.sandbox import run_python
from ..core.store import Store
from ..families import load_families
from ..models import WorkbenchAction, WorkbenchObservation


class WorkbenchEnvironment(Environment):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, families=None, allow_seed: bool = False):
        super().__init__()
        self._families = families if families is not None else load_families()
        # Clients cannot choose the instance. A client-chosen seed would let the
        # py tool open a second session and read answers, so only in-process
        # callers (calibration, tests) may pass one.
        self._allow_seed = allow_seed
        self._episode: dict | None = None
        self._state = State(episode_id=None, step_count=0)

    def reset(self, seed=None, episode_id=None, task_id=None, **kwargs) -> WorkbenchObservation:
        family_id, level = parse_task_id(task_id)
        family = self._families.get(family_id)
        if family is None or level not in family.levels:
            raise ValueError(f"unknown task_id: {task_id!r}")
        if seed is not None and self._allow_seed:
            rng = random.Random(seed)
        else:
            rng = random.Random(secrets.randbits(64))
        built = family.build(level, rng)
        episode_id = episode_id or str(uuid4())
        self._episode = {
            "task_id": task_id,
            "built": built,
            "store": Store(built.files),
            "calls": 0,
            "done": False,
        }
        self._state = State(episode_id=episode_id, step_count=0)
        output = reset_text(task_id, built.question, built.fields)
        return self._observation(output, ok=True, done=False, reward=0.0)

    def step(self, action: WorkbenchAction, timeout_s=None, **kwargs) -> WorkbenchObservation:
        ep = self._require_episode()
        if ep["done"]:
            return self._observation("the episode is over", ok=False, done=True, reward=0.0)
        ep["calls"] += 1
        self._state = State(episode_id=self._state.episode_id, step_count=ep["calls"])
        tool = action.tool
        args = action.args or {}

        if tool == "submit":
            built = ep["built"]
            answer = args.get("answer")
            reward = score_answer(answer, built.fields, built.answer)
            return self._finish(reward, "graded")

        ok, output = self._run_tool(ep, tool, args)
        if ep["calls"] >= MAX_CALLS:
            return self._finish(0.0, output + "\nno calls left; the episode ended without submit")
        return self._observation(output, ok=ok, done=False, reward=0.0)

    @property
    def state(self) -> State:
        return self._state

    def _run_tool(self, ep: dict, tool: str, args: dict) -> tuple[bool, str]:
        store: Store = ep["store"]
        if tool == "ls":
            return store.ls(args.get("path", ""))
        if tool == "read":
            return store.read(args.get("path"), args.get("start", 0), args.get("count", 1))
        if tool == "grep":
            return store.grep(args.get("path", ""), args.get("text"))
        if tool == "py":
            return True, run_python(args.get("lines"), ep["built"].files)
        return False, f"unknown tool {tool!r}; use ls, read, grep, py or submit"

    def _finish(self, reward: float, output: str) -> WorkbenchObservation:
        self._require_episode()["done"] = True
        return self._observation(output, ok=True, done=True, reward=reward)

    def _require_episode(self) -> dict:
        if self._episode is None:
            raise RuntimeError("call reset(task_id=...) first")
        return self._episode

    def _observation(self, output: str, ok: bool, done: bool, reward: float) -> WorkbenchObservation:
        ep = self._episode or {}
        return WorkbenchObservation(
            task_id=ep.get("task_id", ""),
            output=output,
            ok=ok,
            calls_left=max(MAX_CALLS - ep.get("calls", 0), 0),
            done=done,
            reward=reward,
        )
