# SPDX-License-Identifier: Apache-2.0

"""
Derivation Check environment.

Each task is one log from a fixed seed, in one of two families: a worked
calculation with some wrong equations (math) and a list of captions with a
length limit (media). The question asks for the first line that breaks the rule.
The agent searches the log with ``grep`` and ends the episode with ``answer``.
Reward is 1.0 for the right value and 0.0 otherwise.
"""

import re
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

from ..models import DerivationCheckAction, DerivationCheckObservation
from ..tasks import TASKS, build

MAX_STEPS = 10
MAX_MATCHES = 10

NUMBER = re.compile(r"(?:step|cap)?\s*#?(\d+)\.?", re.IGNORECASE)


def _same_answer(given: str, expected: str) -> bool:
    """Accept a step or caption number in any spelling: 7, 07, step 07, cap 7 or 07."""
    text = given.strip()
    match = NUMBER.fullmatch(text)
    if match:
        return int(match.group(1)) == int(expected)
    return text.lower() == expected


# Shared by all instances. The HTTP server builds a new instance per request,
# so the episode must live outside the instance. The arena runs one episode
# per sandbox at a time.
_episode: dict | None = None


class DerivationCheckEnvironment(Environment):
    """Answer a question about one log by searching it with grep."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = False

    def reset(
        self,
        seed: int | None = None,
        episode_id: str | None = None,
        task_id: str | None = None,
        **kwargs,
    ) -> DerivationCheckObservation:
        global _episode
        task_id = task_id or next(iter(TASKS))
        if task_id not in TASKS:
            raise ValueError(f"unknown task_id {task_id!r}")

        built = build(task_id)
        _episode = {
            "episode_id": episode_id or str(uuid4()),
            "task_id": task_id,
            "lines": built.lines,
            "question": built.question,
            "answer": built.answer,
            "steps": 0,
            "done": False,
            "reward": 0.0,
        }
        return self._observation(output="", done=False, reward=0.0)

    def step(
        self,
        action: DerivationCheckAction,
        timeout_s: float | None = None,
        **kwargs,
    ) -> DerivationCheckObservation:  # type: ignore[override]
        ep = self._require_episode()
        if ep["done"]:
            return self._observation(output="the episode is over", done=True, reward=ep["reward"])

        ep["steps"] += 1
        if action.answer is not None and action.grep is None:
            correct = _same_answer(action.answer, ep["answer"])
            return self._finish(1.0 if correct else 0.0, "correct" if correct else "wrong")
        if action.grep is not None and action.answer is None:
            needle = action.grep.lower()
            matches = [line for line in ep["lines"] if needle in line.lower()]
            output = "\n".join(matches[:MAX_MATCHES]) or "no matching lines"
            if len(matches) > MAX_MATCHES:
                output += f"\n({len(matches)} matches, first {MAX_MATCHES} shown)"
        else:
            output = "send exactly one of grep or answer"

        if ep["steps"] >= MAX_STEPS:
            return self._finish(0.0, output + "\nno steps left")
        return self._observation(output=output, done=False, reward=0.0)

    @property
    def state(self) -> State:
        ep = _episode or {}
        return State(episode_id=ep.get("episode_id"), step_count=ep.get("steps", 0))

    def _require_episode(self) -> dict:
        if _episode is None:
            raise RuntimeError("call reset() before step()")
        return _episode

    def _finish(self, reward: float, output: str) -> DerivationCheckObservation:
        ep = self._require_episode()
        ep["done"] = True
        ep["reward"] = reward
        return self._observation(output=output, done=True, reward=reward)

    def _observation(self, output: str, done: bool, reward: float) -> DerivationCheckObservation:
        ep = self._require_episode()
        return DerivationCheckObservation(
            task_id=ep["task_id"],
            question=ep["question"] if ep["steps"] == 0 else "",
            output=output,
            steps_left=max(0, MAX_STEPS - ep["steps"]),
            done=done,
            reward=reward,
        )
