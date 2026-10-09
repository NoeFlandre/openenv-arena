# SPDX-License-Identifier: Apache-2.0

"""
Audit Trail environment.

Each task is one log from a fixed seed, in one of three families: auth logs
(cybersecurity), ledger (finance) and sensor readings (natural science). The
question states a rule. The agent searches the log with ``grep`` and ends the
episode with ``answer``. Reward is 1.0 for the right value and 0.0 otherwise.
"""

from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

from ..models import AuditTrailAction, AuditTrailObservation
from ..tasks import TASKS, build

MAX_STEPS = 10
MAX_MATCHES = 10

# Shared by all instances. The HTTP server builds a new instance per request,
# so the episode must live outside the instance. The arena runs one episode
# per sandbox at a time.
_episode: dict | None = None


class AuditTrailEnvironment(Environment):
    """Answer a question about one log by searching it with grep."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = False

    def reset(
        self,
        seed: int | None = None,
        episode_id: str | None = None,
        task_id: str | None = None,
        **kwargs,
    ) -> AuditTrailObservation:
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
        action: AuditTrailAction,
        timeout_s: float | None = None,
        **kwargs,
    ) -> AuditTrailObservation:  # type: ignore[override]
        ep = self._require_episode()
        if ep["done"]:
            return self._observation(output="the episode is over", done=True, reward=ep["reward"])

        ep["steps"] += 1
        if action.answer is not None and action.grep is None:
            correct = action.answer.strip().lower() == ep["answer"]
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

    def _finish(self, reward: float, output: str) -> AuditTrailObservation:
        ep = self._require_episode()
        ep["done"] = True
        ep["reward"] = reward
        return self._observation(output=output, done=True, reward=reward)

    def _observation(self, output: str, done: bool, reward: float) -> AuditTrailObservation:
        ep = self._require_episode()
        return AuditTrailObservation(
            task_id=ep["task_id"],
            question=ep["question"] if ep["steps"] == 0 else "",
            output=output,
            steps_left=max(0, MAX_STEPS - ep["steps"]),
            done=done,
            reward=reward,
        )
